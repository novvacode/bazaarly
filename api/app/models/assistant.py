from __future__ import annotations

import enum
import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    REAL,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Text,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import UniqueConstraint

from app.models.base import Base, CreatedAt, UUIDPk

EMBEDDING_DIM = 384


class SourceType(enum.StrEnum):
    business_info = "business_info"
    menu_item = "menu_item"
    faq = "faq"


class KbChunk(UUIDPk, Base):
    """One retrievable chunk of a tenant's knowledge (SPEC §6.5, §13.1)."""

    __tablename__ = "kb_chunks"
    __table_args__ = (
        UniqueConstraint("source_type", "source_id"),
        Index(
            "ix_kb_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_type: Mapped[SourceType] = mapped_column(
        Enum(SourceType, name="kb_source_type", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    source_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class AssistantLog(UUIDPk, CreatedAt, Base):
    __tablename__ = "assistant_logs"
    __table_args__ = (Index("ix_assistant_logs_tenant_created", "tenant_id", "created_at", "id"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    session_id: Mapped[str] = mapped_column(Text, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    answered: Mapped[bool] = mapped_column(Boolean, nullable=False)
    retrieved_chunk_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(Uuid), nullable=False)
    top_score: Mapped[float | None] = mapped_column(REAL)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
