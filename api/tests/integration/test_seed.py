"""The seed script must produce data that works through the real API (e.g. valid emails)."""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from scripts.seed import seed_admin, seed_tenant
from scripts.seed_data import ADMIN_EMAIL, ADMIN_PASSWORD, DEMO_PASSWORD, TENANTS


async def test_seed_is_usable_and_idempotent(client: AsyncClient, session: AsyncSession) -> None:
    await seed_admin(session)
    for spec in TENANTS:
        _, created = await seed_tenant(session, spec)
        assert created
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
    client.cookies.clear()
