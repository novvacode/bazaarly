"""Menu (categories, items) and FAQ management."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import errors
from app.core.errors import AppError
from app.core.tenancy import TenantContext
from app.models.catalog import FaqEntry, MenuCategory, MenuItem
from app.repositories import menu as repo
from app.schemas.menu import FaqIn, FaqPatch, ItemIn, ItemPatch, ReorderIn
from app.services import hooks, public

UNCATEGORIZED_KEY = "uncategorized"


async def _commit(session: AsyncSession, ctx: TenantContext) -> None:
    await session.commit()
    await public.invalidate(ctx.tenant_id)


# --- Categories --------------------------------------------------------------------------------


async def list_categories(session: AsyncSession, ctx: TenantContext) -> list[MenuCategory]:
    return await repo.list_categories(session, ctx.tenant_id)


async def _category(
    session: AsyncSession, ctx: TenantContext, category_id: uuid.UUID
) -> MenuCategory:
    category = await repo.get_category(session, ctx, category_id)
    if category is None:
        raise errors.not_found("Category")
    return category


async def create_category(session: AsyncSession, ctx: TenantContext, name: str) -> MenuCategory:
    category = await repo.create_category(session, ctx, name)
    await _commit(session, ctx)
    return category


async def _item_ids_in_category(
    session: AsyncSession, ctx: TenantContext, category_id: uuid.UUID
) -> list[uuid.UUID]:
    return [
        i.id for i in await repo.list_items(session, ctx.tenant_id) if i.category_id == category_id
    ]


async def rename_category(
    session: AsyncSession, ctx: TenantContext, category_id: uuid.UUID, name: str
) -> MenuCategory:
    category = await _category(session, ctx, category_id)
    category.name = name
    await hooks.category_changed(
        session, ctx.tenant_id, await _item_ids_in_category(session, ctx, category_id)
    )
    await _commit(session, ctx)
    return category


async def delete_category(
    session: AsyncSession, ctx: TenantContext, category_id: uuid.UUID
) -> None:
    category = await _category(session, ctx, category_id)
    item_ids = await _item_ids_in_category(session, ctx, category_id)
    await repo.delete_category(session, ctx, category)
    await hooks.category_changed(session, ctx.tenant_id, item_ids)
    await _commit(session, ctx)


# --- Items -------------------------------------------------------------------------------------


async def list_items(session: AsyncSession, ctx: TenantContext) -> list[MenuItem]:
    return await repo.list_items(session, ctx.tenant_id)


async def get_item(session: AsyncSession, ctx: TenantContext, item_id: uuid.UUID) -> MenuItem:
    item = await repo.get_item(session, ctx, item_id)
    if item is None:
        raise errors.not_found("Item")
    return item


async def create_item(session: AsyncSession, ctx: TenantContext, data: ItemIn) -> MenuItem:
    if data.category_id is not None:
        await _category(session, ctx, data.category_id)
    values = data.model_dump()
    values["position"] = await repo.next_item_position(session, ctx, data.category_id)
    item = await repo.create_item(session, ctx, values)
    await hooks.menu_item_changed(session, ctx.tenant_id, item.id)
    await _commit(session, ctx)
    return item


async def update_item(
    session: AsyncSession, ctx: TenantContext, item_id: uuid.UUID, patch: ItemPatch
) -> MenuItem:
    item = await get_item(session, ctx, item_id)
    values = patch.model_dump(exclude_unset=True)
    for key in ("name", "price_paise", "is_available", "is_veg", "tags"):
        if key in values and values[key] is None:
            raise AppError(
                errors.VALIDATION_ERROR,
                f"{key} cannot be null",
                422,
                details={"fields": {key: "cannot be null"}},
            )
    if "category_id" in values and values["category_id"] != item.category_id:
        if values["category_id"] is not None:
            await _category(session, ctx, values["category_id"])
        values["position"] = await repo.next_item_position(session, ctx, values["category_id"])
    for key, value in values.items():
        setattr(item, key, value)
    await hooks.menu_item_changed(session, ctx.tenant_id, item.id)
    await _commit(session, ctx)
    await session.refresh(item)
    return item


async def delete_item(session: AsyncSession, ctx: TenantContext, item_id: uuid.UUID) -> None:
    item = await get_item(session, ctx, item_id)
    repo.soft_delete_item(item)
    await hooks.menu_item_deleted(session, ctx.tenant_id, item.id)
    await _commit(session, ctx)


async def set_item_image(
    session: AsyncSession, ctx: TenantContext, item: MenuItem, url: str
) -> MenuItem:
    item.image_url = url
    await _commit(session, ctx)
    await session.refresh(item)
    return item


async def reorder(session: AsyncSession, ctx: TenantContext, data: ReorderIn) -> None:
    categories = {c.id for c in await repo.list_categories(session, ctx.tenant_id)}
    items = {i.id for i in await repo.list_items(session, ctx.tenant_id)}

    unknown_categories = [str(c) for c in data.categories if c not in categories]
    if len(set(data.categories)) != len(data.categories):
        raise AppError(errors.VALIDATION_ERROR, "Duplicate category ids", 422)

    parsed: dict[uuid.UUID | None, list[uuid.UUID]] = {}
    for key, ids in data.items.items():
        if key == UNCATEGORIZED_KEY:
            parsed[None] = ids
            continue
        try:
            cid = uuid.UUID(key)
        except ValueError:
            raise AppError(errors.VALIDATION_ERROR, f"Invalid category key {key!r}", 422) from None
        if cid not in categories:
            unknown_categories.append(key)
        parsed[cid] = ids
    all_item_ids = [i for ids in parsed.values() for i in ids]
    unknown_items = [str(i) for i in all_item_ids if i not in items]
    if unknown_categories or unknown_items:
        # Same response as for any other resource another tenant owns.
        raise errors.not_found("Category or item")
    if len(set(all_item_ids)) != len(all_item_ids):
        raise AppError(errors.VALIDATION_ERROR, "An item appears in more than one place", 422)

    if data.categories:
        await repo.set_category_positions(session, ctx, data.categories)
    for category_id, ids in parsed.items():
        await repo.set_item_positions(session, ctx, category_id, ids)
    for item_id in all_item_ids:
        await hooks.menu_item_changed(session, ctx.tenant_id, item_id)
    await _commit(session, ctx)


# --- FAQ ---------------------------------------------------------------------------------------


async def list_faq(session: AsyncSession, ctx: TenantContext) -> list[FaqEntry]:
    return await repo.list_faq(session, ctx.tenant_id)


async def _faq(session: AsyncSession, ctx: TenantContext, faq_id: uuid.UUID) -> FaqEntry:
    entry = await repo.get_faq(session, ctx, faq_id)
    if entry is None:
        raise errors.not_found("FAQ")
    return entry


async def create_faq(session: AsyncSession, ctx: TenantContext, data: FaqIn) -> FaqEntry:
    entry = await repo.create_faq(session, ctx, data.question, data.answer)
    await hooks.faq_changed(session, ctx.tenant_id, entry.id)
    await session.commit()
    return entry


async def update_faq(
    session: AsyncSession, ctx: TenantContext, faq_id: uuid.UUID, patch: FaqPatch
) -> FaqEntry:
    entry = await _faq(session, ctx, faq_id)
    for key, value in patch.model_dump(exclude_unset=True).items():
        if value is None:
            raise AppError(errors.VALIDATION_ERROR, f"{key} cannot be null", 422)
        setattr(entry, key, value)
    await hooks.faq_changed(session, ctx.tenant_id, entry.id)
    await session.commit()
    await session.refresh(entry)
    return entry


async def delete_faq(session: AsyncSession, ctx: TenantContext, faq_id: uuid.UUID) -> None:
    entry = await _faq(session, ctx, faq_id)
    await session.delete(entry)
    await hooks.faq_deleted(session, ctx.tenant_id, faq_id)
    await session.commit()


async def reorder_faq(session: AsyncSession, ctx: TenantContext, ids: list[uuid.UUID]) -> None:
    existing = {e.id for e in await repo.list_faq(session, ctx.tenant_id)}
    if any(i not in existing for i in ids):
        raise errors.not_found("FAQ")
    if len(set(ids)) != len(ids):
        raise AppError(errors.VALIDATION_ERROR, "Duplicate ids", 422)
    await repo.set_faq_positions(session, ctx, ids)
    await session.commit()
