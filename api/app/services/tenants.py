"""Tenant settings and team management."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core import errors
from app.core.errors import AppError
from app.core.phone import normalize_phone
from app.core.security import hash_password, random_token, sha256_hex, verify_password
from app.core.tenancy import TenantContext
from app.models.auth import Invite
from app.models.tenant import Tenant
from app.models.user import Role, User
from app.repositories import memberships as membership_repo
from app.repositories import tenants as tenant_repo
from app.repositories import tokens as token_repo
from app.repositories import users as user_repo
from app.schemas.auth import InviteAcceptIn, InvitePreviewOut
from app.schemas.tenant import (
    InviteCreatedOut,
    MemberOut,
    PendingInviteOut,
    TeamOut,
    TenantPatch,
)
from app.services import auth as auth_service
from app.services import membership_cache
from app.services.hooks import on_tenant_changed

INVITE_TTL = timedelta(days=7)


async def get_tenant(session: AsyncSession, ctx: TenantContext) -> Tenant:
    tenant = await tenant_repo.get(session, ctx)
    if tenant is None:
        raise errors.not_found("Business")
    return tenant


async def update_tenant(session: AsyncSession, ctx: TenantContext, patch: TenantPatch) -> Tenant:
    values = patch.model_dump(exclude_unset=True)
    for key in (
        "name",
        "fulfillment_modes",
        "accepts_orders",
        "min_order_paise",
        "delivery_fee_paise",
        "timezone",
        "delivery_areas",
    ):
        if key in values and values[key] is None:
            raise AppError(
                errors.VALIDATION_ERROR,
                f"{key} cannot be null",
                422,
                details={"fields": {key: "cannot be null"}},
            )
    if values.get("phone"):
        normalized = normalize_phone(values["phone"])
        if normalized is None:
            raise AppError(
                errors.PHONE_INVALID,
                "Enter a valid phone number",
                422,
                details={"fields": {"phone": "invalid phone number"}},
            )
        values["phone"] = normalized
    await tenant_repo.update_fields(session, ctx, values)
    await on_tenant_changed(session, ctx.tenant_id)
    await session.commit()
    tenant = await get_tenant(session, ctx)
    await session.refresh(tenant)
    return tenant


async def set_logo(session: AsyncSession, ctx: TenantContext, url: str) -> Tenant:
    await tenant_repo.update_fields(session, ctx, {"logo_url": url})
    await on_tenant_changed(session, ctx.tenant_id)
    await session.commit()
    tenant = await get_tenant(session, ctx)
    await session.refresh(tenant)
    return tenant


# --- Team ------------------------------------------------------------------------------------


async def get_team(session: AsyncSession, ctx: TenantContext) -> TeamOut:
    members = await membership_repo.list_for_tenant(session, ctx)
    invites = await token_repo.list_pending_invites(session, ctx)
    return TeamOut(
        members=[
            MemberOut(
                membership_id=m.id,
                user_id=u.id,
                name=u.name,
                email=u.email,
                role=m.role,
                joined_at=m.created_at,
            )
            for m, u in members
        ],
        pending_invites=[PendingInviteOut.model_validate(i) for i in invites],
    )


async def create_invite(session: AsyncSession, ctx: TenantContext, role: Role) -> InviteCreatedOut:
    token = random_token()
    invite = await token_repo.create_invite(
        session,
        ctx,
        role=role,
        token_hash=sha256_hex(token),
        expires_at=datetime.now(UTC) + INVITE_TTL,
    )
    await session.commit()
    base = get_settings().app_base_url.rstrip("/")
    return InviteCreatedOut(
        id=invite.id,
        url=f"{base}/invite/{token}",
        token=token,
        role=invite.role,
        expires_at=invite.expires_at,
    )


async def remove_member(
    session: AsyncSession, ctx: TenantContext, membership_id: uuid.UUID
) -> None:
    membership = await membership_repo.get(session, ctx, membership_id)
    if membership is None:
        raise errors.not_found("Member")
    if membership.role == Role.owner:
        owners = await membership_repo.count_owners_for_update(session, ctx)
        if owners <= 1:
            raise AppError(errors.LAST_OWNER, "A business needs at least one owner", 409)
    await membership_repo.delete_one(session, ctx, membership_id)
    await session.commit()
    await membership_cache.invalidate(membership.user_id, ctx.tenant_id)


async def _valid_invite(session: AsyncSession, token: str, *, for_update: bool = False) -> Invite:
    invite = await token_repo.get_invite_by_hash(session, sha256_hex(token), for_update=for_update)
    if invite is None or invite.accepted_at is not None or invite.expires_at <= datetime.now(UTC):
        raise AppError(errors.INVITE_INVALID, "This invite link is invalid or has expired", 404)
    return invite


async def preview_invite(session: AsyncSession, token: str) -> InvitePreviewOut:
    invite = await _valid_invite(session, token)
    tenant = await tenant_repo.get_by_resolved_id(session, invite.tenant_id)
    assert tenant is not None
    return InvitePreviewOut(
        business_name=tenant.name, role=invite.role, expires_at=invite.expires_at
    )


async def accept_invite(
    session: AsyncSession, token: str, data: InviteAcceptIn, current_user: User | None
) -> auth_service.AuthResult:
    invite = await _valid_invite(session, token, for_update=True)

    user: User | None = current_user
    if user is None:
        if not data.email or not data.password:
            raise AppError(
                errors.VALIDATION_ERROR,
                "Email and password are required",
                422,
                details={"fields": {"email": "required", "password": "required"}},
            )
        user = await user_repo.get_by_email(session, data.email)
        if user is not None:
            if not verify_password(user.password_hash, data.password):
                raise AppError(errors.INVALID_CREDENTIALS, "Incorrect email or password", 401)
        else:
            if not data.name:
                raise AppError(
                    errors.VALIDATION_ERROR,
                    "Your name is required",
                    422,
                    details={"fields": {"name": "required"}},
                )
            auth_service.check_password(data.password)
            user = await user_repo.create(
                session,
                email=data.email,
                name=data.name,
                password_hash=hash_password(data.password),
            )

    if await membership_repo.get_role(session, user.id, invite.tenant_id) is not None:
        raise AppError(errors.ALREADY_MEMBER, "You're already a member of this business", 409)
    try:
        await membership_repo.create(
            session, user_id=user.id, tenant_id=invite.tenant_id, role=invite.role
        )
    except IntegrityError:
        await session.rollback()
        raise AppError(
            errors.ALREADY_MEMBER, "You're already a member of this business", 409
        ) from None
    invite.accepted_at = datetime.now(UTC)
    tenant = await tenant_repo.get_by_resolved_id(session, invite.tenant_id)
    assert tenant is not None
    result = await auth_service.issue_for(session, user, tenant, invite.role)
    await session.commit()
    await membership_cache.invalidate(user.id, invite.tenant_id)
    return result
