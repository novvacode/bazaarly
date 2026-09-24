"""In-transaction reactions to catalog changes.

Services call these inside the transaction that made the change, so anything they enqueue via
the outbox commits atomically with it (e.g. assistant re-indexing in Phase 6). Cache
invalidation happens separately, after commit (`services.public.invalidate`).
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession


async def tenant_changed(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    return None


async def menu_item_changed(
    session: AsyncSession, tenant_id: uuid.UUID, item_id: uuid.UUID
) -> None:
    return None


async def menu_item_deleted(
    session: AsyncSession, tenant_id: uuid.UUID, item_id: uuid.UUID
) -> None:
    return None


async def category_changed(
    session: AsyncSession, tenant_id: uuid.UUID, item_ids: list[uuid.UUID]
) -> None:
    """A category was renamed/deleted: the listed items' text (which names it) changed."""
    return None


async def faq_changed(session: AsyncSession, tenant_id: uuid.UUID, faq_id: uuid.UUID) -> None:
    return None


async def faq_deleted(session: AsyncSession, tenant_id: uuid.UUID, faq_id: uuid.UUID) -> None:
    return None
