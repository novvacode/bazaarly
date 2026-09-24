from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Response, UploadFile, status

from app.deps import OwnerDep, SessionDep
from app.integrations.storage import Storage, get_storage
from app.models.user import Role
from app.schemas.tenant import InviteCreatedOut, InviteCreateIn, TeamOut, TenantOut, TenantPatch
from app.services import tenants as tenant_service
from app.services.images import store_image

router = APIRouter(tags=["tenant"])
StorageDep = Annotated[Storage, Depends(get_storage)]


@router.get("/tenant", response_model=TenantOut, summary="Business settings")
async def get_tenant(ctx: OwnerDep, session: SessionDep) -> TenantOut:
    return TenantOut.model_validate(await tenant_service.get_tenant(session, ctx))


@router.patch("/tenant", response_model=TenantOut, summary="Update business settings")
async def patch_tenant(data: TenantPatch, ctx: OwnerDep, session: SessionDep) -> TenantOut:
    return TenantOut.model_validate(await tenant_service.update_tenant(session, ctx, data))


@router.post("/tenant/logo", response_model=TenantOut, summary="Upload the business logo")
async def upload_logo(
    ctx: OwnerDep,
    session: SessionDep,
    storage: StorageDep,
    file: Annotated[UploadFile, File(description="JPEG, PNG or WebP, max 2 MB")],
) -> TenantOut:
    url = await store_image(storage, file, tenant_id=ctx.tenant_id, kind="logo")
    return TenantOut.model_validate(await tenant_service.set_logo(session, ctx, url))


@router.get("/team", response_model=TeamOut, summary="Members and pending invites")
async def get_team(ctx: OwnerDep, session: SessionDep) -> TeamOut:
    return await tenant_service.get_team(session, ctx)


@router.post(
    "/team/invites",
    response_model=InviteCreatedOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a staff invite link to share",
)
async def create_invite(
    ctx: OwnerDep, session: SessionDep, data: InviteCreateIn | None = None
) -> InviteCreatedOut:
    return await tenant_service.create_invite(session, ctx, Role((data or InviteCreateIn()).role))


@router.delete(
    "/team/memberships/{membership_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a member (the last owner cannot be removed)",
)
async def remove_member(membership_id: uuid.UUID, ctx: OwnerDep, session: SessionDep) -> Response:
    await tenant_service.remove_member(session, ctx, membership_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
