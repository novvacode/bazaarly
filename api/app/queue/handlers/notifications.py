"""Order notification emails (SPEC §15). Idempotent by construction: the consumer skips a job
whose idempotency key already completed, and each email is keyed per order (and status)."""

from __future__ import annotations

import uuid
from typing import Any

import structlog

from app.config import get_settings
from app.core.logging import mask_phone
from app.models.order import FulfillmentMode, Order, OrderStatus, PaymentMethod, PaymentStatus
from app.models.tenant import Tenant
from app.queue.context import JobContext
from app.queue.registry import handler
from app.repositories import orders as order_repo
from app.repositories import tenants as tenant_repo
from app.services.emails import render
from app.services.money import format_inr

log = structlog.get_logger("jobs")

CUSTOMER_COPY: dict[OrderStatus, tuple[str, str]] = {
    OrderStatus.placed: (
        "Order #{code} received",
        "we've received your order and will confirm it shortly.",
    ),
    OrderStatus.confirmed: ("Order #{code} confirmed", "{business} has confirmed your order."),
    OrderStatus.preparing: ("Order #{code} is being prepared", "your order is being prepared."),
    OrderStatus.ready: (
        "Order #{code} is ready for pickup",
        "your order is ready. Please come by to pick it up.",
    ),
    OrderStatus.out_for_delivery: (
        "Order #{code} is on the way",
        "your order is out for delivery.",
    ),
    OrderStatus.completed: ("Order #{code} completed", "thank you for ordering from {business}!"),
    OrderStatus.cancelled: (
        "Order #{code} was cancelled",
        "unfortunately your order was cancelled.",
    ),
}


class MissingRecord(Exception):
    """The order or tenant vanished; retrying won't help but the failure is recorded."""


async def _load(ctx: JobContext, payload: dict[str, Any]) -> tuple[Order, Tenant, dict[str, Any]]:
    tenant_id = uuid.UUID(payload["tenant_id"])
    order_id = uuid.UUID(payload["order_id"])
    async with ctx.sessionmaker() as session:
        order = await order_repo.get_for_system(session, tenant_id, order_id)
        tenant = await tenant_repo.get_by_resolved_id(session, tenant_id)
        if order is None or tenant is None:
            raise MissingRecord(f"order {order_id} / tenant {tenant_id} not found")
        items = await order_repo.items_for(session, order.id)
        events = await order_repo.events_for(session, order.id)
    base = get_settings().app_base_url.rstrip("/")
    common = {
        "business_name": tenant.name,
        "business_phone": tenant.phone,
        "code": order.code,
        "customer_name": order.customer_name,
        "items": [
            {
                "quantity": i.quantity,
                "name": i.name_snapshot,
                "line_total": format_inr(i.line_total_paise),
            }
            for i in items
        ],
        "delivery_fee": format_inr(order.delivery_fee_paise) if order.delivery_fee_paise else None,
        "total": format_inr(order.total_paise),
        "tracking_url": f"{base}/o/{order.public_token}",
        "dashboard_url": f"{base}/dashboard/orders/{order.id}",
        "last_note": events[-1].note if events else None,
    }
    return order, tenant, common


@handler("notifications.order_placed_owner", max_attempts=5, timeout=30)
async def order_placed_owner(ctx: JobContext, payload: dict[str, Any]) -> None:
    order, tenant, common = await _load(ctx, payload)
    if not tenant.email:
        log.info("owner_email_skipped", reason="no tenant email", order_id=str(order.id))
        return
    payment = (
        (
            "Cash on delivery"
            if order.fulfillment_mode == FulfillmentMode.delivery
            else "Pay at pickup"
        )
        if order.payment_method == PaymentMethod.cod
        else ("Paid online" if order.payment_status == PaymentStatus.paid else "Online")
    )
    email = render(
        "owner_new_order",
        to=tenant.email,
        subject=f"New order #{order.code} · {common['total']}",
        context={
            **common,
            "customer_phone": order.customer_phone,
            "fulfillment": "Delivery"
            if order.fulfillment_mode == FulfillmentMode.delivery
            else "Pickup",
            "delivery_address": order.delivery_address,
            "delivery_area": order.delivery_area,
            "notes": order.notes,
            "payment": payment,
        },
    )
    await ctx.email.send(email)
    log.info("owner_email_sent", order_id=str(order.id), phone=mask_phone(order.customer_phone))


@handler("notifications.order_status_customer", max_attempts=5, timeout=30)
async def order_status_customer(ctx: JobContext, payload: dict[str, Any]) -> None:
    order, tenant, common = await _load(ctx, payload)
    if not order.customer_email:
        return
    status = OrderStatus(payload["status"])
    subject_tpl, message_tpl = CUSTOMER_COPY[status]
    subject = subject_tpl.format(code=order.code, business=tenant.name)
    email = render(
        "customer_order_status",
        to=order.customer_email,
        subject=f"{subject} · {tenant.name}",
        context={
            **common,
            "headline": subject,
            "message": message_tpl.format(code=order.code, business=tenant.name),
            "note": common["last_note"] if status == OrderStatus.cancelled else None,
        },
    )
    await ctx.email.send(email)
