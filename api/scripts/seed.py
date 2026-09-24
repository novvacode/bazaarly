"""Seed demo data: a platform admin plus two fictional tenants (SPEC §21).

Idempotent: existing users/tenants are left alone. Run with `make seed`.
"""

from __future__ import annotations

import asyncio
import random
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import configure_logging
from app.core.security import hash_password, random_token
from app.core.tenancy import TenantContext
from app.db import dispose_engine, get_sessionmaker
from app.models.order import (
    FulfillmentMode,
    Order,
    OrderItem,
    OrderStatus,
    OrderStatusEvent,
    PaymentMethod,
    PaymentStatus,
)
from app.models.user import Role, User
from app.redis import close_redis
from app.repositories import memberships as membership_repo
from app.repositories import menu as menu_repo
from app.repositories import orders as order_repo
from app.repositories import tenants as tenant_repo
from app.repositories import users as user_repo
from app.schemas.menu import FaqIn, ItemIn
from app.services import menu as menu_service
from scripts.seed_data import ADMIN_EMAIL, ADMIN_PASSWORD, DEMO_PASSWORD, TENANTS


async def _user(session: AsyncSession, email: str, name: str, password: str) -> User:
    user = await user_repo.get_by_email(session, email)
    if user is None:
        user = await user_repo.create(
            session, email=email, name=name, password_hash=hash_password(password)
        )
    return user


async def seed_admin(session: AsyncSession) -> None:
    admin = await _user(session, ADMIN_EMAIL, "Platform Admin", ADMIN_PASSWORD)
    admin.is_platform_admin = True
    await session.commit()


async def seed_tenant(session: AsyncSession, spec: dict[str, Any]) -> tuple[uuid.UUID, bool]:
    """Returns (tenant_id, created)."""
    existing = await tenant_repo.get_by_slug(session, spec["tenant"]["slug"])
    if existing is not None:
        return existing.id, False

    owner = await _user(session, spec["owner"]["email"], spec["owner"]["name"], DEMO_PASSWORD)
    staff = await _user(session, spec["staff"]["email"], spec["staff"]["name"], DEMO_PASSWORD)
    t = spec["tenant"]
    tenant = await tenant_repo.create(session, name=t["name"], slug=t["slug"], email=t["email"])
    await membership_repo.create(session, user_id=owner.id, tenant_id=tenant.id, role=Role.owner)
    await membership_repo.create(session, user_id=staff.id, tenant_id=tenant.id, role=Role.staff)
    ctx = TenantContext(tenant_id=tenant.id, user_id=owner.id, role=Role.owner)
    await tenant_repo.update_fields(
        session, ctx, {k: v for k, v in t.items() if k not in {"name", "slug", "email"}}
    )
    await session.commit()

    for category_name, items in spec["menu"]:
        category = await menu_service.create_category(session, ctx, category_name)
        for item in items:
            await menu_service.create_item(session, ctx, ItemIn(category_id=category.id, **item))
    for question, answer in spec["faq"]:
        await menu_service.create_faq(session, ctx, FaqIn(question=question, answer=answer))
    return tenant.id, True


CUSTOMERS = [
    ("Ananya S", "+919800000101"),
    ("Rahul M", "+919800000102"),
    ("Fatima K", "+919800000103"),
    ("Vikram P", "+919800000104"),
    ("Neha G", "+919800000105"),
    ("Joseph D", "+919800000106"),
]
_FLOW = {
    FulfillmentMode.pickup: [
        OrderStatus.confirmed,
        OrderStatus.preparing,
        OrderStatus.ready,
        OrderStatus.completed,
    ],
    FulfillmentMode.delivery: [
        OrderStatus.confirmed,
        OrderStatus.preparing,
        OrderStatus.out_for_delivery,
        OrderStatus.completed,
    ],
}


async def seed_orders(session: AsyncSession, tenant_id: uuid.UUID, spec: dict[str, Any]) -> int:
    """Past orders for the dashboard and analytics (no outbox jobs: nothing is emailed)."""
    rng = random.Random(spec["tenant"]["slug"])  # deterministic per tenant
    items = await menu_repo.list_items(session, tenant_id, available_only=True)
    modes = [FulfillmentMode(m) for m in spec["tenant"]["fulfillment_modes"]]
    now = datetime.now(UTC)
    created = 0
    for days_ago in range(20, -1, -1):
        for _ in range(rng.randint(0, 4) if days_ago else 3):
            placed_at = now - timedelta(
                days=days_ago, hours=rng.randint(0, 8), minutes=rng.randint(0, 59)
            )
            mode = rng.choice(modes)
            lines = rng.sample(items, k=min(len(items), rng.randint(1, 3)))
            order_items = []
            subtotal = 0
            for mi in lines:
                qty = rng.randint(1, 2)
                subtotal += mi.price_paise * qty
                order_items.append(
                    OrderItem(
                        menu_item_id=mi.id,
                        name_snapshot=mi.name,
                        unit_price_paise=mi.price_paise,
                        quantity=qty,
                        line_total_paise=mi.price_paise * qty,
                        created_at=placed_at,
                    )
                )
            fee = spec["tenant"]["delivery_fee_paise"] if mode == FulfillmentMode.delivery else 0
            # Today's orders stay open for the board; older ones are finished.
            if days_ago == 0:
                path = _FLOW[mode][: rng.randint(0, 2)]
            elif rng.random() < 0.08:
                path = [OrderStatus.cancelled]
            else:
                path = _FLOW[mode]
            status = path[-1] if path else OrderStatus.placed
            paid = status == OrderStatus.completed
            name, phone = rng.choice(CUSTOMERS)
            order = Order(
                tenant_id=tenant_id,
                code=await order_repo.allocate_code(session, tenant_id),
                public_token=random_token(32),
                idempotency_key=f"seed-{uuid.uuid4().hex}",
                customer_name=name,
                customer_phone=phone,
                fulfillment_mode=mode,
                delivery_address="Flat 101, Example Residency"
                if mode == FulfillmentMode.delivery
                else None,
                delivery_area=spec["tenant"]["delivery_areas"][0]
                if mode == FulfillmentMode.delivery
                else None,
                status=status,
                payment_method=PaymentMethod.cod,
                payment_status=PaymentStatus.paid if paid else PaymentStatus.pending,
                subtotal_paise=subtotal,
                delivery_fee_paise=fee,
                total_paise=subtotal + fee,
                created_at=placed_at,
                updated_at=placed_at,
            )
            session.add(order)
            await session.flush()
            for oi in order_items:
                oi.order_id = order.id
            session.add_all(order_items)
            events = [(None, OrderStatus.placed)]
            prev = OrderStatus.placed
            for step in path:
                events.append((prev, step))
                prev = step
            for i, (frm, to) in enumerate(events):
                session.add(
                    OrderStatusEvent(
                        order_id=order.id,
                        from_status=frm,
                        to_status=to,
                        created_at=placed_at + timedelta(minutes=15 * i),
                    )
                )
            created += 1
    await session.commit()
    return created


async def main() -> None:
    configure_logging("WARNING", json=False)
    try:
        async with get_sessionmaker()() as session:
            await seed_admin(session)
            created = []
            for spec in TENANTS:
                tenant_id, was_created = await seed_tenant(session, spec)
                if was_created:
                    await seed_orders(session, tenant_id, spec)
                created.append((spec, was_created))
    finally:
        await dispose_engine()
        await close_redis()

    print("\nSeed complete. Demo credentials (local only):\n")
    print(f"  Platform admin   {ADMIN_EMAIL} / {ADMIN_PASSWORD}")
    for spec, was_created in created:
        note = "" if was_created else "  (already existed)"
        slug = spec["tenant"]["slug"]
        print(f"\n  {spec['tenant']['name']}  →  http://localhost:3000/b/{slug}{note}")
        print(f"    owner  {spec['owner']['email']} / {DEMO_PASSWORD}")
        print(f"    staff  {spec['staff']['email']} / {DEMO_PASSWORD}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
