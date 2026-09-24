"""Owner dashboard aggregates, computed in the tenant's timezone (SPEC §9.1)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import TenantContext
from app.repositories import orders as repo
from app.repositories import tenants as tenant_repo
from app.schemas.order import DashboardSummaryOut, SalesOut, SalesPointOut, TopItemOut
from app.services.orders import local_day_bounds


async def _tz(session: AsyncSession, ctx: TenantContext) -> str:
    tenant = await tenant_repo.get(session, ctx)
    assert tenant is not None
    return tenant.timezone


def today_in(tz: str) -> date:
    return datetime.now(ZoneInfo(tz)).date()


async def summary(
    session: AsyncSession, ctx: TenantContext, day: date | None
) -> DashboardSummaryOut:
    tz = await _tz(session, ctx)
    day = day or today_in(tz)
    start, end = local_day_bounds(day, tz)
    counts = await repo.status_counts(session, ctx, start, end)
    top = await repo.top_items(session, ctx, start, end)
    return DashboardSummaryOut(
        date=day.isoformat(),
        timezone=tz,
        orders_total=sum(counts.values()),
        orders_by_status={s.value: n for s, n in counts.items()},
        revenue_paise=await repo.paid_revenue(session, ctx, start, end),
        top_items=[{"name": n, "quantity": q, "revenue_paise": r} for n, q, r in top],
    )


async def sales(session: AsyncSession, ctx: TenantContext, days: int) -> SalesOut:
    tz = await _tz(session, ctx)
    last = today_in(tz)
    first = last - timedelta(days=days - 1)
    start = local_day_bounds(first, tz)[0]
    end = local_day_bounds(last, tz)[1]
    rows = await repo.daily_series(session, ctx, start, end, tz)
    series = []
    for offset in range(days):
        d = (first + timedelta(days=offset)).isoformat()
        orders, revenue = rows.get(d, (0, 0))
        series.append(SalesPointOut(date=d, orders=orders, revenue_paise=revenue))
    top = await repo.top_items(session, ctx, start, end, limit=10)
    return SalesOut(
        days=days,
        timezone=tz,
        series=series,
        top_items=[TopItemOut(name=n, quantity=q, revenue_paise=r) for n, q, r in top],
    )
