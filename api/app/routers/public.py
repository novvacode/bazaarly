"""Unauthenticated, rate-limited customer-facing routes (SPEC §9.1 "Public")."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from app.core.ratelimit import limit_by_ip
from app.deps import SessionDep
from app.schemas.order import OrderCreatedOut, OrderCreateIn, PublicOrderOut
from app.schemas.public import StorefrontOut
from app.services import orders as order_service
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
