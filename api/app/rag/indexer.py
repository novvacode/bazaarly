"""Build knowledge chunks from a tenant's own data and keep them in sync (SPEC §13.1).

One chunk per business, per menu item and per FAQ entry. The chunk text is rebuilt from the
database on every run and re-embedded only when its sha256 changed.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assistant import KbChunk, SourceType
from app.models.catalog import FaqEntry, MenuCategory, MenuItem
from app.models.tenant import Tenant
from app.rag.embedder import Embedder
from app.services.money import format_inr


@dataclass(frozen=True, slots=True)
class SourceText:
    title: str
    content: str


def business_text(t: Tenant) -> SourceText:
    modes = []
    if "pickup" in t.fulfillment_modes:
        modes.append(f"pickup from {t.address}" if t.address else "pickup")
    if "delivery" in t.fulfillment_modes:
        fee = (
            f"delivery fee {format_inr(t.delivery_fee_paise)}"
            if t.delivery_fee_paise
            else "free delivery"
        )
        areas = (
            f"delivers only to: {', '.join(t.delivery_areas)}"
            if t.delivery_areas
            else "delivers anywhere nearby"
        )
        modes.append(f"delivery ({fee}; {areas})")
    lines = [f"Business: {t.name}."]
    if t.description:
        lines.append(f"About: {t.description}")
    if t.hours_text:
        lines.append(f"Hours: {t.hours_text}.")
    if t.address:
        lines.append(f"Address: {t.address}.")
    if t.phone:
        lines.append(f"Phone: {t.phone}.")
    lines.append(f"Ordering: {'; '.join(modes) or 'not configured'}.")
    lines.append(
        f"Minimum order: {format_inr(t.min_order_paise)}."
        if t.min_order_paise
        else "No minimum order."
    )
    lines.append(
        "Currently taking orders." if t.accepts_orders else "Not taking orders at the moment."
    )
    lines.append("Payment: cash or UPI on delivery/pickup, or online payment where offered.")
    return SourceText("Business info", " ".join(lines))


def item_text(item: MenuItem, category: str | None) -> SourceText:
    parts = [f"{item.name}{f' ({category})' if category else ''} — {format_inr(item.price_paise)}."]
    parts.append("Vegetarian." if item.is_veg else "Non-vegetarian.")
    if item.tags:
        parts.append(f"Tags: {', '.join(item.tags)}.")
    parts.append(f"Currently available: {'yes' if item.is_available else 'no (sold out)'}.")
    if item.description:
        parts.append(f"Description: {item.description}")
    return SourceText(item.name, " ".join(parts))


def faq_text(entry: FaqEntry) -> SourceText:
    return SourceText("FAQ", f"Q: {entry.question} A: {entry.answer}")


def content_hash(text: str, embedder_name: str) -> str:
    """Hash of text *and* model: switching embedding models forces re-embedding."""
    return hashlib.sha256(f"{embedder_name}\n{text}".encode()).hexdigest()


async def _load_source(
    session: AsyncSession, tenant_id: uuid.UUID, source_type: SourceType, source_id: uuid.UUID
) -> SourceText | None:
    """Current text for a source, or None if it no longer exists / shouldn't be indexed."""
    if source_type == SourceType.business_info:
        tenant = await session.get(Tenant, tenant_id)
        return business_text(tenant) if tenant and tenant.id == source_id else None
    if source_type == SourceType.menu_item:
        row = (
            await session.execute(
                select(MenuItem, MenuCategory.name)
                .outerjoin(MenuCategory, MenuCategory.id == MenuItem.category_id)
                .where(MenuItem.id == source_id, MenuItem.tenant_id == tenant_id)
            )
        ).first()
        if row is None or row[0].deleted_at is not None:
            return None
        return item_text(row[0], row[1])
    entry = (
        await session.execute(
            select(FaqEntry).where(FaqEntry.id == source_id, FaqEntry.tenant_id == tenant_id)
        )
    ).scalar_one_or_none()
    return faq_text(entry) if entry else None


async def delete_source(
    session: AsyncSession, tenant_id: uuid.UUID, source_type: SourceType, source_id: uuid.UUID
) -> None:
    await session.execute(
        delete(KbChunk).where(
            KbChunk.tenant_id == tenant_id,
            KbChunk.source_type == source_type,
            KbChunk.source_id == source_id,
        )
    )
    await session.commit()


async def index_source(
    session: AsyncSession,
    embedder: Embedder,
    tenant_id: uuid.UUID,
    source_type: SourceType,
    source_id: uuid.UUID,
) -> str:
    """(Re)index one source. Returns "indexed", "unchanged" or "deleted"."""
    source = await _load_source(session, tenant_id, source_type, source_id)
    if source is None:
        await delete_source(session, tenant_id, source_type, source_id)
        return "deleted"
    digest = content_hash(source.content, embedder.name)
    existing = (
        await session.execute(
            select(KbChunk.content_hash).where(
                KbChunk.tenant_id == tenant_id,
                KbChunk.source_type == source_type,
                KbChunk.source_id == source_id,
            )
        )
    ).scalar_one_or_none()
    if existing == digest:
        await session.rollback()
        return "unchanged"
    (vector,) = await embedder.embed_documents([source.content])
    values = {
        "tenant_id": tenant_id,
        "source_type": source_type,
        "source_id": source_id,
        "title": source.title,
        "content": source.content,
        "content_hash": digest,
        "embedding": vector,
    }
    await session.execute(
        insert(KbChunk)
        .values(id=uuid.uuid4(), **values)
        .on_conflict_do_update(
            index_elements=["source_type", "source_id"],
            set_={k: v for k, v in values.items() if k not in {"source_type", "source_id"}},
        )
    )
    await session.commit()
    return "indexed"


async def all_sources(
    session: AsyncSession, tenant_id: uuid.UUID
) -> list[tuple[SourceType, uuid.UUID]]:
    items = await session.execute(
        select(MenuItem.id).where(MenuItem.tenant_id == tenant_id, MenuItem.deleted_at.is_(None))
    )
    faqs = await session.execute(select(FaqEntry.id).where(FaqEntry.tenant_id == tenant_id))
    return [
        (SourceType.business_info, tenant_id),
        *[(SourceType.menu_item, i) for (i,) in items],
        *[(SourceType.faq, f) for (f,) in faqs],
    ]
