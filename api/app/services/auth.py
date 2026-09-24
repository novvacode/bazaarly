"""Signup, login, refresh-token rotation with reuse detection, tenant switching (SPEC §8)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core import errors
from app.core.errors import AppError
from app.core.security import (
    create_access_token,
    hash_password,
    password_problem,
    random_token,
    sha256_hex,
    verify_password,
)
from app.core.slugs import slug_problem
from app.models.tenant import Tenant
from app.models.user import Role, User
from app.repositories import memberships as membership_repo
from app.repositories import tenants as tenant_repo
from app.repositories import tokens as token_repo
from app.repositories import users as user_repo
from app.schemas.auth import (
    ActiveTenantOut,
    AuthOut,
    MembershipOut,
    MeOut,
    SignupIn,
    TenantBrief,
    UserOut,
)

log = structlog.get_logger()


@dataclass(slots=True)
class AuthResult:
    """What a router needs to respond: the body and the new refresh token for the cookie."""

    body: AuthOut
    refresh_token: str


def check_password(password: str) -> None:
    problem = password_problem(password)
    if problem:
        raise AppError(
            errors.WEAK_PASSWORD, problem, 422, details={"fields": {"password": problem}}
        )


async def _issue(
    session: AsyncSession,
    user: User,
    tenant: Tenant | None,
    role: Role | None,
    *,
    family_id: uuid.UUID | None = None,
) -> tuple[AuthOut, str, uuid.UUID]:
    """Create an access token and a new refresh token row. Caller commits."""
    settings = get_settings()
    access, expires_in = create_access_token(user.id, tenant.id if tenant else None, role)
    refresh = random_token()
    row = await token_repo.create_refresh(
        session,
        user_id=user.id,
        family_id=family_id or uuid.uuid4(),
        token_hash=sha256_hex(refresh),
        tenant_id=tenant.id if tenant else None,
        expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_ttl_days),
    )
    active = (
        ActiveTenantOut(id=tenant.id, name=tenant.name, slug=tenant.slug, role=role)
        if tenant and role
        else None
    )
    body = AuthOut(
        access_token=access,
        expires_in=expires_in,
        user=UserOut.model_validate(user),
        tenant=active,
    )
    return body, refresh, row.id


async def _pick_tenant(
    session: AsyncSession, user_id: uuid.UUID, preferred: uuid.UUID | None
) -> tuple[Tenant | None, Role | None]:
    memberships = await membership_repo.list_for_user(session, user_id)
    for membership, tenant in memberships:
        if tenant.id == preferred:
            return tenant, membership.role
    if memberships:
        membership, tenant = memberships[0]
        return tenant, membership.role
    return None, None


async def signup(session: AsyncSession, data: SignupIn) -> AuthResult:
    check_password(data.password)
    if problem := slug_problem(data.slug):
        raise AppError(errors.SLUG_INVALID, problem, 422, details={"fields": {"slug": problem}})
    if await user_repo.email_exists(session, data.email):
        raise AppError(errors.EMAIL_TAKEN, "An account with this email already exists", 409)
    if await tenant_repo.slug_exists(session, data.slug):
        raise AppError(errors.SLUG_TAKEN, "This store link is already taken", 409)
    try:
        user = await user_repo.create(
            session, email=data.email, name=data.name, password_hash=hash_password(data.password)
        )
        tenant = await tenant_repo.create(
            session, name=data.business_name, slug=data.slug, email=data.email
        )
        await membership_repo.create(session, user_id=user.id, tenant_id=tenant.id, role=Role.owner)
        await user_repo.touch_login(session, user.id)
        body, refresh, _ = await _issue(session, user, tenant, Role.owner)
        await session.commit()
    except IntegrityError:
        # Lost a race on the unique email/slug with a concurrent signup.
        await session.rollback()
        raise AppError(errors.CONFLICT, "Email or store link already taken", 409) from None
    log.info("signup", user_id=str(user.id), tenant_id=str(tenant.id))
    return AuthResult(body, refresh)


async def login(session: AsyncSession, email: str, password: str) -> AuthResult:
    user = await user_repo.get_by_email(session, email)
    if not verify_password(user.password_hash if user else None, password) or user is None:
        raise AppError(errors.INVALID_CREDENTIALS, "Incorrect email or password", 401)
    tenant, role = await _pick_tenant(session, user.id, None)
    await user_repo.touch_login(session, user.id)
    body, refresh, _ = await _issue(session, user, tenant, role)
    await session.commit()
    return AuthResult(body, refresh)


async def refresh(session: AsyncSession, token: str | None) -> AuthResult:
    """Rotate the refresh token. Presenting a revoked token revokes its whole family."""
    if not token:
        raise AppError(errors.REFRESH_INVALID, "Not signed in", 401)
    row = await token_repo.get_refresh_for_update(session, sha256_hex(token))
    now = datetime.now(UTC)
    if row is None:
        raise AppError(errors.REFRESH_INVALID, "Session expired; please sign in", 401)
    if row.revoked_at is not None:
        await token_repo.revoke_family(session, row.family_id)
        await session.commit()
        log.warning("refresh_token_reuse", user_id=str(row.user_id), family=str(row.family_id))
        raise AppError(errors.REFRESH_REUSED, "Session expired; please sign in", 401)
    if row.expires_at <= now:
        raise AppError(errors.REFRESH_INVALID, "Session expired; please sign in", 401)

    user = await user_repo.get_by_id(session, row.user_id)
    if user is None:
        raise AppError(errors.REFRESH_INVALID, "Session expired; please sign in", 401)
    tenant, role = await _pick_tenant(session, user.id, row.tenant_id)
    body, new_refresh, new_id = await _issue(session, user, tenant, role, family_id=row.family_id)
    row.revoked_at = now
    row.replaced_by = new_id
    await session.commit()
    return AuthResult(body, new_refresh)


async def logout(session: AsyncSession, token: str | None) -> None:
    if not token:
        return
    row = await token_repo.get_refresh_for_update(session, sha256_hex(token))
    if row is not None and row.revoked_at is None:
        row.revoked_at = datetime.now(UTC)
    await session.commit()


async def switch_tenant(
    session: AsyncSession, user: User, tenant_id: uuid.UUID, refresh_token: str | None
) -> AuthOut:
    role = await membership_repo.get_role(session, user.id, tenant_id)
    if role is None:
        raise errors.not_found("Business")
    tenant = await tenant_repo.get_by_resolved_id(session, tenant_id)
    assert tenant is not None
    if refresh_token:
        row = await token_repo.get_refresh_for_update(session, sha256_hex(refresh_token))
        if row is not None and row.user_id == user.id and row.revoked_at is None:
            row.tenant_id = tenant_id
    await session.commit()
    access, expires_in = create_access_token(user.id, tenant.id, role)
    return AuthOut(
        access_token=access,
        expires_in=expires_in,
        user=UserOut.model_validate(user),
        tenant=ActiveTenantOut(id=tenant.id, name=tenant.name, slug=tenant.slug, role=role),
    )


async def me(session: AsyncSession, user: User, active_tenant_id: uuid.UUID | None) -> MeOut:
    memberships = await membership_repo.list_for_user(session, user.id)
    out = [MembershipOut(tenant=TenantBrief.model_validate(t), role=m.role) for m, t in memberships]
    active = next(
        (
            ActiveTenantOut(id=t.id, name=t.name, slug=t.slug, role=m.role)
            for m, t in memberships
            if t.id == active_tenant_id
        ),
        None,
    )
    return MeOut(user=UserOut.model_validate(user), memberships=out, active_tenant=active)


async def issue_for(session: AsyncSession, user: User, tenant: Tenant, role: Role) -> AuthResult:
    """Log a user straight into a tenant (used after accepting an invite). Caller commits."""
    body, refresh_token, _ = await _issue(session, user, tenant, role)
    return AuthResult(body, refresh_token)
