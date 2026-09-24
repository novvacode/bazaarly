"""Menu categories, items and FAQ entries. Every query is filtered by tenant."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import TenantContext
from app.models.catalog import FaqEntry, MenuCategory, MenuItem

# --- Categories --------------------------------------------------------------------------------


async def list_categories(session: AsyncSession, tenant_id: uuid.UUID) -> list[MenuCategory]:
    result = await session.execute(
        select(MenuCategory)
        .where(MenuCategory.tenant_id == tenant_id)
        .order_by(MenuCategory.position, MenuCategory.created_at)
    )
    return list(result.scalars())


async def get_category(
    session: AsyncSession, ctx: TenantContext, category_id: uuid.UUID
) -> MenuCategory | None:
    result = await session.execute(
        select(MenuCategory).where(
            MenuCategory.id == category_id, MenuCategory.tenant_id == ctx.tenant_id
        )
    )
    return result.scalar_one_or_none()


async def next_category_position(session: AsyncSession, ctx: TenantContext) -> int:
    result = await session.execute(
        select(func.coalesce(func.max(MenuCategory.position), -1)).where(
            MenuCategory.tenant_id == ctx.tenant_id
        )
    )
    return int(result.scalar_one()) + 1


async def create_category(session: AsyncSession, ctx: TenantContext, name: str) -> MenuCategory:
    category = MenuCategory(
        tenant_id=ctx.tenant_id, name=name, position=await next_category_position(session, ctx)
    )
    session.add(category)
    await session.flush()
    return category


async def delete_category(
    session: AsyncSession, ctx: TenantContext, category: MenuCategory
) -> None:
    # Items fall back to "uncategorized" (the FK is ON DELETE SET NULL; done explicitly here so
    # the ORM identity map stays consistent).
    await session.execute(
        update(MenuItem)
        .where(MenuItem.tenant_id == ctx.tenant_id, MenuItem.category_id == category.id)
        .values(category_id=None)
    )
    await session.delete(category)


# --- Items -------------------------------------------------------------------------------------


async def list_items(
    session: AsyncSession, tenant_id: uuid.UUID, *, available_only: bool = False
) -> list[MenuItem]:
    stmt = select(MenuItem).where(MenuItem.tenant_id == tenant_id, MenuItem.deleted_at.is_(None))
    if available_only:
        stmt = stmt.where(MenuItem.is_available.is_(True))
    result = await session.execute(stmt.order_by(MenuItem.position, MenuItem.created_at))
    return list(result.scalars())


async def get_item(
    session: AsyncSession, ctx: TenantContext, item_id: uuid.UUID, *, include_deleted: bool = False
) -> MenuItem | None:
    stmt = select(MenuItem).where(MenuItem.id == item_id, MenuItem.tenant_id == ctx.tenant_id)
    if not include_deleted:
        stmt = stmt.where(MenuItem.deleted_at.is_(None))
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_items_by_ids(
    session: AsyncSession, tenant_id: uuid.UUID, item_ids: Sequence[uuid.UUID]
) -> list[MenuItem]:
    """Items of one tenant by id, including soft-deleted ones (callers decide)."""
    if not item_ids:
        return []
    result = await session.execute(
        select(MenuItem).where(MenuItem.tenant_id == tenant_id, MenuItem.id.in_(item_ids))
    )
    return list(result.scalars())


async def next_item_position(
    session: AsyncSession, ctx: TenantContext, category_id: uuid.UUID | None
) -> int:
    cond = (
        MenuItem.category_id.is_(None)
        if category_id is None
        else MenuItem.category_id == category_id
    )
    result = await session.execute(
        select(func.coalesce(func.max(MenuItem.position), -1)).where(
            MenuItem.tenant_id == ctx.tenant_id, cond, MenuItem.deleted_at.is_(None)
        )
    )
    return int(result.scalar_one()) + 1


async def create_item(
    session: AsyncSession, ctx: TenantContext, values: dict[str, Any]
) -> MenuItem:
    item = MenuItem(tenant_id=ctx.tenant_id, **values)
    session.add(item)
    await session.flush()
    return item


def soft_delete_item(item: MenuItem) -> None:
    item.deleted_at = datetime.now(UTC)


async def set_category_positions(
    session: AsyncSession, ctx: TenantContext, ordered_ids: Sequence[uuid.UUID]
) -> None:
    for position, category_id in enumerate(ordered_ids):
        await session.execute(
            update(MenuCategory)
            .where(MenuCategory.id == category_id, MenuCategory.tenant_id == ctx.tenant_id)
            .values(position=position)
        )


async def set_item_positions(
    session: AsyncSession,
    ctx: TenantContext,
    category_id: uuid.UUID | None,
    ordered_ids: Sequence[uuid.UUID],
) -> None:
    for position, item_id in enumerate(ordered_ids):
        await session.execute(
            update(MenuItem)
            .where(MenuItem.id == item_id, MenuItem.tenant_id == ctx.tenant_id)
            .values(position=position, category_id=category_id)
        )


# --- FAQ ---------------------------------------------------------------------------------------


async def list_faq(session: AsyncSession, tenant_id: uuid.UUID) -> list[FaqEntry]:
    result = await session.execute(
        select(FaqEntry)
        .where(FaqEntry.tenant_id == tenant_id)
        .order_by(FaqEntry.position, FaqEntry.created_at)
    )
    return list(result.scalars())


async def get_faq(session: AsyncSession, ctx: TenantContext, faq_id: uuid.UUID) -> FaqEntry | None:
    result = await session.execute(
        select(FaqEntry).where(FaqEntry.id == faq_id, FaqEntry.tenant_id == ctx.tenant_id)
    )
    return result.scalar_one_or_none()


async def create_faq(
    session: AsyncSession, ctx: TenantContext, question: str, answer: str
) -> FaqEntry:
    result = await session.execute(
        select(func.coalesce(func.max(FaqEntry.position), -1)).where(
            FaqEntry.tenant_id == ctx.tenant_id
        )
    )
    entry = FaqEntry(
        tenant_id=ctx.tenant_id,
        question=question,
        answer=answer,
        position=int(result.scalar_one()) + 1,
    )
    session.add(entry)
    await session.flush()
    return entry


async def set_faq_positions(
    session: AsyncSession, ctx: TenantContext, ordered_ids: Sequence[uuid.UUID]
) -> None:
    for position, faq_id in enumerate(ordered_ids):
        await session.execute(
            update(FaqEntry)
            .where(FaqEntry.id == faq_id, FaqEntry.tenant_id == ctx.tenant_id)
            .values(position=position)
        )
