"""Refresh tokens and invites (looked up by token hash — the token is the capability)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import TenantContext
from app.models.auth import Invite, RefreshToken
from app.models.user import Role


async def create_refresh(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    family_id: uuid.UUID,
    token_hash: str,
    tenant_id: uuid.UUID | None,
    expires_at: datetime,
) -> RefreshToken:
    row = RefreshToken(
        user_id=user_id,
        family_id=family_id,
        token_hash=token_hash,
        tenant_id=tenant_id,
        expires_at=expires_at,
    )
    session.add(row)
    await session.flush()
    return row


async def get_refresh_for_update(session: AsyncSession, token_hash: str) -> RefreshToken | None:
    result = await session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash).with_for_update()
    )
    return result.scalar_one_or_none()


async def revoke_family(session: AsyncSession, family_id: uuid.UUID) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )


async def create_invite(
    session: AsyncSession,
    ctx: TenantContext,
    *,
    role: Role,
    token_hash: str,
    expires_at: datetime,
) -> Invite:
    invite = Invite(
        tenant_id=ctx.tenant_id,
        role=role,
        token_hash=token_hash,
        created_by=ctx.user_id,
        expires_at=expires_at,
    )
    session.add(invite)
    await session.flush()
    return invite


async def get_invite_by_hash(
    session: AsyncSession, token_hash: str, *, for_update: bool = False
) -> Invite | None:
    stmt = select(Invite).where(Invite.token_hash == token_hash)
    if for_update:
        stmt = stmt.with_for_update()
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_pending_invites(session: AsyncSession, ctx: TenantContext) -> list[Invite]:
    result = await session.execute(
        select(Invite)
        .where(
            Invite.tenant_id == ctx.tenant_id,
            Invite.accepted_at.is_(None),
            Invite.expires_at > datetime.now(UTC),
        )
        .order_by(Invite.created_at.desc())
    )
    return list(result.scalars())
