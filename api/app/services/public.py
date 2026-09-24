"""Public storefront data with a short Redis cache (SPEC §7.3, §9.1)."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import errors
from app.models.tenant import Tenant
from app.redis import get_redis
from app.repositories import menu as menu_repo
from app.repositories import tenants as tenant_repo
from app.schemas.public import PublicBusiness, PublicCategory, PublicItem, StorefrontOut

CACHE_TTL_S = 60
UNCATEGORIZED = "Other"


def _storefront_key(tenant_id: uuid.UUID) -> str:
    return f"bz:storefront:{tenant_id}"


def _slug_key(slug: str) -> str:
    return f"bz:slug:{slug}"


async def resolve_tenant_id(session: AsyncSession, slug: str) -> uuid.UUID:
    """Slug → tenant id, cached for 60 s. Unknown slugs raise 404."""
    slug = slug.lower()
    redis = get_redis()
    cached = await redis.get(_slug_key(slug))
    if cached:
        return uuid.UUID(str(cached))
    tenant = await tenant_repo.get_by_slug(session, slug)
    if tenant is None:
        raise errors.not_found("Store")
    await redis.set(_slug_key(slug), str(tenant.id), ex=CACHE_TTL_S)
    return tenant.id


async def resolve_tenant(session: AsyncSession, slug: str) -> Tenant:
    tenant_id = await resolve_tenant_id(session, slug)
    tenant = await tenant_repo.get_by_resolved_id(session, tenant_id)
    if tenant is None:
        raise errors.not_found("Store")
    return tenant


async def build_storefront(session: AsyncSession, tenant: Tenant) -> StorefrontOut:
    categories = await menu_repo.list_categories(session, tenant.id)
    items = await menu_repo.list_items(session, tenant.id, available_only=True)
    by_category: dict[uuid.UUID | None, list[PublicItem]] = {}
    for item in items:
        by_category.setdefault(item.category_id, []).append(PublicItem.model_validate(item))
    out = [
        PublicCategory(id=c.id, name=c.name, items=by_category[c.id])
        for c in categories
        if by_category.get(c.id)
    ]
    if by_category.get(None):
        out.append(PublicCategory(id=None, name=UNCATEGORIZED, items=by_category[None]))
    return StorefrontOut(business=PublicBusiness.model_validate(tenant), categories=out)


async def get_storefront(session: AsyncSession, slug: str) -> StorefrontOut:
    tenant_id = await resolve_tenant_id(session, slug)
    redis = get_redis()
    cached = await redis.get(_storefront_key(tenant_id))
    if cached:
        return StorefrontOut.model_validate_json(cached)
    tenant = await tenant_repo.get_by_resolved_id(session, tenant_id)
    if tenant is None:
        raise errors.not_found("Store")
    storefront = await build_storefront(session, tenant)
    await redis.set(_storefront_key(tenant_id), storefront.model_dump_json(), ex=CACHE_TTL_S)
    return storefront


async def invalidate(tenant_id: uuid.UUID) -> None:
    """Call after committing any change to a tenant's settings, menu or availability."""
    await get_redis().delete(_storefront_key(tenant_id))
