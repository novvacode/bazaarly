"""Job worker (SPEC §12): `python -m app.queue.worker`.

Runs inside one asyncio process:
  * outbox relay (every 500 ms)          → relay.py
  * delayed-job promotion (every 1 s)   → scheduler.py
  * daily cron check (every 60 s)       → scheduler.py
  * crash recovery via XAUTOCLAIM (30 s)
  * N consumers reading the `bz:jobs` stream with a consumer group

Delivery is at-least-once; handlers are idempotent and a completed job's idempotency key is
remembered for 7 days, so side effects happen effectively once.
"""

from __future__ import annotations

import asyncio
import contextlib
import random
import signal
import socket
import time
import traceback
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import structlog
from redis.asyncio import Redis
from redis.exceptions import ResponseError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.integrations.email import EmailSender
from app.queue import keys, registry
from app.queue.context import JobContext
from app.queue.envelope import Envelope
from app.queue.relay import relay_once
from app.queue.scheduler import cron_once, promote_once
from app.queue.scripts import Scripts

log = structlog.get_logger("worker")

BASE_DELAY_S = 5.0
MAX_DELAY_S = 3600.0
RECLAIM_IDLE_MS = 60_000
SHUTDOWN_GRACE_S = 25.0


def backoff_delay_s(attempt: int, rng: random.Random | None = None) -> float:
    """Exponential backoff with full jitter: uniform(0, min(5 s · 2^attempt, 1 h))."""
    cap = min(BASE_DELAY_S * (2**attempt), MAX_DELAY_S)
    return (rng or random).uniform(0, cap)


class UnknownJobType(Exception):
    pass


@dataclass
class Worker:
    sessionmaker: async_sessionmaker[AsyncSession]
    redis: Redis
    email: EmailSender
    default_max_attempts: int = 5
    name: str = field(default_factory=lambda: f"{socket.gethostname()}-{uuid.uuid4().hex[:6]}")
    rng: random.Random = field(default_factory=random.Random)

    def __post_init__(self) -> None:
        self.scripts = Scripts.load(self.redis)
        self.stopping = asyncio.Event()
        self.in_flight: set[asyncio.Task[None]] = set()

    # --- Setup ---------------------------------------------------------------------------------

    async def ensure_group(self) -> None:
        try:
            await self.redis.xgroup_create(keys.JOBS, keys.GROUP, id="0", mkstream=True)
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    # --- Processing ----------------------------------------------------------------------------

    async def _stat(self, job_type: str, outcome: str) -> None:
        await self.redis.hincrby(keys.STATS, f"{job_type}:{outcome}", 1)

    async def process(self, entry_id: str, envelope: Envelope) -> str:
        """Run one delivery and settle it. Returns the outcome."""
        bound = log.bind(job_id=envelope.job_id, type=envelope.type, attempt=envelope.attempt)
        started = time.perf_counter()

        if await self.redis.exists(keys.done_key(envelope.idempotency_key)):
            await self.redis.xack(keys.JOBS, keys.GROUP, entry_id)
            await self._stat(envelope.type, "skipped")
            bound.info("job_skipped_duplicate")
            return "skipped"

        spec = registry.get(envelope.type)
        try:
            if spec is None:
                raise UnknownJobType(f"No handler registered for {envelope.type!r}")
            ctx = JobContext(self.sessionmaker, self.redis, self.email, envelope)
            await asyncio.wait_for(spec.fn(ctx, envelope.payload), timeout=spec.timeout_s)
        except Exception as exc:  # noqa: BLE001 - every failure is retried or dead-lettered
            duration = round((time.perf_counter() - started) * 1000, 1)
            if spec is not None and envelope.attempt + 1 < envelope.max_attempts:
                delay = backoff_delay_s(envelope.attempt, self.rng)
                run_at_ms = int((time.time() + delay) * 1000)
                await self.scripts.retry(
                    keys=[keys.DELAYED, keys.JOBS],
                    args=[run_at_ms, envelope.next_attempt().to_json(), keys.GROUP, entry_id],
                )
                await self._stat(envelope.type, "retried")
                bound.warning(
                    "job_retry", error=repr(exc), delay_s=round(delay, 1), duration_ms=duration
                )
                return "retried"
            await self.scripts.dead(
                keys=[keys.DEAD, keys.JOBS],
                args=[
                    envelope.to_json(),
                    type(exc).__name__,
                    str(exc)[:500],
                    "".join(traceback.format_exception(exc))[-4000:],
                    datetime.now(UTC).isoformat(),
                    keys.GROUP,
                    entry_id,
                ],
            )
            await self._stat(envelope.type, "dead")
            bound.error("job_dead", error=repr(exc), duration_ms=duration)
            return "dead"

        await self.redis.set(keys.done_key(envelope.idempotency_key), "1", ex=keys.DONE_TTL_S)
        await self.redis.xack(keys.JOBS, keys.GROUP, entry_id)
        await self._stat(envelope.type, "ok")
        bound.info("job_ok", duration_ms=round((time.perf_counter() - started) * 1000, 1))
        return "ok"

    async def _process_raw(self, entry_id: str, fields: dict[str, str]) -> str:
        try:
            envelope = Envelope.from_json(fields["envelope"])
        except (KeyError, ValueError) as exc:
            # Unparseable entry: dead-letter it as-is so it can be inspected.
            await self.scripts.dead(
                keys=[keys.DEAD, keys.JOBS],
                args=[
                    fields.get("envelope", ""),
                    "BadEnvelope",
                    str(exc),
                    "",
                    datetime.now(UTC).isoformat(),
                    keys.GROUP,
                    entry_id,
                ],
            )
            return "dead"
        return await self.process(entry_id, envelope)

    async def consume_once(self, count: int = 10, block_ms: int = 5000) -> int:
        """Read and process up to `count` new entries. Returns how many were read."""
        response: Any = await self.redis.xreadgroup(
            keys.GROUP, self.name, {keys.JOBS: ">"}, count=count, block=block_ms
        )
        n = 0
        for _stream, entries in response or []:
            for entry_id, fields in entries:
                n += 1
                await self._process_raw(entry_id, fields)
        return n

    async def recover_once(self, min_idle_ms: int = RECLAIM_IDLE_MS, count: int = 50) -> int:
        """Claim entries a dead worker read but never acknowledged; count that as an attempt."""
        _next, entries, deleted = await self.redis.xautoclaim(
            keys.JOBS, keys.GROUP, self.name, min_idle_time=min_idle_ms, start_id="0", count=count
        )
        for entry_id in deleted or []:
            await self.redis.xack(keys.JOBS, keys.GROUP, entry_id)
        for entry_id, fields in entries:
            try:
                envelope = Envelope.from_json(fields["envelope"]).next_attempt()
            except (KeyError, ValueError):
                await self._process_raw(entry_id, fields)
                continue
            log.warning(
                "job_recovered",
                job_id=envelope.job_id,
                type=envelope.type,
                attempt=envelope.attempt,
            )
            if envelope.attempt >= envelope.max_attempts:
                await self.scripts.dead(
                    keys=[keys.DEAD, keys.JOBS],
                    args=[
                        envelope.to_json(),
                        "WorkerCrashed",
                        "Job was claimed by a worker that never finished it",
                        "",
                        datetime.now(UTC).isoformat(),
                        keys.GROUP,
                        entry_id,
                    ],
                )
                await self._stat(envelope.type, "dead")
                continue
            await self.process(entry_id, envelope)
        return len(entries)

    # --- Loops ---------------------------------------------------------------------------------

    async def _every(
        self, interval_s: float, fn_name: str, fn: Callable[[], Awaitable[object]]
    ) -> None:
        while not self.stopping.is_set():
            try:
                await fn()
            except Exception:
                log.exception("loop_error", loop=fn_name)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self.stopping.wait(), timeout=interval_s)

    async def _consumer_loop(self, index: int) -> None:
        consumer = Worker(
            self.sessionmaker,
            self.redis,
            self.email,
            self.default_max_attempts,
            name=f"{self.name}-{index}",
            rng=self.rng,
        )
        while not self.stopping.is_set():
            try:
                await consumer.consume_once(block_ms=2000)
            except Exception:
                log.exception("consumer_error", consumer=consumer.name)
                await asyncio.sleep(1)

    async def run(self, *, concurrency: int, summary_hour: int) -> None:
        await self.ensure_group()
        log.info("worker_started", name=self.name, concurrency=concurrency)
        loops = [
            self._every(
                0.5,
                "relay",
                lambda: relay_once(self.sessionmaker, self.redis, self.default_max_attempts),
            ),
            self._every(1.0, "promote", lambda: promote_once(self.scripts)),
            self._every(
                60.0,
                "cron",
                lambda: cron_once(
                    self.sessionmaker,
                    self.redis,
                    summary_hour=summary_hour,
                    max_attempts=self.default_max_attempts,
                ),
            ),
            self._every(30.0, "recover", self.recover_once),
        ]
        background = [asyncio.create_task(c) for c in loops]
        consumers = [asyncio.create_task(self._consumer_loop(i)) for i in range(concurrency)]
        await self.stopping.wait()
        log.info("worker_stopping", grace_s=SHUTDOWN_GRACE_S)
        # Consumers finish the batch they're on (bounded); anything left is recovered later
        # by XAUTOCLAIM on another worker.
        _done, pending = await asyncio.wait(consumers, timeout=SHUTDOWN_GRACE_S)
        for task in [*pending, *background]:
            task.cancel()
        await asyncio.gather(*pending, *background, return_exceptions=True)
        await self._deregister(concurrency)
        log.info("worker_stopped")

    async def _deregister(self, concurrency: int) -> None:
        """Remove this worker's consumers from the group if they hold no pending entries."""
        for i in range(concurrency):
            name = f"{self.name}-{i}"
            with contextlib.suppress(ResponseError):
                pending: Any = await self.redis.xpending_range(
                    keys.JOBS, keys.GROUP, min="-", max="+", count=1, consumername=name
                )
                if not pending:
                    await self.redis.xgroup_delconsumer(keys.JOBS, keys.GROUP, name)


async def main() -> None:
    from app.config import get_settings
    from app.core.logging import configure_logging
    from app.core.sentry import init_sentry
    from app.db import dispose_engine, get_sessionmaker
    from app.integrations.email import get_email_sender
    from app.queue import handlers  # noqa: F401 - registers every handler
    from app.redis import close_redis, get_redis

    settings = get_settings()
    configure_logging(settings.log_level, json=settings.app_env != "local")
    init_sentry(settings, component="worker")
    worker = Worker(
        get_sessionmaker(), get_redis(), get_email_sender(), settings.job_default_max_attempts
    )
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, worker.stopping.set)
    try:
        await worker.run(
            concurrency=settings.worker_concurrency, summary_hour=settings.daily_summary_hour
        )
    finally:
        await dispose_engine()
        await close_redis()


if __name__ == "__main__":
    asyncio.run(main())
