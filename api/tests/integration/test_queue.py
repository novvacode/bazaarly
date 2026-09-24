"""Job queue semantics against real Redis and Postgres (SPEC §12.8)."""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_sessionmaker
from app.integrations.email import MemoryEmailSender
from app.models.order import Outbox
from app.queue import keys, registry
from app.queue.envelope import Envelope
from app.queue.producer import enqueue_in_tx
from app.queue.registry import HandlerSpec
from app.queue.relay import publish, relay_once
from app.queue.scheduler import cron_once, promote_once
from app.queue.worker import Worker, backoff_delay_s
from app.redis import get_redis


@pytest.fixture
async def worker() -> Worker:
    w = Worker(
        get_sessionmaker(),
        get_redis(),
        MemoryEmailSender(),
        name="test-worker",
        rng=random.Random(7),
    )
    await w.ensure_group()
    return w


class Calls:
    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []
        self.fail_times = 0


@pytest.fixture
def test_handler() -> Iterator[Calls]:
    """Register `test.job`: records calls and fails the first `fail_times` times."""
    calls = Calls()

    async def fn(ctx: Any, payload: dict[str, Any]) -> None:
        calls.payloads.append(payload)
        if calls.fail_times > 0:
            calls.fail_times -= 1
            raise RuntimeError("boom")

    registry.REGISTRY["test.job"] = HandlerSpec("test.job", fn, max_attempts=3, timeout_s=5)
    yield calls
    registry.REGISTRY.pop("test.job", None)


def env(key: str = "k1", **kw: Any) -> Envelope:
    return Envelope(type="test.job", payload={"n": 1}, idempotency_key=key, max_attempts=3, **kw)


async def _stats() -> dict[str, str]:
    return await get_redis().hgetall(keys.STATS)


async def _pending() -> int:
    info = await get_redis().xpending(keys.JOBS, keys.GROUP)
    return int(info["pending"])


async def _delayed() -> list[tuple[str, float]]:
    return await get_redis().zrange(keys.DELAYED, 0, -1, withscores=True)


async def test_success_path(worker: Worker, test_handler: Calls) -> None:
    await publish(get_redis(), env())
    assert await worker.consume_once(block_ms=100) == 1
    assert test_handler.payloads == [{"n": 1}]
    assert await get_redis().exists(keys.done_key("k1"))
    assert await _pending() == 0
    assert (await _stats())["test.job:ok"] == "1"


async def test_retry_then_success(worker: Worker, test_handler: Calls) -> None:
    test_handler.fail_times = 1
    await publish(get_redis(), env())
    await worker.consume_once(block_ms=100)
    assert await _pending() == 0  # the failed delivery was acked...
    delayed = await _delayed()
    assert len(delayed) == 1  # ...and rescheduled with attempt + 1
    assert Envelope.from_json(delayed[0][0]).attempt == 1

    moved = await promote_once(worker.scripts, now_ms=int(time.time() * 1000) + 3_600_000)
    assert moved == 1
    await worker.consume_once(block_ms=100)
    assert len(test_handler.payloads) == 2
    stats = await _stats()
    assert (stats["test.job:retried"], stats["test.job:ok"]) == ("1", "1")


async def test_dead_letter_after_max_attempts(worker: Worker, test_handler: Calls) -> None:
    test_handler.fail_times = 99
    await publish(get_redis(), env())
    far_future = int(time.time() * 1000) + 10 * 3_600_000
    for _ in range(3):
        await worker.consume_once(block_ms=100)
        await promote_once(worker.scripts, now_ms=far_future)
    assert len(test_handler.payloads) == 3
    dead = await get_redis().xrange(keys.DEAD)
    assert len(dead) == 1
    fields = dead[0][1]
    assert fields["error_type"] == "RuntimeError"
    assert fields["error"] == "boom"
    assert "Traceback" in fields["traceback"]
    assert Envelope.from_json(fields["envelope"]).attempt == 2
    assert await _delayed() == []
    assert await _pending() == 0
    assert not await get_redis().exists(keys.done_key("k1"))


async def test_unknown_job_type_is_dead_lettered(worker: Worker) -> None:
    await publish(get_redis(), Envelope(type="nope", payload={}, idempotency_key="x"))
    await worker.consume_once(block_ms=100)
    dead = await get_redis().xrange(keys.DEAD)
    assert dead[0][1]["error_type"] == "UnknownJobType"


def test_backoff_delay_bounds() -> None:
    rng = random.Random(1)
    for attempt in range(15):
        cap = min(5 * 2**attempt, 3600)
        samples = [backoff_delay_s(attempt, rng) for _ in range(200)]
        assert all(0 <= s <= cap for s in samples)
        assert max(samples) > cap * 0.8  # full jitter actually spreads over the range


async def test_retry_is_scheduled_within_backoff_bounds(
    worker: Worker, test_handler: Calls
) -> None:
    test_handler.fail_times = 1
    await publish(get_redis(), env(attempt=1))
    before = time.time() * 1000
    await worker.consume_once(block_ms=100)
    after = time.time() * 1000
    ((_, score),) = await _delayed()
    assert before <= score <= after + 10_000  # attempt 1 → up to 10 s


async def test_dedupe_skips_completed_job(worker: Worker, test_handler: Calls) -> None:
    await publish(get_redis(), env())
    await publish(get_redis(), env())  # duplicate publish (e.g. relay crashed before commit)
    await worker.consume_once(block_ms=100)
    assert len(test_handler.payloads) == 1
    stats = await _stats()
    assert (stats["test.job:ok"], stats["test.job:skipped"]) == ("1", "1")
    assert await _pending() == 0


async def test_delayed_job_moves_only_when_due(worker: Worker, test_handler: Calls) -> None:
    run_at = int(time.time() * 1000) + 60_000
    await publish(get_redis(), env(), run_at_ms=run_at)
    assert await get_redis().xlen(keys.JOBS) == 0
    assert await promote_once(worker.scripts, now_ms=run_at - 1) == 0
    assert await worker.consume_once(block_ms=50) == 0
    assert await promote_once(worker.scripts, now_ms=run_at) == 1
    assert await _delayed() == []
    assert await worker.consume_once(block_ms=100) == 1
    assert test_handler.payloads == [{"n": 1}]


async def test_crash_recovery_via_xautoclaim(worker: Worker, test_handler: Calls) -> None:
    await publish(get_redis(), env())
    # A consumer reads the entry and "dies" without acknowledging it.
    await get_redis().xreadgroup(keys.GROUP, "crashed", {keys.JOBS: ">"}, count=1)
    assert await _pending() == 1
    assert await worker.recover_once(min_idle_ms=60_000) == 0  # not idle long enough yet
    await asyncio.sleep(0.02)
    assert await worker.recover_once(min_idle_ms=10) == 1
    assert test_handler.payloads == [{"n": 1}]
    assert await _pending() == 0


async def test_recovered_job_past_max_attempts_is_dead(worker: Worker, test_handler: Calls) -> None:
    await publish(get_redis(), env(attempt=2))  # last allowed attempt
    await get_redis().xreadgroup(keys.GROUP, "crashed", {keys.JOBS: ">"}, count=1)
    await asyncio.sleep(0.02)
    await worker.recover_once(min_idle_ms=10)
    assert test_handler.payloads == []
    dead = await get_redis().xrange(keys.DEAD)
    assert dead[0][1]["error_type"] == "WorkerCrashed"


async def test_relay_publishes_exactly_unpublished_rows(
    session: AsyncSession, worker: Worker
) -> None:
    for i in range(3):
        await enqueue_in_tx(session, "test.job", {"i": i}, idempotency_key=f"r{i}")
    later = datetime.now(UTC) + timedelta(minutes=30)
    await enqueue_in_tx(session, "test.job", {"i": 3}, idempotency_key="r3", run_at=later)
    await session.commit()

    sm = get_sessionmaker()
    assert await relay_once(sm, get_redis(), 5) == 4
    assert await relay_once(sm, get_redis(), 5) == 0  # nothing left
    assert await get_redis().xlen(keys.JOBS) == 3
    delayed = await _delayed()
    assert len(delayed) == 1
    assert abs(delayed[0][1] - later.timestamp() * 1000) < 1000

    session.expire_all()
    rows = (await session.execute(select(Outbox).order_by(Outbox.id))).scalars().all()
    assert all(r.published_at is not None for r in rows)

    # A row added later is picked up alone.
    await enqueue_in_tx(session, "test.job", {"i": 4}, idempotency_key="r4")
    await session.commit()
    assert await relay_once(sm, get_redis(), 5) == 1


async def test_concurrent_relays_do_not_double_publish(session: AsyncSession) -> None:
    for i in range(50):
        await enqueue_in_tx(session, "test.job", {"i": i}, idempotency_key=f"c{i}")
    await session.commit()
    sm = get_sessionmaker()
    counts = await asyncio.gather(*[relay_once(sm, get_redis(), 5) for _ in range(4)])
    assert sum(counts) == 50
    assert await get_redis().xlen(keys.JOBS) == 50


async def test_cron_lock_prevents_double_enqueue(session: AsyncSession) -> None:
    from tests.integration.test_notifications import make_tenant

    await make_tenant(session, email="owner@example.com")
    sm = get_sessionmaker()
    nine_pm_ist = datetime(2026, 9, 24, 15, 30, tzinfo=UTC)  # 21:00 in Asia/Kolkata
    before = nine_pm_ist - timedelta(hours=1)
    assert await cron_once(sm, get_redis(), summary_hour=21, max_attempts=3, now=before) == 0
    results = await asyncio.gather(
        cron_once(sm, get_redis(), summary_hour=21, max_attempts=3, now=nine_pm_ist),
        cron_once(sm, get_redis(), summary_hour=21, max_attempts=3, now=nine_pm_ist),
    )
    assert sorted(results) == [0, 1]
    # Later the same evening: still locked.
    assert (
        await cron_once(
            sm, get_redis(), summary_hour=21, max_attempts=3, now=nine_pm_ist + timedelta(hours=2)
        )
        == 0
    )
    entries = await get_redis().xrange(keys.JOBS)
    envelope = Envelope.from_json(entries[0][1]["envelope"])
    assert envelope.type == "summary.daily"
    assert envelope.payload["date"] == "2026-09-24"


async def test_worker_run_and_graceful_shutdown(test_handler: Calls) -> None:
    w = Worker(get_sessionmaker(), get_redis(), MemoryEmailSender(), name="runner")
    task = asyncio.create_task(w.run(concurrency=2, summary_hour=23))
    await asyncio.sleep(0.2)
    await publish(get_redis(), env("run-1"))
    for _ in range(50):
        if test_handler.payloads:
            break
        await asyncio.sleep(0.1)
    assert test_handler.payloads == [{"n": 1}]
    w.stopping.set()
    await asyncio.wait_for(task, timeout=10)
    consumers = await get_redis().xinfo_consumers(keys.JOBS, keys.GROUP)
    assert [c["name"] for c in consumers if c["name"].startswith("runner")] == []
