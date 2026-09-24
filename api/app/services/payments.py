"""Online payments (Razorpay). Phase 3 ships cash on delivery only; Phase 5 fills this in."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import errors
from app.core.errors import AppError
from app.models.order import Order
from app.models.tenant import Tenant
from app.schemas.order import PaymentParamsOut


def ensure_online_enabled() -> None:
    raise AppError(
        errors.VALIDATION_ERROR,
        "Online payment isn't available yet; please choose cash",
        422,
        details={"fields": {"payment_method": "online payment unavailable"}},
    )


async def checkout_params(session: AsyncSession, order: Order) -> PaymentParamsOut | None:
    return None


async def schedule_expiry(session: AsyncSession, order: Order) -> None:
    return None


async def start_online_payment(session: AsyncSession, order: Order, tenant: Tenant) -> None:
    return None
