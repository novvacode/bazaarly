"""Auth and tenant-context dependencies (SPEC §7, §8)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated

import structlog
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import FORBIDDEN, UNAUTHORIZED, AppError
from app.core.security import AccessClaims, InvalidToken, decode_access_token
from app.core.tenancy import TenantContext
from app.db import get_session
from app.models.user import Role, User
from app.repositories import users as user_repo
from app.services import membership_cache

_bearer = HTTPBearer(auto_error=False, description="Access token from /auth/login")

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _unauthorized(message: str = "Authentication required") -> AppError:
    return AppError(UNAUTHORIZED, message, 401, headers={"WWW-Authenticate": "Bearer"})


async def get_optional_claims(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> AccessClaims | None:
    if creds is None or creds.scheme.lower() != "bearer":
        return None
    try:
        return decode_access_token(creds.credentials)
    except InvalidToken:
        raise _unauthorized("Invalid or expired access token") from None


async def get_claims(
    claims: Annotated[AccessClaims | None, Depends(get_optional_claims)],
) -> AccessClaims:
    if claims is None:
        raise _unauthorized()
    structlog.contextvars.bind_contextvars(user_id=str(claims.user_id))
    return claims


ClaimsDep = Annotated[AccessClaims, Depends(get_claims)]


async def get_current_user(claims: ClaimsDep, session: SessionDep) -> User:
    user = await user_repo.get_by_id(session, claims.user_id)
    if user is None:
        raise _unauthorized()
    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]


async def get_tenant_context(claims: ClaimsDep, session: SessionDep) -> TenantContext:
    """Re-verify on every request that the membership behind the token still exists."""
    if claims.tenant_id is None:
        raise AppError(FORBIDDEN, "No active business for this account", 403)
    role = await membership_cache.resolve_role(session, claims.user_id, claims.tenant_id)
    if role is None or role.value != claims.role:
        # Membership removed or role changed: the client should refresh its access token.
        raise _unauthorized("Your access changed; please sign in again")
    structlog.contextvars.bind_contextvars(tenant_id=str(claims.tenant_id))
    return TenantContext(tenant_id=claims.tenant_id, user_id=claims.user_id, role=role)


TenantDep = Annotated[TenantContext, Depends(get_tenant_context)]


def require_role(*roles: Role | str) -> Callable[[TenantContext], Awaitable[TenantContext]]:
    allowed = {Role(r) for r in roles}

    async def dependency(ctx: TenantDep) -> TenantContext:
        if ctx.role not in allowed:
            raise AppError(FORBIDDEN, "You don't have permission to do this", 403)
        return ctx

    return dependency


OwnerDep = Annotated[TenantContext, Depends(require_role(Role.owner))]


async def require_platform_admin(user: CurrentUserDep) -> User:
    if not user.is_platform_admin:
        # Admin routes are invisible to everyone else.
        raise AppError("NOT_FOUND", "Not found", 404)
    return user


AdminDep = Annotated[User, Depends(require_platform_admin)]
