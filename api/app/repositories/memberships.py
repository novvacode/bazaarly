from __future__ import annotations

import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import TenantContext
from app.models.tenant import Tenant
from app.models.user import Membership, Role, User


async def get_role(session: AsyncSession, user_id: uuid.UUID, tenant_id: uuid.UUID) -> Role | None:
    """Used to authorize a claimed tenant before a TenantContext exists."""
    result = await session.execute(
        select(Membership.role).where(
            Membership.user_id == user_id, Membership.tenant_id == tenant_id
        )
    )
    return result.scalar_one_or_none()


async def list_for_user(
    session: AsyncSession, user_id: uuid.UUID
) -> list[tuple[Membership, Tenant]]:
    result = await session.execute(
        select(Membership, Tenant)
        .join(Tenant, Tenant.id == Membership.tenant_id)
        .where(Membership.user_id == user_id)
        .order_by(Membership.created_at, Membership.id)
    )
    return [(m, t) for m, t in result.tuples()]


async def create(
    session: AsyncSession, *, user_id: uuid.UUID, tenant_id: uuid.UUID, role: Role
) -> Membership:
    membership = Membership(user_id=user_id, tenant_id=tenant_id, role=role)
    session.add(membership)
    await session.flush()
    return membership


async def list_for_tenant(
    session: AsyncSession, ctx: TenantContext
) -> list[tuple[Membership, User]]:
    result = await session.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.tenant_id == ctx.tenant_id)
        .order_by(Membership.created_at, Membership.id)
    )
    return [(m, u) for m, u in result.tuples()]


async def get(
    session: AsyncSession, ctx: TenantContext, membership_id: uuid.UUID
) -> Membership | None:
    result = await session.execute(
        select(Membership).where(
            Membership.id == membership_id, Membership.tenant_id == ctx.tenant_id
        )
    )
    return result.scalar_one_or_none()


async def count_owners_for_update(session: AsyncSession, ctx: TenantContext) -> int:
    # Lock the owner rows so two concurrent removals can't both pass the last-owner check.
    rows = await session.execute(
        select(Membership.id)
        .where(Membership.tenant_id == ctx.tenant_id, Membership.role == Role.owner)
        .with_for_update()
    )
    return len(rows.all())


async def delete_one(session: AsyncSession, ctx: TenantContext, membership_id: uuid.UUID) -> None:
    await session.execute(
        delete(Membership).where(
            Membership.id == membership_id, Membership.tenant_id == ctx.tenant_id
        )
    )


async def count_for_tenant(session: AsyncSession, ctx: TenantContext) -> int:
    result = await session.execute(
        select(func.count()).select_from(Membership).where(Membership.tenant_id == ctx.tenant_id)
    )
    return int(result.scalar_one())
