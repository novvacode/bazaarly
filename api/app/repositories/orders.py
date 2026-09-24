"""Orders, order items and status events. Tenant-scoped except lookups by public token."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Select, and_, func, literal, or_, select, text, tuple_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import TenantContext
from app.models.order import Order, OrderItem, OrderStatus, OrderStatusEvent
from app.models.tenant import Tenant


async def allocate_code(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    """Next per-tenant order code. Row-locks the tenant until the transaction ends."""
    result = await session.execute(
        update(Tenant)
        .where(Tenant.id == tenant_id)
        .values(order_seq=Tenant.order_seq + 1)
        .returning(Tenant.order_seq)
    )
    return int(result.scalar_one())


async def get_by_idempotency_key(
    session: AsyncSession, tenant_id: uuid.UUID, key: str
) -> Order | None:
    result = await session.execute(
        select(Order).where(Order.tenant_id == tenant_id, Order.idempotency_key == key)
    )
    return result.scalar_one_or_none()


def add_order(session: AsyncSession, order: Order, items: Sequence[OrderItem]) -> None:
    session.add(order)
    session.add_all(items)


def add_event(
    session: AsyncSession,
    order_id: uuid.UUID,
    from_status: OrderStatus | None,
    to_status: OrderStatus,
    actor_user_id: uuid.UUID | None,
    note: str | None = None,
) -> None:
    session.add(
        OrderStatusEvent(
            order_id=order_id,
            from_status=from_status,
            to_status=to_status,
            actor_user_id=actor_user_id,
            note=note,
        )
    )


async def get(
    session: AsyncSession, ctx: TenantContext, order_id: uuid.UUID, *, for_update: bool = False
) -> Order | None:
    stmt = select(Order).where(Order.id == order_id, Order.tenant_id == ctx.tenant_id)
    if for_update:
        stmt = stmt.with_for_update()
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_by_public_token(
    session: AsyncSession, token: str, *, for_update: bool = False
) -> Order | None:
    stmt = select(Order).where(Order.public_token == token)
    if for_update:
        stmt = stmt.with_for_update()
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_for_system(
    session: AsyncSession, tenant_id: uuid.UUID, order_id: uuid.UUID, *, for_update: bool = False
) -> Order | None:
    """For jobs/webhooks that carry an already-resolved tenant id."""
    stmt = select(Order).where(Order.id == order_id, Order.tenant_id == tenant_id)
    if for_update:
        stmt = stmt.with_for_update()
    return (await session.execute(stmt)).scalar_one_or_none()


async def items_for(session: AsyncSession, order_id: uuid.UUID) -> list[OrderItem]:
    result = await session.execute(
        select(OrderItem).where(OrderItem.order_id == order_id).order_by(OrderItem.created_at)
    )
    return list(result.scalars())


async def events_for(session: AsyncSession, order_id: uuid.UUID) -> list[OrderStatusEvent]:
    result = await session.execute(
        select(OrderStatusEvent)
        .where(OrderStatusEvent.order_id == order_id)
        .order_by(OrderStatusEvent.created_at, OrderStatusEvent.id)
    )
    return list(result.scalars())


async def item_counts(
    session: AsyncSession, order_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, int]:
    if not order_ids:
        return {}
    result = await session.execute(
        select(OrderItem.order_id, func.sum(OrderItem.quantity))
        .where(OrderItem.order_id.in_(order_ids))
        .group_by(OrderItem.order_id)
    )
    return {oid: int(n) for oid, n in result.tuples()}


@dataclass(frozen=True, slots=True)
class OrderFilters:
    statuses: Sequence[OrderStatus] = ()
    created_from: datetime | None = None
    created_to: datetime | None = None
    code: int | None = None
    text: str | None = None
    phone_digits: str | None = None


def _filtered(ctx: TenantContext, f: OrderFilters) -> Select[tuple[Order]]:
    stmt = select(Order).where(Order.tenant_id == ctx.tenant_id)
    if f.statuses:
        stmt = stmt.where(Order.status.in_(f.statuses))
    if f.created_from:
        stmt = stmt.where(Order.created_at >= f.created_from)
    if f.created_to:
        stmt = stmt.where(Order.created_at < f.created_to)
    search = []
    if f.code is not None:
        search.append(Order.code == f.code)
    if f.text:
        search.append(Order.customer_name.ilike(f"%{f.text}%"))
    if f.phone_digits:
        search.append(Order.customer_phone.like(f"%{f.phone_digits}%"))
    if search:
        stmt = stmt.where(or_(*search))
    return stmt


async def list_page(
    session: AsyncSession,
    ctx: TenantContext,
    filters: OrderFilters,
    *,
    limit: int,
    after: tuple[datetime, uuid.UUID] | None,
) -> list[Order]:
    stmt = _filtered(ctx, filters)
    if after is not None:
        after_ts, after_id = after
        stmt = stmt.where(
            tuple_(Order.created_at, Order.id) < tuple_(literal(after_ts), literal(after_id))
        )
    stmt = stmt.order_by(Order.created_at.desc(), Order.id.desc()).limit(limit)
    return list((await session.execute(stmt)).scalars())


# --- Dashboard aggregates ----------------------------------------------------------------------


async def status_counts(
    session: AsyncSession, ctx: TenantContext, start: datetime, end: datetime
) -> dict[OrderStatus, int]:
    result = await session.execute(
        select(Order.status, func.count())
        .where(Order.tenant_id == ctx.tenant_id, Order.created_at >= start, Order.created_at < end)
        .group_by(Order.status)
    )
    return {status: int(n) for status, n in result.tuples()}


def _counted() -> list[object]:
    """Orders that count towards sales: not cancelled and not waiting for payment."""
    return [Order.status.notin_([OrderStatus.cancelled, OrderStatus.pending_payment])]


async def paid_revenue(
    session: AsyncSession, ctx: TenantContext, start: datetime, end: datetime
) -> int:
    result = await session.execute(
        select(func.coalesce(func.sum(Order.total_paise), 0)).where(
            Order.tenant_id == ctx.tenant_id,
            Order.created_at >= start,
            Order.created_at < end,
            Order.payment_status == "paid",
            *_counted(),  # type: ignore[arg-type]
        )
    )
    return int(result.scalar_one())


async def top_items(
    session: AsyncSession, ctx: TenantContext, start: datetime, end: datetime, limit: int = 5
) -> list[tuple[str, int, int]]:
    """(name, quantity, revenue_paise) of the best sellers in the window."""
    result = await session.execute(
        select(
            OrderItem.name_snapshot,
            func.sum(OrderItem.quantity).label("qty"),
            func.sum(OrderItem.line_total_paise),
        )
        .join(Order, Order.id == OrderItem.order_id)
        .where(
            Order.tenant_id == ctx.tenant_id,
            Order.created_at >= start,
            Order.created_at < end,
            *_counted(),  # type: ignore[arg-type]
        )
        .group_by(OrderItem.name_snapshot)
        .order_by(text("qty DESC"), OrderItem.name_snapshot)
        .limit(limit)
    )
    return [(name, int(q), int(r)) for name, q, r in result.tuples()]


async def daily_series(
    session: AsyncSession, ctx: TenantContext, start: datetime, end: datetime, tz: str
) -> dict[str, tuple[int, int]]:
    """Local date (YYYY-MM-DD) → (orders, paid revenue) for counted orders in the window."""
    local_day = func.to_char(func.timezone(tz, Order.created_at), "YYYY-MM-DD")
    paid_total = func.coalesce(
        func.sum(Order.total_paise).filter(Order.payment_status == "paid"), 0
    )
    result = await session.execute(
        select(local_day.label("day"), func.count(), paid_total)
        .where(
            and_(
                Order.tenant_id == ctx.tenant_id,
                Order.created_at >= start,
                Order.created_at < end,
                *_counted(),  # type: ignore[arg-type]
            )
        )
        .group_by(text("day"))
    )
    return {day: (int(n), int(rev)) for day, n, rev in result.tuples()}
