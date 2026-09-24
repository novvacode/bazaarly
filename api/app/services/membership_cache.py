"""Membership lookups cached in Redis for 60 s (SPEC §7.2); invalidated on change."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import Role
from app.redis import get_redis
from app.repositories import memberships as membership_repo

_TTL_S = 60
_NONE = "-"


def _key(user_id: uuid.UUID, tenant_id: uuid.UUID) -> str:
    return f"bz:member:{user_id}:{tenant_id}"


async def resolve_role(
    session: AsyncSession, user_id: uuid.UUID, tenant_id: uuid.UUID
) -> Role | None:
    redis = get_redis()
    cached = await redis.get(_key(user_id, tenant_id))
    if cached is not None:
        return None if cached == _NONE else Role(str(cached))
    role = await membership_repo.get_role(session, user_id, tenant_id)
    await redis.set(_key(user_id, tenant_id), role.value if role else _NONE, ex=_TTL_S)
    return role


async def invalidate(user_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    await get_redis().delete(_key(user_id, tenant_id))
