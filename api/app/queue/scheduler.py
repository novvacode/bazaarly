"""Delayed-job promotion and daily cron (SPEC §12.4.3, §12.4.5)."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import structlog
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.tenant import Tenant
from app.queue import keys
from app.queue.envelope import Envelope
from app.queue.relay import publish
from app.queue.scripts import Scripts

log = structlog.get_logger("scheduler")

PROMOTE_BATCH = 100


async def promote_once(scripts: Scripts, now_ms: int | None = None) -> int:
    """Atomically move due delayed jobs to the ready stream."""
    now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
    moved = await scripts.promote(
        keys=[keys.DELAYED, keys.JOBS], args=[now_ms, PROMOTE_BATCH, keys.STREAM_MAXLEN]
    )
    return int(moved)


async def cron_once(
    sessionmaker: async_sessionmaker[AsyncSession],
    redis: Redis,
    *,
    summary_hour: int,
    max_attempts: int,
    now: datetime | None = None,
) -> int:
    """Enqueue `summary.daily` for every tenant whose local time has reached `summary_hour`.

    A `SET NX` lock per tenant and local date means several scheduler replicas (or restarts)
    never enqueue the same summary twice.
    """
    now = now or datetime.now(UTC)
    async with sessionmaker() as session:
        tenants = (await session.execute(select(Tenant.id, Tenant.timezone))).all()
    enqueued = 0
    for tenant_id, tz in tenants:
        local = now.astimezone(ZoneInfo(tz))
        if local.hour < summary_hour:
            continue
        day = local.date().isoformat()
        lock = keys.cron_key("summary.daily", str(tenant_id), day)
        if not await redis.set(lock, "1", nx=True, ex=keys.CRON_LOCK_TTL_S):
            continue
        await publish(
            redis,
            Envelope(
                type="summary.daily",
                payload={"tenant_id": str(tenant_id), "date": day},
                idempotency_key=f"summary.daily:{tenant_id}:{day}",
                max_attempts=max_attempts,
            ),
        )
        enqueued += 1
    if enqueued:
        log.info("cron_enqueued", job="summary.daily", count=enqueued)
    return enqueued
