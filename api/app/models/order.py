from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAt, Timestamps, UUIDPk


def _pg_enum(cls: type[enum.Enum], name: str) -> Enum:
    return Enum(cls, name=name, values_callable=lambda e: [m.value for m in e])


class OrderStatus(enum.StrEnum):
    pending_payment = "pending_payment"
    placed = "placed"
    confirmed = "confirmed"
    preparing = "preparing"
    ready = "ready"
    out_for_delivery = "out_for_delivery"
    completed = "completed"
    cancelled = "cancelled"


class FulfillmentMode(enum.StrEnum):
    pickup = "pickup"
    delivery = "delivery"


class PaymentMethod(enum.StrEnum):
    online = "online"
    cod = "cod"


class PaymentStatus(enum.StrEnum):
    pending = "pending"
    paid = "paid"
    failed = "failed"
    refunded = "refunded"


order_status_enum = _pg_enum(OrderStatus, "order_status")


class Order(UUIDPk, Timestamps, Base):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code"),
        UniqueConstraint("tenant_id", "idempotency_key"),
        Index("ix_orders_tenant_created", "tenant_id", "created_at", "id"),
        Index("ix_orders_tenant_status", "tenant_id", "status"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[int] = mapped_column(Integer, nullable=False)
    public_token: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    customer_name: Mapped[str] = mapped_column(Text, nullable=False)
    customer_phone: Mapped[str] = mapped_column(Text, nullable=False)
    customer_email: Mapped[str | None] = mapped_column(Text)
    fulfillment_mode: Mapped[FulfillmentMode] = mapped_column(
        _pg_enum(FulfillmentMode, "fulfillment_mode"), nullable=False
    )
    delivery_address: Mapped[str | None] = mapped_column(Text)
    delivery_area: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[OrderStatus] = mapped_column(order_status_enum, nullable=False)
    payment_method: Mapped[PaymentMethod] = mapped_column(
        _pg_enum(PaymentMethod, "payment_method"), nullable=False
    )
    payment_status: Mapped[PaymentStatus] = mapped_column(
        _pg_enum(PaymentStatus, "payment_status"), nullable=False
    )
    subtotal_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    delivery_fee_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    total_paise: Mapped[int] = mapped_column(Integer, nullable=False)


class OrderItem(UUIDPk, CreatedAt, Base):
    __tablename__ = "order_items"
    __table_args__ = (CheckConstraint("quantity BETWEEN 1 AND 50", name="quantity_range"),)

    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    menu_item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("menu_items.id", ondelete="SET NULL")
    )
    name_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    unit_price_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    line_total_paise: Mapped[int] = mapped_column(Integer, nullable=False)


class OrderStatusEvent(UUIDPk, CreatedAt, Base):
    __tablename__ = "order_status_events"

    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_status: Mapped[OrderStatus | None] = mapped_column(order_status_enum)
    to_status: Mapped[OrderStatus] = mapped_column(order_status_enum, nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    note: Mapped[str | None] = mapped_column(Text)


class Outbox(Base):
    """Transactional outbox (SPEC §6.4, §12). Written only via `enqueue_in_tx`."""

    __tablename__ = "outbox"
    __table_args__ = (
        Index(
            "ix_outbox_unpublished",
            "id",
            postgresql_where="published_at IS NULL",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
