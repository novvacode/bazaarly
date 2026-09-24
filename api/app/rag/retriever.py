"""Tenant-scoped vector retrieval (SPEC §13.3). Every query filters by tenant_id."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assistant import KbChunk, SourceType
from app.rag.embedder import Embedder

TOP_K = 6


@dataclass(frozen=True, slots=True)
class Retrieved:
    id: uuid.UUID
    source_type: SourceType
    title: str
    content: str
    score: float  # cosine similarity in [-1, 1]


async def retrieve(
    session: AsyncSession,
    embedder: Embedder,
    tenant_id: uuid.UUID,
    query: str,
    *,
    min_similarity: float,
    k: int = TOP_K,
) -> list[Retrieved]:
    """Top-k chunks above the similarity threshold, plus the tenant's business-info chunk."""
    qvec = await embedder.embed_query(query)
    distance = KbChunk.embedding.cosine_distance(qvec)
    rows = await session.execute(
        select(KbChunk, (1 - distance).label("score"))
        .where(KbChunk.tenant_id == tenant_id)
        .order_by(distance)
        .limit(k)
    )
    hits = [
        Retrieved(c.id, c.source_type, c.title, c.content, float(score))
        for c, score in rows.tuples()
        if float(score) >= min_similarity
    ]
    if not any(h.source_type == SourceType.business_info for h in hits):
        info = (
            await session.execute(
                select(KbChunk).where(
                    KbChunk.tenant_id == tenant_id,
                    KbChunk.source_type == SourceType.business_info,
                )
            )
        ).scalar_one_or_none()
        if info is not None:
            hits.append(Retrieved(info.id, info.source_type, info.title, info.content, 0.0))
    return hits
