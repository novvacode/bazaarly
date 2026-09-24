from __future__ import annotations

from sqlalchemy import Boolean, Integer, Text, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Timestamps, UUIDPk


class Tenant(UUIDPk, Timestamps, Base):
    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    logo_url: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text)
    address: Mapped[str | None] = mapped_column(Text)
    accepts_orders: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    fulfillment_modes: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=lambda: ["pickup"], server_default=text("'{pickup}'")
    )
    delivery_areas: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list, server_default=text("'{}'")
    )
    min_order_paise: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    delivery_fee_paise: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    hours_text: Mapped[str | None] = mapped_column(Text)
    timezone: Mapped[str] = mapped_column(
        Text, nullable=False, default="Asia/Kolkata", server_default=text("'Asia/Kolkata'")
    )
    order_seq: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1000, server_default=text("1000")
    )
