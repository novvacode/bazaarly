"""Assistant knowledge-base jobs (SPEC §12.6, §13.1)."""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy import delete, select

from app.models.assistant import KbChunk, SourceType
from app.queue.context import JobContext
from app.queue.registry import handler
from app.rag import indexer
from app.rag.embedder import get_embedder
from app.services import hooks

log = structlog.get_logger("jobs")


def _ids(payload: dict[str, Any]) -> tuple[uuid.UUID, SourceType, uuid.UUID]:
    return (
        uuid.UUID(payload["tenant_id"]),
        SourceType(payload["source_type"]),
        uuid.UUID(payload["source_id"]),
    )


@handler("rag.index_source", max_attempts=5, timeout=60)
async def index_source(ctx: JobContext, payload: dict[str, Any]) -> None:
    tenant_id, source_type, source_id = _ids(payload)
    async with ctx.sessionmaker() as session:
        outcome = await indexer.index_source(
            session, get_embedder(), tenant_id, source_type, source_id
        )
    log.info("rag_index", source_type=source_type.value, outcome=outcome)


@handler("rag.delete_source", max_attempts=5, timeout=30)
async def delete_source(ctx: JobContext, payload: dict[str, Any]) -> None:
    tenant_id, source_type, source_id = _ids(payload)
    async with ctx.sessionmaker() as session:
        await indexer.delete_source(session, tenant_id, source_type, source_id)


@handler("rag.reindex_tenant", max_attempts=3, timeout=60)
async def reindex_tenant(ctx: JobContext, payload: dict[str, Any]) -> None:
    """Enqueue an index job per source and drop chunks whose source no longer exists."""
    tenant_id = uuid.UUID(payload["tenant_id"])
    async with ctx.sessionmaker() as session:
        sources = await indexer.all_sources(session, tenant_id)
        live = {sid for _, sid in sources}
        stale = (
            (
                await session.execute(
                    select(KbChunk.id).where(
                        KbChunk.tenant_id == tenant_id, KbChunk.source_id.notin_(live)
                    )
                )
            )
            .scalars()
            .all()
        )
        if stale:
            await session.execute(delete(KbChunk).where(KbChunk.id.in_(stale)))
        for source_type, source_id in sources:
            await hooks.index(session, tenant_id, source_type, source_id)
        await session.commit()
    log.info("rag_reindex", tenant_id=str(tenant_id), sources=len(sources), removed=len(stale))
