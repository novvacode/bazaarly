from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import EmailStr, StringConstraints

from app.models.user import Role
from app.schemas.common import Name, Password, Schema

Slug = Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, max_length=40)]


class SignupIn(Schema):
    name: Name
    email: EmailStr
    password: Password
    business_name: Name
    slug: Slug


class LoginIn(Schema):
    email: EmailStr
    password: Password


class SwitchTenantIn(Schema):
    tenant_id: uuid.UUID


class InviteAcceptIn(Schema):
    """Anonymous accept: `email` + `password` (+ `name` for a new account).

    A logged-in user may send an empty body with their bearer token instead.
    """

    email: EmailStr | None = None
    password: Password | None = None
    name: Name | None = None


class UserOut(Schema):
    id: uuid.UUID
    email: str
    name: str
    is_platform_admin: bool


class TenantBrief(Schema):
    id: uuid.UUID
    name: str
    slug: str


class MembershipOut(Schema):
    tenant: TenantBrief
    role: Role


class ActiveTenantOut(TenantBrief):
    role: Role


class AuthOut(Schema):
    access_token: str
    token_type: str = "bearer"  # noqa: S105
    expires_in: int
    user: UserOut
    tenant: ActiveTenantOut | None


class MeOut(Schema):
    user: UserOut
    memberships: list[MembershipOut]
    active_tenant: ActiveTenantOut | None


class InvitePreviewOut(Schema):
    business_name: str
    role: Role
    expires_at: datetime
