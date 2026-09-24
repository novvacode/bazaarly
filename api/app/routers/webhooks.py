"""Provider webhooks. Verified, stored and enqueued in well under 100 ms (SPEC §11.4)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header, Request

from app.deps import SessionDep
from app.services import payments

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/razorpay", summary="Razorpay webhook (payment.captured, payment.failed, …)")
async def razorpay_webhook(
    request: Request,
    session: SessionDep,
    signature: Annotated[str | None, Header(alias="X-Razorpay-Signature")] = None,
    event_id: Annotated[str | None, Header(alias="X-Razorpay-Event-Id", max_length=100)] = None,
) -> dict[str, str]:
    raw = await request.body()
    created = await payments.ingest_webhook(session, raw, signature, event_id)
    return {"status": "accepted" if created else "duplicate"}
