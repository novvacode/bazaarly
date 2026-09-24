from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import EmailStr, Field, StringConstraints

from app.models.order import FulfillmentMode, OrderStatus, PaymentMethod, PaymentStatus
from app.schemas.common import Schema

CustomerName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]
PhoneIn = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20)]
Address = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
Notes = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]
IdempotencyKey = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=8, max_length=64, pattern=r"^[\w-]+$")
]


class OrderLineIn(Schema):
    menu_item_id: uuid.UUID
    quantity: int = Field(ge=1, le=50)


class OrderCreateIn(Schema):
    """Prices are never accepted from the client (SPEC §10.3.5)."""

    idempotency_key: IdempotencyKey
    items: list[OrderLineIn] = Field(min_length=1, max_length=30)
    customer_name: CustomerName
    customer_phone: PhoneIn
    customer_email: EmailStr | None = None
    fulfillment_mode: FulfillmentMode
    delivery_address: Address | None = None
    delivery_area: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=60)] | None
    ) = None
    notes: Notes | None = None
    payment_method: PaymentMethod


class OrderItemOut(Schema):
    menu_item_id: uuid.UUID | None
    name: str
    unit_price_paise: int
    quantity: int
    line_total_paise: int


class StatusEventOut(Schema):
    from_status: OrderStatus | None
    to_status: OrderStatus
    at: datetime
    note: str | None = None


class TotalsOut(Schema):
    subtotal_paise: int
    delivery_fee_paise: int
    total_paise: int


class PaymentParamsOut(Schema):
    key_id: str
    razorpay_order_id: str
    amount_paise: int
    currency: str = "INR"
    name: str
    prefill: dict[str, str] = Field(default_factory=dict)


class PaymentVerifyIn(Schema):
    razorpay_order_id: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    razorpay_payment_id: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    razorpay_signature: Annotated[str, StringConstraints(min_length=1, max_length=128)]


class PublicOrderBrief(Schema):
    code: int
    public_token: str
    status: OrderStatus
    payment_method: PaymentMethod
    payment_status: PaymentStatus
    totals: TotalsOut


class OrderCreatedOut(Schema):
    order: PublicOrderBrief
    tracking_url: str
    payment: PaymentParamsOut | None = None


class BusinessContactOut(Schema):
    name: str
    slug: str
    phone: str | None
    address: str | None


class PublicOrderOut(Schema):
    code: int
    status: OrderStatus
    fulfillment_mode: FulfillmentMode
    payment_method: PaymentMethod
    payment_status: PaymentStatus
    customer_name: str
    delivery_address: str | None
    delivery_area: str | None
    notes: str | None
    items: list[OrderItemOut]
    totals: TotalsOut
    timeline: list[StatusEventOut]
    business: BusinessContactOut
    created_at: datetime
    is_terminal: bool
    can_pay: bool = False


class OrderSummaryOut(Schema):
    id: uuid.UUID
    code: int
    status: OrderStatus
    customer_name: str
    customer_phone: str
    fulfillment_mode: FulfillmentMode
    payment_method: PaymentMethod
    payment_status: PaymentStatus
    total_paise: int
    item_count: int
    created_at: datetime


class OrderListOut(Schema):
    items: list[OrderSummaryOut]
    next_cursor: str | None


class OrderDetailOut(OrderSummaryOut):
    public_token: str
    customer_email: str | None
    delivery_address: str | None
    delivery_area: str | None
    notes: str | None
    items: list[OrderItemOut]
    totals: TotalsOut
    timeline: list[StatusEventOut]
    allowed_transitions: list[OrderStatus]
    refund_required: bool


class TransitionIn(Schema):
    to_status: OrderStatus
    reason: Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)] | None = None


class DashboardSummaryOut(Schema):
    date: str
    timezone: str
    orders_total: int
    orders_by_status: dict[str, int]
    revenue_paise: int
    top_items: list[dict[str, int | str]]


class SalesPointOut(Schema):
    date: str
    orders: int
    revenue_paise: int


class TopItemOut(Schema):
    name: str
    quantity: int
    revenue_paise: int


class SalesOut(Schema):
    days: int
    timezone: str
    series: list[SalesPointOut]
    top_items: list[TopItemOut]
