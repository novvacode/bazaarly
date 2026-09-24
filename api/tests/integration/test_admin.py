from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.queue import keys
from app.queue.envelope import Envelope
from app.redis import get_redis
from tests.factories import Actor, create_item, place_order, signup_owner


async def _admin(client: AsyncClient, session: AsyncSession) -> Actor:
    admin = await signup_owner(client)
    await session.execute(
        update(User).where(User.id == admin.user_id).values(is_platform_admin=True)
    )
    await session.commit()
    return admin


async def _dead(entry_type: str = "notifications.order_placed_owner") -> str:
    env = Envelope(type=entry_type, payload={"x": 1}, idempotency_key="dead-1", attempt=4)
    return str(
        await get_redis().xadd(
            keys.DEAD,
            {
                "envelope": env.to_json(),
                "error_type": "RuntimeError",
                "error": "boom",
                "traceback": "Traceback...",
                "failed_at": "2026-09-24T00:00:00+00:00",
            },
        )
    )


async def test_admin_routes_are_invisible_to_others(client: AsyncClient) -> None:
    owner = await signup_owner(client)
    for method, url in [
        ("GET", "/api/v1/admin/tenants"),
        ("GET", "/api/v1/admin/jobs/stats"),
        ("GET", "/api/v1/admin/jobs/dead"),
        ("POST", "/api/v1/admin/jobs/dead/1-0/retry"),
        ("DELETE", "/api/v1/admin/jobs/dead/1-0"),
    ]:
        res = await client.request(method, url, headers=owner.headers)
        assert res.status_code == 404, (method, url)
        assert (await client.request(method, url)).status_code == 401


async def test_admin_tenants_and_stats(client: AsyncClient, session: AsyncSession) -> None:
    admin = await _admin(client, session)
    shop = await signup_owner(client, business="Busy Shop")
    item = await create_item(client, shop)
    await place_order(client, shop.slug, [item])

    tenants = (await client.get("/api/v1/admin/tenants", headers=admin.headers)).json()
    busy = next(t for t in tenants if t["name"] == "Busy Shop")
    assert (busy["members"], busy["orders"], busy["orders_last_7_days"]) == (1, 1, 1)

    stats = (await client.get("/api/v1/admin/jobs/stats", headers=admin.headers)).json()
    assert stats == {
        "stream_length": 0,
        "pending": 0,
        "delayed": 0,
        "dead": 0,
        "consumers": [],
        "counters": {},
    }


async def test_dead_letter_retry_and_delete(client: AsyncClient, session: AsyncSession) -> None:
    admin = await _admin(client, session)
    first = await _dead()
    second = await _dead()

    dead = (await client.get("/api/v1/admin/jobs/dead", headers=admin.headers)).json()
    assert [d["entry_id"] for d in dead] == [second, first]
    assert dead[0]["error"] == "boom"
    assert dead[0]["attempt"] == 4

    res = await client.post(f"/api/v1/admin/jobs/dead/{first}/retry", headers=admin.headers)
    assert res.status_code == 204
    (entry,) = await get_redis().xrange(keys.JOBS)
    assert Envelope.from_json(entry[1]["envelope"]).attempt == 0

    assert (
        await client.delete(f"/api/v1/admin/jobs/dead/{second}", headers=admin.headers)
    ).status_code == 204
    assert (await client.get("/api/v1/admin/jobs/dead", headers=admin.headers)).json() == []
    res = await client.delete(f"/api/v1/admin/jobs/dead/{second}", headers=admin.headers)
    assert res.status_code == 404
    res = await client.post("/api/v1/admin/jobs/dead/not-an-id/retry", headers=admin.headers)
    assert res.status_code == 422
