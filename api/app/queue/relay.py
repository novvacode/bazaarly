"""Outbox relay (SPEC §12.4.1): publish committed outbox rows to Redis.

A crash between XADD and the commit re-publishes the batch next time; the consumers' dedupe
key (`bz:done:{idempotency_key}`) absorbs those duplicates.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.order import Outbox
from app.queue import keys, registry
from app.queue.envelope import Envelope

BATCH = 100


async def publish(redis: Redis, envelope: Envelope, run_at_ms: int | None = None) -> None:
    """Put an envelope on the ready stream, or on the delayed set if it's for later."""
    if run_at_ms is not None and run_at_ms > int(time.time() * 1000):
        await redis.zadd(keys.DELAYED, {envelope.to_json(): run_at_ms})
    else:
        await redis.xadd(
            keys.JOBS,
            {"envelope": envelope.to_json()},
            maxlen=keys.STREAM_MAXLEN,
            approximate=True,
        )


async def relay_once(
    sessionmaker: async_sessionmaker[AsyncSession], redis: Redis, default_max_attempts: int
) -> int:
    """Publish up to BATCH unpublished rows. Returns how many were published."""
    async with sessionmaker() as session, session.begin():
        rows = (
            (
                await session.execute(
                    select(Outbox)
                    .where(Outbox.published_at.is_(None))
                    .order_by(Outbox.id)
                    .limit(BATCH)
                    .with_for_update(skip_locked=True)
                )
            )
            .scalars()
            .all()
        )
        now = datetime.now(UTC)
        for row in rows:
            envelope = Envelope(
                type=row.job_type,
                payload=row.payload,
                idempotency_key=row.idempotency_key,
                max_attempts=registry.max_attempts_for(row.job_type, default_max_attempts),
            )
            run_at_ms = int(row.run_at.timestamp() * 1000) if row.run_at else None
            await publish(redis, envelope, run_at_ms)
            row.published_at = now
        return len(rows)
