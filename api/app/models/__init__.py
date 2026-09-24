"""Import every model so Alembic autogenerate and `Base.metadata` see all tables."""

from app.models.assistant import AssistantLog, KbChunk
from app.models.auth import Invite, RefreshToken
from app.models.base import Base
from app.models.catalog import FaqEntry, MenuCategory, MenuItem
from app.models.order import Order, OrderItem, OrderStatusEvent, Outbox
from app.models.payment import Payment, WebhookEvent
from app.models.tenant import Tenant
from app.models.user import Membership, Role, User

__all__ = [
    "AssistantLog",
    "Base",
    "FaqEntry",
    "Invite",
    "KbChunk",
    "Membership",
    "MenuCategory",
    "MenuItem",
    "Order",
    "OrderItem",
    "OrderStatusEvent",
    "Outbox",
    "Payment",
    "RefreshToken",
    "Role",
    "Tenant",
    "User",
    "WebhookEvent",
]
