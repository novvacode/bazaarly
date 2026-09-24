from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.deps import OwnerDep, SessionDep
from app.schemas.assistant import AssistantLogListOut, FaqDraftOut
from app.services import assistant as assistant_service

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.get("/logs", response_model=AssistantLogListOut, summary="Assistant conversations")
async def logs(
    ctx: OwnerDep,
    session: SessionDep,
    answered: bool | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
) -> AssistantLogListOut:
    return await assistant_service.list_logs(
        session, ctx, answered=answered, limit=limit, cursor=cursor
    )


@router.post(
    "/reindex",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Rebuild the assistant's knowledge for this business (runs in the background)",
)
async def reindex(ctx: OwnerDep, session: SessionDep) -> Response:
    await assistant_service.reindex(session, ctx)
    return Response(status_code=status.HTTP_202_ACCEPTED)


@router.post(
    "/logs/{log_id}/to-faq",
    response_model=FaqDraftOut,
    summary="Prefill an FAQ draft from a customer question",
)
async def to_faq(log_id: uuid.UUID, ctx: OwnerDep, session: SessionDep) -> FaqDraftOut:
    return await assistant_service.faq_draft(session, ctx, log_id)
