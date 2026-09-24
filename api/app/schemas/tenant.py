from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal
from zoneinfo import available_timezones

from pydantic import EmailStr, Field, StringConstraints, field_validator

from app.models.user import Role
from app.schemas.common import LongText, Name, Schema, ShortText

FulfillmentMode = Literal["pickup", "delivery"]
Area = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
Phone = Annotated[str, StringConstraints(strip_whitespace=True, max_length=20)]


class TenantOut(Schema):
    id: uuid.UUID
    name: str
    slug: str
    description: str | None
    logo_url: str | None
    phone: str | None
    email: str | None
    address: str | None
    accepts_orders: bool
    fulfillment_modes: list[FulfillmentMode]
    delivery_areas: list[str]
    min_order_paise: int
    delivery_fee_paise: int
    hours_text: str | None
    timezone: str


class TenantPatch(Schema):
    name: Name | None = None
    description: LongText | None = None
    phone: Phone | None = None
    email: EmailStr | None = None
    address: ShortText | None = None
    accepts_orders: bool | None = None
    fulfillment_modes: list[FulfillmentMode] | None = Field(default=None, min_length=1)
    delivery_areas: list[Area] | None = Field(default=None, max_length=50)
    min_order_paise: int | None = Field(default=None, ge=0, le=10_000_000)
    delivery_fee_paise: int | None = Field(default=None, ge=0, le=1_000_000)
    hours_text: ShortText | None = None
    timezone: str | None = None

    @field_validator("fulfillment_modes")
    @classmethod
    def _dedupe_modes(cls, v: list[str] | None) -> list[str] | None:
        return sorted(set(v)) if v is not None else None

    @field_validator("delivery_areas")
    @classmethod
    def _dedupe_areas(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        seen: dict[str, str] = {}
        for area in v:
            seen.setdefault(area.lower(), area)
        return list(seen.values())

    @field_validator("timezone")
    @classmethod
    def _valid_tz(cls, v: str | None) -> str | None:
        if v is not None and v not in available_timezones():
            raise ValueError("Unknown timezone")
        return v


class MemberOut(Schema):
    membership_id: uuid.UUID
    user_id: uuid.UUID
    name: str
    email: str
    role: Role
    joined_at: datetime


class PendingInviteOut(Schema):
    id: uuid.UUID
    role: Role
    expires_at: datetime
    created_at: datetime


class TeamOut(Schema):
    members: list[MemberOut]
    pending_invites: list[PendingInviteOut]


class InviteCreateIn(Schema):
    role: Literal["staff"] = "staff"


class InviteCreatedOut(Schema):
    id: uuid.UUID
    url: str
    token: str
    role: Role
    expires_at: datetime
