from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import TenantContext
from app.models.tenant import Tenant


async def get(session: AsyncSession, ctx: TenantContext) -> Tenant | None:
    return await session.get(Tenant, ctx.tenant_id)


async def get_for_update(session: AsyncSession, ctx: TenantContext) -> Tenant | None:
    result = await session.execute(
        select(Tenant).where(Tenant.id == ctx.tenant_id).with_for_update()
    )
    return result.scalar_one_or_none()


async def get_by_slug(session: AsyncSession, slug: str) -> Tenant | None:
    result = await session.execute(select(Tenant).where(Tenant.slug == slug))
    return result.scalar_one_or_none()


async def get_by_resolved_id(session: AsyncSession, tenant_id: uuid.UUID) -> Tenant | None:
    """For public routes and jobs where the tenant id was already resolved (slug/token/job)."""
    return await session.get(Tenant, tenant_id)


async def slug_exists(session: AsyncSession, slug: str) -> bool:
    result = await session.execute(select(Tenant.id).where(Tenant.slug == slug))
    return result.first() is not None


async def create(session: AsyncSession, *, name: str, slug: str, email: str | None) -> Tenant:
    tenant = Tenant(name=name, slug=slug, email=email)
    session.add(tenant)
    await session.flush()
    return tenant


async def update_fields(session: AsyncSession, ctx: TenantContext, values: dict[str, Any]) -> None:
    if values:
        await session.execute(update(Tenant).where(Tenant.id == ctx.tenant_id).values(**values))


async def list_all(session: AsyncSession) -> list[Tenant]:
    """Platform admin only."""
    result = await session.execute(select(Tenant).order_by(Tenant.created_at.desc()))
    return list(result.scalars())
