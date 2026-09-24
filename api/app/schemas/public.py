from __future__ import annotations

import uuid

from app.schemas.common import Schema


class PublicBusiness(Schema):
    name: str
    slug: str
    description: str | None
    logo_url: str | None
    phone: str | None
    address: str | None
    hours_text: str | None
    accepts_orders: bool
    fulfillment_modes: list[str]
    delivery_areas: list[str]
    min_order_paise: int
    delivery_fee_paise: int
    accepts_online_payments: bool = False


class PublicItem(Schema):
    id: uuid.UUID
    name: str
    description: str | None
    price_paise: int
    image_url: str | None
    is_veg: bool
    tags: list[str]


class PublicCategory(Schema):
    id: uuid.UUID | None
    name: str
    items: list[PublicItem]


class StorefrontOut(Schema):
    business: PublicBusiness
    categories: list[PublicCategory]
