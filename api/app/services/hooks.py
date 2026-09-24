"""In-transaction reactions to catalog changes.

Services call these inside the transaction that made the change, so the assistant re-indexing
jobs they enqueue through the outbox commit atomically with it (SPEC §13.1). Storefront cache
invalidation happens separately, after commit (`services.public.invalidate`).
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assistant import SourceType
from app.queue.producer import enqueue_in_tx


async def index(
    session: AsyncSession, tenant_id: uuid.UUID, source_type: SourceType, source_id: uuid.UUID
) -> None:
    # Each change is a distinct job (unique key); the handler skips unchanged content by hash.
    await enqueue_in_tx(
        session,
        "rag.index_source",
        {
            "tenant_id": str(tenant_id),
            "source_type": source_type.value,
            "source_id": str(source_id),
        },
        idempotency_key=f"rag.index:{source_type.value}:{source_id}:{uuid.uuid4().hex}",
    )


async def _delete(
    session: AsyncSession, tenant_id: uuid.UUID, source_type: SourceType, source_id: uuid.UUID
) -> None:
    await enqueue_in_tx(
        session,
        "rag.delete_source",
        {
            "tenant_id": str(tenant_id),
            "source_type": source_type.value,
            "source_id": str(source_id),
        },
        idempotency_key=f"rag.delete:{source_type.value}:{source_id}:{uuid.uuid4().hex}",
    )


async def tenant_changed(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    await index(session, tenant_id, SourceType.business_info, tenant_id)


async def menu_item_changed(
    session: AsyncSession, tenant_id: uuid.UUID, item_id: uuid.UUID
) -> None:
    await index(session, tenant_id, SourceType.menu_item, item_id)


async def menu_item_deleted(
    session: AsyncSession, tenant_id: uuid.UUID, item_id: uuid.UUID
) -> None:
    await _delete(session, tenant_id, SourceType.menu_item, item_id)


async def category_changed(
    session: AsyncSession, tenant_id: uuid.UUID, item_ids: list[uuid.UUID]
) -> None:
    """A category was renamed/deleted: the listed items' text (which names it) changed."""
    for item_id in item_ids:
        await index(session, tenant_id, SourceType.menu_item, item_id)


async def faq_changed(session: AsyncSession, tenant_id: uuid.UUID, faq_id: uuid.UUID) -> None:
    await index(session, tenant_id, SourceType.faq, faq_id)


async def faq_deleted(session: AsyncSession, tenant_id: uuid.UUID, faq_id: uuid.UUID) -> None:
    await _delete(session, tenant_id, SourceType.faq, faq_id)


async def reindex_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    await enqueue_in_tx(
        session,
        "rag.reindex_tenant",
        {"tenant_id": str(tenant_id)},
        idempotency_key=f"rag.reindex:{tenant_id}:{uuid.uuid4().hex}",
    )
