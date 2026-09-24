from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Response, UploadFile, status

from app.deps import OwnerDep, SessionDep, TenantDep
from app.integrations.storage import Storage, get_storage
from app.schemas.menu import (
    CategoryIn,
    CategoryOut,
    FaqIn,
    FaqOut,
    FaqPatch,
    FaqReorderIn,
    ItemIn,
    ItemOut,
    ItemPatch,
    ReorderIn,
)
from app.services import menu as menu_service
from app.services.images import store_image

router = APIRouter(tags=["menu"])
StorageDep = Annotated[Storage, Depends(get_storage)]
NO_CONTENT = status.HTTP_204_NO_CONTENT


# --- Categories --------------------------------------------------------------------------------


@router.get("/menu/categories", response_model=list[CategoryOut], summary="List categories")
async def list_categories(ctx: TenantDep, session: SessionDep) -> list[CategoryOut]:
    return [CategoryOut.model_validate(c) for c in await menu_service.list_categories(session, ctx)]


@router.post(
    "/menu/categories",
    response_model=CategoryOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a category",
)
async def create_category(data: CategoryIn, ctx: OwnerDep, session: SessionDep) -> CategoryOut:
    return CategoryOut.model_validate(await menu_service.create_category(session, ctx, data.name))


@router.patch(
    "/menu/categories/{category_id}", response_model=CategoryOut, summary="Rename a category"
)
async def rename_category(
    category_id: uuid.UUID, data: CategoryIn, ctx: OwnerDep, session: SessionDep
) -> CategoryOut:
    category = await menu_service.rename_category(session, ctx, category_id, data.name)
    return CategoryOut.model_validate(category)


@router.delete(
    "/menu/categories/{category_id}",
    status_code=NO_CONTENT,
    summary="Delete a category (its items become uncategorized)",
)
async def delete_category(category_id: uuid.UUID, ctx: OwnerDep, session: SessionDep) -> Response:
    await menu_service.delete_category(session, ctx, category_id)
    return Response(status_code=NO_CONTENT)


# --- Items -------------------------------------------------------------------------------------


@router.get("/menu/items", response_model=list[ItemOut], summary="List menu items")
async def list_items(ctx: TenantDep, session: SessionDep) -> list[ItemOut]:
    return [ItemOut.model_validate(i) for i in await menu_service.list_items(session, ctx)]


@router.post(
    "/menu/items",
    response_model=ItemOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a menu item",
)
async def create_item(data: ItemIn, ctx: OwnerDep, session: SessionDep) -> ItemOut:
    return ItemOut.model_validate(await menu_service.create_item(session, ctx, data))


@router.patch("/menu/items/{item_id}", response_model=ItemOut, summary="Update a menu item")
async def update_item(
    item_id: uuid.UUID, data: ItemPatch, ctx: OwnerDep, session: SessionDep
) -> ItemOut:
    return ItemOut.model_validate(await menu_service.update_item(session, ctx, item_id, data))


@router.delete(
    "/menu/items/{item_id}", status_code=NO_CONTENT, summary="Delete a menu item (soft delete)"
)
async def delete_item(item_id: uuid.UUID, ctx: OwnerDep, session: SessionDep) -> Response:
    await menu_service.delete_item(session, ctx, item_id)
    return Response(status_code=NO_CONTENT)


@router.post("/menu/items/{item_id}/image", response_model=ItemOut, summary="Upload item photo")
async def upload_item_image(
    item_id: uuid.UUID,
    ctx: OwnerDep,
    session: SessionDep,
    storage: StorageDep,
    file: Annotated[UploadFile, File(description="JPEG, PNG or WebP, max 2 MB")],
) -> ItemOut:
    item = await menu_service.get_item(session, ctx, item_id)
    url = await store_image(storage, file, tenant_id=ctx.tenant_id, kind="items")
    return ItemOut.model_validate(await menu_service.set_item_image(session, ctx, item, url))


@router.post("/menu/reorder", status_code=NO_CONTENT, summary="Reorder categories and items")
async def reorder(data: ReorderIn, ctx: OwnerDep, session: SessionDep) -> Response:
    await menu_service.reorder(session, ctx, data)
    return Response(status_code=NO_CONTENT)


# --- FAQ ---------------------------------------------------------------------------------------


@router.get("/faq", response_model=list[FaqOut], summary="List FAQ entries", tags=["faq"])
async def list_faq(ctx: OwnerDep, session: SessionDep) -> list[FaqOut]:
    return [FaqOut.model_validate(e) for e in await menu_service.list_faq(session, ctx)]


@router.post(
    "/faq",
    response_model=FaqOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create an FAQ entry",
    tags=["faq"],
)
async def create_faq(data: FaqIn, ctx: OwnerDep, session: SessionDep) -> FaqOut:
    return FaqOut.model_validate(await menu_service.create_faq(session, ctx, data))


@router.patch("/faq/{faq_id}", response_model=FaqOut, summary="Update an FAQ entry", tags=["faq"])
async def update_faq(
    faq_id: uuid.UUID, data: FaqPatch, ctx: OwnerDep, session: SessionDep
) -> FaqOut:
    return FaqOut.model_validate(await menu_service.update_faq(session, ctx, faq_id, data))


@router.delete("/faq/{faq_id}", status_code=NO_CONTENT, summary="Delete an FAQ entry", tags=["faq"])
async def delete_faq(faq_id: uuid.UUID, ctx: OwnerDep, session: SessionDep) -> Response:
    await menu_service.delete_faq(session, ctx, faq_id)
    return Response(status_code=NO_CONTENT)


@router.post("/faq/reorder", status_code=NO_CONTENT, summary="Reorder FAQ", tags=["faq"])
async def reorder_faq(data: FaqReorderIn, ctx: OwnerDep, session: SessionDep) -> Response:
    await menu_service.reorder_faq(session, ctx, data.ids)
    return Response(status_code=NO_CONTENT)
