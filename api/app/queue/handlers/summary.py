"""Daily summary email to the owner (SPEC §12.4.5, §15)."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from app.config import get_settings
from app.core.tenancy import TenantContext
from app.models.user import Role
from app.queue.context import JobContext
from app.queue.registry import handler
from app.repositories import tenants as tenant_repo
from app.services import dashboard
from app.services.emails import render
from app.services.money import format_inr

STATUS_NAMES = {
    "placed": "New",
    "confirmed": "Confirmed",
    "preparing": "Preparing",
    "ready": "Ready",
    "out_for_delivery": "Out for delivery",
    "completed": "Completed",
    "cancelled": "Cancelled",
    "pending_payment": "Awaiting payment",
}


@handler("summary.daily", max_attempts=3, timeout=60)
async def daily_summary(ctx: JobContext, payload: dict[str, Any]) -> None:
    tenant_id = uuid.UUID(payload["tenant_id"])
    day = date.fromisoformat(payload["date"])
    async with ctx.sessionmaker() as session:
        tenant = await tenant_repo.get_by_resolved_id(session, tenant_id)
        if tenant is None or not tenant.email:
            return
        # A system context for the owner-facing aggregate queries (read-only).
        system = TenantContext(tenant_id=tenant_id, user_id=uuid.UUID(int=0), role=Role.owner)
        summary = await dashboard.summary(session, system, day)
    email = render(
        "daily_summary",
        to=tenant.email,
        subject=(
            f"{tenant.name}: {summary.orders_total} orders today · "
            f"{format_inr(summary.revenue_paise)}"
        ),
        context={
            "business_name": tenant.name,
            "date_label": day.strftime("%a %d %b %Y"),
            "orders_total": summary.orders_total,
            "revenue": format_inr(summary.revenue_paise),
            "by_status": [(STATUS_NAMES.get(k, k), v) for k, v in summary.orders_by_status.items()],
            "top_items": summary.top_items,
            "dashboard_url": f"{get_settings().app_base_url.rstrip('/')}/dashboard",
        },
    )
    await ctx.email.send(email)
