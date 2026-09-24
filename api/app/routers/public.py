"""Unauthenticated, rate-limited customer-facing routes (SPEC §9.1 "Public")."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.ratelimit import limit_by_ip
from app.deps import SessionDep
from app.schemas.public import StorefrontOut
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
