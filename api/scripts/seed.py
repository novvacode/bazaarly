"""Seed demo data: a platform admin plus two fictional tenants (SPEC §21).

Idempotent: existing users/tenants are left alone. Run with `make seed`.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import configure_logging
from app.core.security import hash_password
from app.core.tenancy import TenantContext
from app.db import dispose_engine, get_sessionmaker
from app.models.user import Role, User
from app.redis import close_redis
from app.repositories import memberships as membership_repo
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


async def main() -> None:
    configure_logging("WARNING", json=False)
    try:
        async with get_sessionmaker()() as session:
            await seed_admin(session)
            created = []
            for spec in TENANTS:
                _, was_created = await seed_tenant(session, spec)
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
