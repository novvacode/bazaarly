"""Payment jobs (SPEC §11, §12.6)."""

from __future__ import annotations

import uuid
from typing import Any

import structlog

from app.queue.context import JobContext
from app.queue.registry import handler
from app.services import payments

log = structlog.get_logger("jobs")


@handler("payments.process_webhook", max_attempts=8, timeout=30)
async def process_webhook(ctx: JobContext, payload: dict[str, Any]) -> None:
    async with ctx.sessionmaker() as session:
        await payments.process_webhook(session, uuid.UUID(payload["webhook_event_id"]))


@handler("orders.expire_unpaid", max_attempts=8, timeout=30)
async def expire_unpaid(ctx: JobContext, payload: dict[str, Any]) -> None:
    async with ctx.sessionmaker() as session:
        outcome = await payments.expire_unpaid(
            session, uuid.UUID(payload["tenant_id"]), uuid.UUID(payload["order_id"])
        )
    log.info("expire_unpaid", order_id=payload["order_id"], outcome=outcome)
