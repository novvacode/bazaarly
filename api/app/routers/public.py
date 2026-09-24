"""Unauthenticated, rate-limited customer-facing routes (SPEC §9.1 "Public")."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from app.core.ratelimit import limit_by_ip
from app.deps import SessionDep
from app.schemas.order import (
    OrderCreatedOut,
    OrderCreateIn,
    PaymentParamsOut,
    PaymentVerifyIn,
    PublicOrderOut,
)
from app.schemas.public import StorefrontOut
from app.services import orders as order_service
from app.services import payments as payment_service
from app.services import public as public_service

router = APIRouter(prefix="/public", tags=["public"])


@router.get(
    "/b/{slug}",
    response_model=StorefrontOut,
    summary="Storefront: business info, categories and available items",
    dependencies=[Depends(limit_by_ip("storefront", 120))],
)
async def storefront(slug: str, session: SessionDep) -> StorefrontOut:
    return await public_service.get_storefront(session, slug)


@router.post(
    "/b/{slug}/orders",
    response_model=OrderCreatedOut,
    status_code=status.HTTP_201_CREATED,
    summary="Place an order (idempotent on idempotency_key)",
    responses={200: {"description": "Existing order for this idempotency key"}},
    dependencies=[Depends(limit_by_ip("place_order", 10))],
)
async def place_order(
    slug: str, data: OrderCreateIn, response: Response, session: SessionDep
) -> OrderCreatedOut:
    result, created = await order_service.create_order(session, slug, data)
    if not created:
        response.status_code = status.HTTP_200_OK
    return result


@router.get(
    "/orders/{public_token}",
    response_model=PublicOrderOut,
    summary="Order tracking: status, items, totals and timeline",
    dependencies=[Depends(limit_by_ip("track_order", 60))],
)
async def track_order(public_token: str, session: SessionDep) -> PublicOrderOut:
    return await order_service.public_order(session, public_token)


@router.get(
    "/orders/{public_token}/payment",
    response_model=PaymentParamsOut,
    summary="Razorpay Checkout parameters to (re)try paying an order awaiting payment",
    dependencies=[Depends(limit_by_ip("payment_params", 20))],
)
async def payment_params(public_token: str, session: SessionDep) -> PaymentParamsOut:
    return await payment_service.public_checkout_params(session, public_token)


@router.post(
    "/orders/{public_token}/payment/verify",
    response_model=PublicOrderOut,
    summary="Verify the Razorpay Checkout callback and mark the order paid",
    dependencies=[Depends(limit_by_ip("payment_verify", 20))],
)
async def verify_payment(
    public_token: str, data: PaymentVerifyIn, session: SessionDep
) -> PublicOrderOut:
    await payment_service.verify_checkout(
        session,
        public_token,
        data.razorpay_order_id,
        data.razorpay_payment_id,
        data.razorpay_signature,
    )
    return await order_service.public_order(session, public_token)
