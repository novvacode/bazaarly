"""The only way business code enqueues jobs (SPEC §12.5).

`enqueue_in_tx` writes an outbox row in the caller's transaction, so a job exists if and only
if the business change committed. The worker's relay publishes rows to Redis.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Outbox


async def enqueue_in_tx(
    session: AsyncSession,
    job_type: str,
    payload: dict[str, Any],
    idempotency_key: str,
    run_at: datetime | None = None,
) -> Outbox:
    row = Outbox(job_type=job_type, payload=payload, idempotency_key=idempotency_key, run_at=run_at)
    session.add(row)
    await session.flush()
    return row
