"""Online payments through Razorpay (SPEC §11).

Two paths confirm a payment — the browser's checkout callback (`verify`) and Razorpay's
webhook — and both converge on `mark_paid`, which is idempotent: however many times and in
whatever order they arrive, the order moves to `placed` once and notifications go out once.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core import errors
from app.core.errors import AppError
from app.integrations import razorpay
from app.integrations.razorpay import RazorpayError
from app.models.order import Order, OrderStatus, PaymentMethod, PaymentStatus
from app.models.payment import Payment, ProviderPaymentStatus, WebhookEvent
from app.models.tenant import Tenant
from app.queue.producer import enqueue_in_tx
from app.repositories import orders as order_repo
from app.repositories import tenants as tenant_repo
from app.schemas.order import PaymentParamsOut
from app.services import order_state
from app.services.order_state import Actor
from app.services.orders import apply_effects

log = structlog.get_logger()

EXPIRY = timedelta(minutes=30)
PROVIDER = "razorpay"


def ensure_online_enabled() -> None:
    if not razorpay.online_payments_configured():
        raise AppError(
            errors.VALIDATION_ERROR,
            "Online payment isn't available; please choose cash",
            422,
            details={"fields": {"payment_method": "online payment unavailable"}},
        )


async def schedule_expiry(session: AsyncSession, order: Order) -> None:
    """Enqueue `orders.expire_unpaid` for +30 min in the order-creation transaction."""
    await enqueue_in_tx(
        session,
        "orders.expire_unpaid",
        {"tenant_id": str(order.tenant_id), "order_id": str(order.id)},
        idempotency_key=f"expire_unpaid:{order.id}",
        run_at=datetime.now(UTC) + EXPIRY,
    )


async def _payments_for(session: AsyncSession, order: Order) -> list[Payment]:
    result = await session.execute(
        select(Payment)
        .where(Payment.order_id == order.id, Payment.tenant_id == order.tenant_id)
        .order_by(Payment.created_at.desc())
    )
    return list(result.scalars())


async def start_online_payment(session: AsyncSession, order: Order, tenant: Tenant) -> Payment:
    """Create the Razorpay order for an online order (once). Raises 502 on provider failure."""
    order_id, tenant_id = order.id, order.tenant_id
    locked = await order_repo.get_for_system(session, tenant_id, order_id, for_update=True)
    assert locked is not None
    existing = await _payments_for(session, locked)
    if existing:
        await session.commit()
        return existing[0]
    try:
        provider_order = await razorpay.get_razorpay().create_order(
            amount_paise=locked.total_paise,
            receipt=str(locked.id),
            notes={"tenant_id": str(locked.tenant_id), "order_id": str(locked.id)},
        )
    except RazorpayError as exc:
        await session.rollback()
        log.error("razorpay_create_order_failed", order_id=str(order_id), error=str(exc))
        raise AppError(
            errors.PAYMENT_PROVIDER_ERROR,
            "We couldn't start the payment. Please try again in a moment.",
            502,
        ) from None
    payment = Payment(
        tenant_id=locked.tenant_id,
        order_id=locked.id,
        provider=PROVIDER,
        provider_order_id=provider_order.id,
        amount_paise=provider_order.amount,
        status=ProviderPaymentStatus.created,
        raw=provider_order.raw,
    )
    session.add(payment)
    await session.commit()
    return payment


async def checkout_params(session: AsyncSession, order: Order) -> PaymentParamsOut | None:
    """Razorpay Checkout parameters while an online order is awaiting payment."""
    if order.payment_method != PaymentMethod.online or order.status != OrderStatus.pending_payment:
        return None
    tenant = await tenant_repo.get_by_resolved_id(session, order.tenant_id)
    assert tenant is not None
    payments = await _payments_for(session, order)
    payment = payments[0] if payments else await start_online_payment(session, order, tenant)
    prefill = {"name": order.customer_name, "contact": order.customer_phone}
    if order.customer_email:
        prefill["email"] = order.customer_email
    return PaymentParamsOut(
        key_id=razorpay.get_razorpay().key_id,
        razorpay_order_id=payment.provider_order_id,
        amount_paise=payment.amount_paise,
        name=tenant.name,
        prefill=prefill,
    )


async def mark_paid(
    session: AsyncSession, provider_order_id: str, provider_payment_id: str
) -> bool:
    """The single convergence point for a successful payment. Commits. Returns True if this
    call recorded the payment, False if it was already recorded (or unknown)."""
    result = await session.execute(
        update(Payment)
        .where(
            Payment.provider_order_id == provider_order_id,
            Payment.status != ProviderPaymentStatus.paid,
        )
        .values(
            status=ProviderPaymentStatus.paid,
            provider_payment_id=provider_payment_id,
            updated_at=text("now()"),
        )
        .returning(Payment.order_id, Payment.tenant_id)
    )
    row = result.first()
    if row is None:
        await session.rollback()
        return False
    order_id, tenant_id = row
    order = await order_repo.get_for_system(session, tenant_id, order_id, for_update=True)
    assert order is not None
    order.payment_status = PaymentStatus.paid
    if order.status == OrderStatus.pending_payment:
        effects = order_state.transition(order, OrderStatus.placed, Actor.system)
        order.status = OrderStatus.placed
        order_repo.add_event(
            session,
            order.id,
            OrderStatus.pending_payment,
            OrderStatus.placed,
            actor_user_id=None,
            note="Paid online",
        )
        await apply_effects(session, order, effects)
    else:
        # Paid after the order was cancelled (e.g. expired while the webhook was late): keep it
        # cancelled and flag a manual refund on the order page.
        log.warning("payment_after_cancel", order_id=str(order.id), status=order.status.value)
    await session.commit()
    log.info("order_paid", order_id=str(order.id), provider_order_id=provider_order_id)
    return True


async def verify_checkout(
    session: AsyncSession,
    public_token: str,
    provider_order_id: str,
    provider_payment_id: str,
    signature: str,
) -> None:
    order = await order_repo.get_by_public_token(session, public_token)
    if order is None:
        raise errors.not_found("Order")
    if not any(
        p.provider_order_id == provider_order_id for p in await _payments_for(session, order)
    ):
        raise errors.not_found("Payment")
    secret = get_settings().razorpay_key_secret
    if not razorpay.verify_payment_signature(
        provider_order_id, provider_payment_id, signature, secret
    ):
        raise AppError(errors.PAYMENT_SIGNATURE_INVALID, "Payment could not be verified", 400)
    await mark_paid(session, provider_order_id, provider_payment_id)


async def public_checkout_params(session: AsyncSession, public_token: str) -> PaymentParamsOut:
    order = await order_repo.get_by_public_token(session, public_token)
    if order is None:
        raise errors.not_found("Order")
    params = await checkout_params(session, order)
    if params is None:
        raise AppError(errors.CONFLICT, "This order doesn't need a payment", 409)
    return params


# --- Webhooks ----------------------------------------------------------------------------------


async def ingest_webhook(
    session: AsyncSession, raw_body: bytes, signature: str | None, event_id: str | None
) -> bool:
    """Verify, store and enqueue a webhook. Returns False for a duplicate delivery.

    No business logic runs here (SPEC §11.4); `payments.process_webhook` does it.
    """
    if not razorpay.verify_webhook_signature(
        raw_body, signature or "", get_settings().razorpay_webhook_secret
    ):
        raise AppError(errors.WEBHOOK_SIGNATURE_INVALID, "Invalid signature", 400)
    try:
        payload = json.loads(raw_body)
    except ValueError:
        raise AppError(errors.VALIDATION_ERROR, "Body is not JSON", 400) from None
    event_id = event_id or hashlib.sha256(raw_body).hexdigest()
    inserted = await session.execute(
        insert(WebhookEvent)
        .values(
            id=uuid.uuid4(),
            provider=PROVIDER,
            event_id=event_id,
            event_type=str(payload.get("event", "unknown"))[:100],
            payload=payload,
        )
        .on_conflict_do_nothing(index_elements=["provider", "event_id"])
        .returning(WebhookEvent.id)
    )
    webhook_id = inserted.scalar_one_or_none()
    if webhook_id is None:
        await session.rollback()
        return False
    await enqueue_in_tx(
        session,
        "payments.process_webhook",
        {"webhook_event_id": str(webhook_id)},
        idempotency_key=f"webhook:{PROVIDER}:{event_id}",
    )
    await session.commit()
    return True


def _payment_entity(payload: dict[str, Any]) -> dict[str, Any] | None:
    entity = payload.get("payload", {}).get("payment", {}).get("entity")
    return entity if isinstance(entity, dict) else None


async def process_webhook(session: AsyncSession, webhook_event_id: uuid.UUID) -> None:
    """Apply a stored webhook. Safe to repeat: `mark_paid` is idempotent and `processed_at` is
    only set after the effect is committed, so a crash in between just re-runs it."""
    event = await session.get(WebhookEvent, webhook_event_id)
    if event is None or event.processed_at is not None:
        await session.rollback()
        return
    kind, entity = event.event_type, _payment_entity(event.payload)
    await session.rollback()

    if kind in {"payment.captured", "order.paid"} and entity and entity.get("order_id"):
        await mark_paid(session, str(entity["order_id"]), str(entity["id"]))
    elif kind == "payment.failed" and entity and entity.get("order_id"):
        await session.execute(
            update(Payment)
            .where(
                Payment.provider_order_id == str(entity["order_id"]),
                Payment.status == ProviderPaymentStatus.created,
            )
            .values(status=ProviderPaymentStatus.failed)
        )
        await session.commit()
        log.info("payment_failed", provider_order_id=entity["order_id"])

    await session.execute(
        update(WebhookEvent)
        .where(WebhookEvent.id == webhook_event_id, WebhookEvent.processed_at.is_(None))
        .values(processed_at=datetime.now(UTC))
    )
    await session.commit()


# --- Expiry ------------------------------------------------------------------------------------


async def expire_unpaid(session: AsyncSession, tenant_id: uuid.UUID, order_id: uuid.UUID) -> str:
    """Cancel an order still awaiting payment — unless Razorpay says it was actually paid and
    the webhook is merely late. Returns what happened."""
    order = await order_repo.get_for_system(session, tenant_id, order_id)
    if order is None or order.status != OrderStatus.pending_payment:
        return "noop"
    provider_order_ids = [p.provider_order_id for p in await _payments_for(session, order)]
    await session.rollback()  # don't hold a transaction open across provider calls
    client = razorpay.get_razorpay()
    for provider_order_id in provider_order_ids:
        items = await client.order_payments(provider_order_id)  # raises → the job retries
        captured = next((p for p in items if p.get("status") == "captured"), None)
        if captured:
            await mark_paid(session, provider_order_id, str(captured["id"]))
            return "paid"

    order = await order_repo.get_for_system(session, tenant_id, order_id, for_update=True)
    if order is None or order.status != OrderStatus.pending_payment:
        await session.rollback()
        return "noop"
    effects = order_state.transition(order, OrderStatus.cancelled, Actor.system)
    order.status = OrderStatus.cancelled
    order_repo.add_event(
        session,
        order.id,
        OrderStatus.pending_payment,
        OrderStatus.cancelled,
        actor_user_id=None,
        note="Payment not completed in time",
    )
    await apply_effects(session, order, effects)
    await session.commit()
    return "cancelled"
