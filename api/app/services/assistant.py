"""Owner-side assistant management: logs, reindex, log → FAQ draft (SPEC §9.1, §13.5)."""

from __future__ import annotations

import uuid

from sqlalchemy import literal, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import errors
from app.core.tenancy import TenantContext
from app.models.assistant import AssistantLog
from app.schemas.assistant import AssistantLogListOut, AssistantLogOut, FaqDraftOut
from app.services import hooks
from app.services.orders import decode_cursor


def _cursor(entry: AssistantLog) -> str:
    import base64

    raw = f"{entry.created_at.isoformat()}|{entry.id}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


async def list_logs(
    session: AsyncSession,
    ctx: TenantContext,
    *,
    answered: bool | None,
    limit: int,
    cursor: str | None,
) -> AssistantLogListOut:
    stmt = select(AssistantLog).where(AssistantLog.tenant_id == ctx.tenant_id)
    if answered is not None:
        stmt = stmt.where(AssistantLog.answered.is_(answered))
    if cursor:
        ts, lid = decode_cursor(cursor)
        stmt = stmt.where(
            tuple_(AssistantLog.created_at, AssistantLog.id) < tuple_(literal(ts), literal(lid))
        )
    rows = list(
        (
            await session.execute(
                stmt.order_by(AssistantLog.created_at.desc(), AssistantLog.id.desc()).limit(
                    limit + 1
                )
            )
        ).scalars()
    )
    page = rows[:limit]
    return AssistantLogListOut(
        items=[AssistantLogOut.model_validate(r) for r in page],
        next_cursor=_cursor(page[-1]) if len(rows) > limit and page else None,
    )


async def reindex(session: AsyncSession, ctx: TenantContext) -> None:
    await hooks.reindex_tenant(session, ctx.tenant_id)
    await session.commit()


async def faq_draft(session: AsyncSession, ctx: TenantContext, log_id: uuid.UUID) -> FaqDraftOut:
    entry = (
        await session.execute(
            select(AssistantLog).where(
                AssistantLog.id == log_id, AssistantLog.tenant_id == ctx.tenant_id
            )
        )
    ).scalar_one_or_none()
    if entry is None:
        raise errors.not_found("Log entry")
    question = entry.question.strip()
    if question and question[-1] not in "?.!":
        question += "?"
    return FaqDraftOut(question=question[:300], answer="")
