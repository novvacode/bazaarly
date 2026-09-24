"""Order creation, tracking, merchant transitions and COD payment (SPEC §10)."""

from __future__ import annotations

import base64
import binascii
import re
import uuid
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core import errors
from app.core.errors import AppError
from app.core.phone import normalize_phone
from app.core.security import random_token
from app.core.tenancy import TenantContext
from app.models.order import (
    FulfillmentMode,
    Order,
    OrderItem,
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
)
from app.models.tenant import Tenant
from app.queue.producer import enqueue_in_tx
from app.repositories import menu as menu_repo
from app.repositories import orders as repo
from app.repositories import tenants as tenant_repo
from app.schemas.order import (
    BusinessContactOut,
    OrderCreatedOut,
    OrderCreateIn,
    OrderDetailOut,
    OrderItemOut,
    OrderListOut,
    OrderSummaryOut,
    PublicOrderBrief,
    PublicOrderOut,
    StatusEventOut,
    TotalsOut,
)
from app.services import order_state
from app.services import public as public_service
from app.services.order_state import Actor, Effect, InvalidTransition

log = structlog.get_logger()

MAX_LINES = 30
MAX_QTY = 50


# --- Helpers -----------------------------------------------------------------------------------


def tracking_url(order: Order) -> str:
    return f"{get_settings().app_base_url.rstrip('/')}/o/{order.public_token}"


def _totals(order: Order) -> TotalsOut:
    return TotalsOut(
        subtotal_paise=order.subtotal_paise,
        delivery_fee_paise=order.delivery_fee_paise,
        total_paise=order.total_paise,
    )


def _brief(order: Order) -> PublicOrderBrief:
    return PublicOrderBrief(
        code=order.code,
        public_token=order.public_token,
        status=order.status,
        payment_method=order.payment_method,
        payment_status=order.payment_status,
        totals=_totals(order),
    )


def _items_out(items: list[OrderItem]) -> list[OrderItemOut]:
    return [
        OrderItemOut(
            menu_item_id=i.menu_item_id,
            name=i.name_snapshot,
            unit_price_paise=i.unit_price_paise,
            quantity=i.quantity,
            line_total_paise=i.line_total_paise,
        )
        for i in items
    ]


async def _timeline(session: AsyncSession, order_id: uuid.UUID) -> list[StatusEventOut]:
    return [
        StatusEventOut(
            from_status=e.from_status, to_status=e.to_status, at=e.created_at, note=e.note
        )
        for e in await repo.events_for(session, order_id)
    ]


async def apply_effects(session: AsyncSession, order: Order, effects: list[Effect]) -> None:
    """Translate state-machine effects into outbox jobs (same transaction as the change)."""
    ids = {"tenant_id": str(order.tenant_id), "order_id": str(order.id)}
    for effect in effects:
        if isinstance(effect, order_state.NotifyOwnerNewOrder):
            await enqueue_in_tx(
                session,
                "notifications.order_placed_owner",
                ids,
                idempotency_key=f"order_placed_owner:{order.id}",
            )
        elif isinstance(effect, order_state.NotifyCustomerStatus) and order.customer_email:
            await enqueue_in_tx(
                session,
                "notifications.order_status_customer",
                {**ids, "status": effect.status.value},
                idempotency_key=f"order_status_customer:{order.id}:{effect.status.value}",
            )


def _validation(message: str, field: str, code: str = errors.VALIDATION_ERROR) -> AppError:
    return AppError(code, message, 422, details={"fields": {field: message}})


# --- Creation (public) -------------------------------------------------------------------------


async def _created_response(session: AsyncSession, order: Order) -> OrderCreatedOut:
    from app.services import payments  # local import: payments depends on this module

    payment = await payments.checkout_params(session, order)
    return OrderCreatedOut(order=_brief(order), tracking_url=tracking_url(order), payment=payment)


def _check_fulfilment(tenant: Tenant, data: OrderCreateIn) -> tuple[str | None, str | None, int]:
    """Validate pickup/delivery details; return (address, area, delivery_fee_paise)."""
    mode = data.fulfillment_mode
    if mode.value not in tenant.fulfillment_modes:
        label = "Delivery" if mode == FulfillmentMode.delivery else "Pickup"
        raise _validation(
            f"{label} isn't available from this store",
            "fulfillment_mode",
            errors.FULFILLMENT_INVALID,
        )
    if mode == FulfillmentMode.pickup:
        return None, None, 0
    if not data.delivery_address:
        raise _validation(
            "Enter a delivery address", "delivery_address", errors.FULFILLMENT_INVALID
        )
    area = data.delivery_area
    if tenant.delivery_areas:
        match = next((a for a in tenant.delivery_areas if area and a.lower() == area.lower()), None)
        if match is None:
            raise _validation(
                "We don't deliver to that area", "delivery_area", errors.FULFILLMENT_INVALID
            )
        area = match
    return data.delivery_address, area, tenant.delivery_fee_paise


async def create_order(
    session: AsyncSession, slug: str, data: OrderCreateIn
) -> tuple[OrderCreatedOut, bool]:
    """Place an order from the storefront. Returns (response, created)."""
    tenant = await public_service.resolve_tenant(session, slug)

    # Idempotent resubmit: same key → same order, same response (SPEC §10.3.2).
    existing = await repo.get_by_idempotency_key(session, tenant.id, data.idempotency_key)
    if existing is not None:
        return await _created_response(session, existing), False

    if not tenant.accepts_orders:
        raise AppError(errors.STORE_CLOSED, "This store isn't taking orders right now", 409)

    # Merge duplicate lines, then price everything from the database.
    quantities: dict[uuid.UUID, int] = {}
    for line in data.items:
        quantities[line.menu_item_id] = quantities.get(line.menu_item_id, 0) + line.quantity
    over = [str(i) for i, q in quantities.items() if q > MAX_QTY]
    if over:
        raise AppError(
            errors.ORDER_ITEMS_INVALID,
            f"At most {MAX_QTY} of each item",
            422,
            details={"item_ids": over},
        )

    menu_items = {
        i.id: i for i in await menu_repo.get_items_by_ids(session, tenant.id, list(quantities))
    }
    invalid = [
        str(item_id)
        for item_id in quantities
        if (mi := menu_items.get(item_id)) is None
        or mi.deleted_at is not None
        or not mi.is_available
    ]
    if invalid:
        raise AppError(
            errors.ORDER_ITEMS_INVALID,
            "Some items are no longer available",
            422,
            details={"item_ids": invalid},
        )

    address, area, delivery_fee = _check_fulfilment(tenant, data)
    phone = normalize_phone(data.customer_phone)
    if phone is None:
        raise _validation(
            "Enter a valid 10-digit mobile number", "customer_phone", errors.PHONE_INVALID
        )

    order_items: list[OrderItem] = []
    subtotal = 0
    for item_id, qty in quantities.items():
        mi = menu_items[item_id]
        line_total = mi.price_paise * qty
        subtotal += line_total
        order_items.append(
            OrderItem(
                menu_item_id=mi.id,
                name_snapshot=mi.name,
                unit_price_paise=mi.price_paise,
                quantity=qty,
                line_total_paise=line_total,
            )
        )
    if subtotal < tenant.min_order_paise:
        raise AppError(
            errors.ORDER_BELOW_MINIMUM,
            "Your order is below the store's minimum",
            422,
            details={"min_order_paise": tenant.min_order_paise, "subtotal_paise": subtotal},
        )

    if data.payment_method == PaymentMethod.online:
        from app.services import payments

        payments.ensure_online_enabled()

    status = order_state.initial_status(data.payment_method)
    order_id = uuid.uuid4()
    tenant_id = tenant.id  # plain value: ORM attributes expire on rollback
    try:
        code = await repo.allocate_code(session, tenant.id)
        order = Order(
            id=order_id,
            tenant_id=tenant.id,
            code=code,
            public_token=random_token(32),
            idempotency_key=data.idempotency_key,
            customer_name=data.customer_name,
            customer_phone=phone,
            customer_email=str(data.customer_email) if data.customer_email else None,
            fulfillment_mode=data.fulfillment_mode,
            delivery_address=address,
            delivery_area=area,
            notes=data.notes or None,
            status=status,
            payment_method=data.payment_method,
            payment_status=PaymentStatus.pending,
            subtotal_paise=subtotal,
            delivery_fee_paise=delivery_fee,
            total_paise=subtotal + delivery_fee,
        )
        for item in order_items:
            item.order_id = order_id
        repo.add_order(session, order, order_items)
        await session.flush()
        repo.add_event(session, order.id, None, status, actor_user_id=None)
        await apply_effects(session, order, order_state.creation_effects(status))
        if status == OrderStatus.pending_payment:
            from app.services import payments

            await payments.schedule_expiry(session, order)
        await session.commit()
    except IntegrityError:
        # A concurrent request with the same idempotency key won the race.
        await session.rollback()
        existing = await repo.get_by_idempotency_key(session, tenant_id, data.idempotency_key)
        if existing is None:
            raise
        return await _created_response(session, existing), False

    log.info("order_created", order_id=str(order.id), code=order.code, total=order.total_paise)
    # For online orders this also creates the Razorpay order (502 if the provider fails; the
    # order then stays pending_payment and a resubmit with the same key retries it).
    return await _created_response(session, order), True


async def public_order(session: AsyncSession, token: str) -> PublicOrderOut:
    order = await repo.get_by_public_token(session, token)
    if order is None:
        raise errors.not_found("Order")
    tenant = await tenant_repo.get_by_resolved_id(session, order.tenant_id)
    assert tenant is not None
    return PublicOrderOut(
        code=order.code,
        status=order.status,
        fulfillment_mode=order.fulfillment_mode,
        payment_method=order.payment_method,
        payment_status=order.payment_status,
        customer_name=order.customer_name,
        delivery_address=order.delivery_address,
        delivery_area=order.delivery_area,
        notes=order.notes,
        items=_items_out(await repo.items_for(session, order.id)),
        totals=_totals(order),
        timeline=await _timeline(session, order.id),
        business=BusinessContactOut(
            name=tenant.name, slug=tenant.slug, phone=tenant.phone, address=tenant.address
        ),
        created_at=order.created_at,
        is_terminal=order.status in order_state.TERMINAL,
        can_pay=order.status == OrderStatus.pending_payment,
    )


# --- Merchant ----------------------------------------------------------------------------------


async def _get(
    session: AsyncSession, ctx: TenantContext, order_id: uuid.UUID, *, for_update: bool = False
) -> Order:
    order = await repo.get(session, ctx, order_id, for_update=for_update)
    if order is None:
        raise errors.not_found("Order")
    return order


def _summary(order: Order, item_count: int) -> OrderSummaryOut:
    return OrderSummaryOut(
        id=order.id,
        code=order.code,
        status=order.status,
        customer_name=order.customer_name,
        customer_phone=order.customer_phone,
        fulfillment_mode=order.fulfillment_mode,
        payment_method=order.payment_method,
        payment_status=order.payment_status,
        total_paise=order.total_paise,
        item_count=item_count,
        created_at=order.created_at,
    )


async def order_detail(
    session: AsyncSession, ctx: TenantContext, order_id: uuid.UUID
) -> OrderDetailOut:
    order = await _get(session, ctx, order_id)
    items = await repo.items_for(session, order.id)
    return OrderDetailOut(
        **_summary(order, sum(i.quantity for i in items)).model_dump(),
        public_token=order.public_token,
        customer_email=order.customer_email,
        delivery_address=order.delivery_address,
        delivery_area=order.delivery_area,
        notes=order.notes,
        items=_items_out(items),
        totals=_totals(order),
        timeline=await _timeline(session, order.id),
        allowed_transitions=sorted(
            order_state.allowed_transitions(order, Actor.merchant),
            key=lambda s: list(OrderStatus).index(s),
        ),
        refund_required=(
            order.status == OrderStatus.cancelled and order.payment_status == PaymentStatus.paid
        ),
    )


async def transition_order(
    session: AsyncSession,
    ctx: TenantContext,
    order_id: uuid.UUID,
    to: OrderStatus,
    reason: str | None,
) -> OrderDetailOut:
    order = await _get(session, ctx, order_id, for_update=True)
    try:
        effects = order_state.transition(order, to, Actor.merchant)
    except InvalidTransition as exc:
        allowed = sorted(s.value for s in order_state.allowed_transitions(order, Actor.merchant))
        raise AppError(
            errors.ORDER_INVALID_TRANSITION,
            str(exc),
            409,
            details={"from": exc.current.value, "to": exc.target.value, "allowed": allowed},
        ) from None
    previous = order.status
    order.status = to
    repo.add_event(session, order.id, previous, to, ctx.user_id, note=reason)
    await apply_effects(session, order, effects)
    await session.commit()
    log.info("order_transition", order_id=str(order.id), frm=previous.value, to=to.value)
    return await order_detail(session, ctx, order_id)


async def mark_cod_paid(
    session: AsyncSession, ctx: TenantContext, order_id: uuid.UUID
) -> OrderDetailOut:
    order = await _get(session, ctx, order_id, for_update=True)
    if order.payment_method != PaymentMethod.cod:
        raise AppError(errors.NOT_COD_ORDER, "Only cash orders can be marked paid by hand", 409)
    if order.status == OrderStatus.cancelled:
        raise AppError(errors.ORDER_INVALID_TRANSITION, "This order was cancelled", 409)
    if order.payment_status != PaymentStatus.paid:
        order.payment_status = PaymentStatus.paid
        await session.commit()
    return await order_detail(session, ctx, order_id)


# --- Listing -----------------------------------------------------------------------------------


def encode_cursor(order: Order) -> str:
    raw = f"{order.created_at.isoformat()}|{order.id}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        ts, oid = base64.urlsafe_b64decode(padded).decode().split("|")
        return datetime.fromisoformat(ts), uuid.UUID(oid)
    except (ValueError, binascii.Error, UnicodeDecodeError):
        raise AppError(
            errors.VALIDATION_ERROR,
            "Invalid cursor",
            422,
            details={"fields": {"cursor": "invalid"}},
        ) from None


def local_day_bounds(day: date, tz: str) -> tuple[datetime, datetime]:
    zone = ZoneInfo(tz)
    start = datetime.combine(day, time.min, tzinfo=zone)
    return start, start + timedelta(days=1)


async def list_orders(
    session: AsyncSession,
    ctx: TenantContext,
    *,
    statuses: list[OrderStatus],
    date_from: date | None,
    date_to: date | None,
    q: str | None,
    limit: int,
    cursor: str | None,
) -> OrderListOut:
    tenant = await tenant_repo.get(session, ctx)
    assert tenant is not None
    created_from = local_day_bounds(date_from, tenant.timezone)[0] if date_from else None
    created_to = local_day_bounds(date_to, tenant.timezone)[1] if date_to else None
    code = text_q = phone = None
    if q:
        q = q.strip().lstrip("#")
        digits = re.sub(r"\D", "", q)
        if q.isdigit() and len(q) <= 9:
            code = int(q)
        if len(digits) >= 4:
            phone = digits[-10:]
        if not q.isdigit():
            text_q = q[:100]
    filters = repo.OrderFilters(
        statuses=statuses,
        created_from=created_from,
        created_to=created_to,
        code=code,
        text=text_q,
        phone_digits=phone,
    )
    after = decode_cursor(cursor) if cursor else None
    rows = await repo.list_page(session, ctx, filters, limit=limit + 1, after=after)
    page, more = rows[:limit], len(rows) > limit
    counts = await repo.item_counts(session, [o.id for o in page])
    return OrderListOut(
        items=[_summary(o, counts.get(o.id, 0)) for o in page],
        next_cursor=encode_cursor(page[-1]) if more and page else None,
    )
