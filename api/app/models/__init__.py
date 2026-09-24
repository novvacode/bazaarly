"""Import every model so Alembic autogenerate and `Base.metadata` see all tables."""

from app.models.auth import Invite, RefreshToken
from app.models.base import Base
from app.models.catalog import FaqEntry, MenuCategory, MenuItem
from app.models.order import Order, OrderItem, OrderStatusEvent, Outbox
from app.models.tenant import Tenant
from app.models.user import Membership, Role, User

__all__ = [
    "Base",
    "FaqEntry",
    "Invite",
    "Membership",
    "MenuCategory",
    "MenuItem",
    "Order",
    "OrderItem",
    "OrderStatusEvent",
    "Outbox",
    "RefreshToken",
    "Role",
    "Tenant",
    "User",
]
