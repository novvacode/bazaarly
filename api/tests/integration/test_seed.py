"""The seed script must produce data that works through the real API (e.g. valid emails)."""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from scripts.seed import seed_admin, seed_orders, seed_tenant
from scripts.seed_data import ADMIN_EMAIL, ADMIN_PASSWORD, DEMO_PASSWORD, TENANTS


async def test_seed_is_usable_and_idempotent(client: AsyncClient, session: AsyncSession) -> None:
    await seed_admin(session)
    for spec in TENANTS:
        tenant_id, created = await seed_tenant(session, spec)
        assert created
        assert await seed_orders(session, tenant_id, spec) > 0
        _, created_again = await seed_tenant(session, spec)
        assert not created_again

    res = await client.post(
        "/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    assert res.status_code == 200, res.text
    assert res.json()["user"]["is_platform_admin"] is True

    for spec in TENANTS:
        for who in ("owner", "staff"):
            res = await client.post(
                "/api/v1/auth/login",
                json={"email": spec[who]["email"], "password": DEMO_PASSWORD},
            )
            assert res.status_code == 200, res.text
            assert res.json()["tenant"]["role"] == who
        store = (await client.get(f"/api/v1/public/b/{spec['tenant']['slug']}")).json()
        assert store["business"]["name"] == spec["tenant"]["name"]
        assert store["categories"]
        owner = await client.post(
            "/api/v1/auth/login", json={"email": spec["owner"]["email"], "password": DEMO_PASSWORD}
        )
        headers = {"Authorization": f"Bearer {owner.json()['access_token']}"}
        sales = (await client.get("/api/v1/dashboard/sales", headers=headers)).json()
        assert sum(p["orders"] for p in sales["series"]) > 0
    client.cookies.clear()


async def test_create_admin_creates_and_promotes(client: AsyncClient) -> None:
    from scripts.create_admin import create_admin
    from tests.factories import signup_owner

    assert await create_admin("new.admin@example.com", "New Admin", "long-enough-pass") == "created"
    owner = await signup_owner(client)
    assert await create_admin(owner.email, "ignored", None) == "promoted"
    res = await client.post(
        "/api/v1/auth/login",
        json={"email": "new.admin@example.com", "password": "long-enough-pass"},
    )
    assert res.json()["user"]["is_platform_admin"] is True
    client.cookies.clear()
