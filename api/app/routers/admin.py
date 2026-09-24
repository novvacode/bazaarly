"""Platform admin (SPEC §9.1). Invisible (404) to everyone but platform admins."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Path, Response, status
from sqlalchemy import func, select

from app.core import errors
from app.deps import AdminDep, SessionDep
from app.models.order import Order
from app.models.tenant import Tenant
from app.models.user import Membership
from app.queue import admin as queue_admin
from app.redis import get_redis
from app.schemas.admin import AdminTenantOut, DeadJobOut, JobStatsOut

router = APIRouter(prefix="/admin", tags=["admin"])
EntryId = Annotated[str, Path(pattern=r"^\d+-\d+$", max_length=40)]


@router.get("/tenants", response_model=list[AdminTenantOut], summary="All tenants")
async def tenants(_: AdminDep, session: SessionDep) -> list[AdminTenantOut]:
    week_ago = datetime.now(UTC) - timedelta(days=7)
    members = (
        select(Membership.tenant_id, func.count().label("n"))
        .group_by(Membership.tenant_id)
        .subquery()
    )
    orders = (
        select(
            Order.tenant_id,
            func.count().label("n"),
            func.count().filter(Order.created_at >= week_ago).label("recent"),
        )
        .group_by(Order.tenant_id)
        .subquery()
    )
    rows = await session.execute(
        select(Tenant, members.c.n, orders.c.n, orders.c.recent)
        .outerjoin(members, members.c.tenant_id == Tenant.id)
        .outerjoin(orders, orders.c.tenant_id == Tenant.id)
        .order_by(Tenant.created_at.desc())
    )
    return [
        AdminTenantOut(
            id=t.id,
            name=t.name,
            slug=t.slug,
            email=t.email,
            accepts_orders=t.accepts_orders,
            created_at=t.created_at,
            members=m or 0,
            orders=o or 0,
            orders_last_7_days=r or 0,
        )
        for t, m, o, r in rows.tuples()
    ]


@router.get("/jobs/stats", response_model=JobStatsOut, summary="Queue statistics")
async def job_stats(_: AdminDep) -> JobStatsOut:
    return JobStatsOut.model_validate(await queue_admin.stats(get_redis()))


@router.get("/jobs/dead", response_model=list[DeadJobOut], summary="Dead-lettered jobs")
async def dead_jobs(_: AdminDep) -> list[DeadJobOut]:
    return [DeadJobOut.model_validate(d) for d in await queue_admin.list_dead(get_redis())]


@router.post(
    "/jobs/dead/{entry_id}/retry",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Re-enqueue a dead job with attempt=0",
)
async def retry_dead(entry_id: EntryId, _: AdminDep) -> Response:
    if not await queue_admin.retry_dead(get_redis(), entry_id):
        raise errors.not_found("Dead job")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/jobs/dead/{entry_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Discard a dead job"
)
async def delete_dead(entry_id: EntryId, _: AdminDep) -> Response:
    if not await queue_admin.delete_dead(get_redis(), entry_id):
        raise errors.not_found("Dead job")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
