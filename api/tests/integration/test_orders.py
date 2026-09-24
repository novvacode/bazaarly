from __future__ import annotations

import asyncio
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Outbox
from tests.factories import (
    Actor,
    add_staff,
    create_item,
    order_body,
    order_id_by_code,
    place_order,
    signup_owner,
)


async def _shop(client: AsyncClient, **settings: object) -> tuple[Actor, str, str]:
    owner = await signup_owner(client)
    if settings:
        res = await client.patch("/api/v1/tenant", headers=owner.headers, json=settings)
        assert res.status_code == 200, res.text
    cake = await create_item(client, owner, "Truffle Cake", 65000)
    cookie = await create_item(client, owner, "Cookies", 24000)
    return owner, cake, cookie


async def _outbox(session: AsyncSession) -> list[Outbox]:
    """Notification jobs only (assistant indexing jobs are covered in test_assistant)."""
    result = await session.execute(
        select(Outbox).where(Outbox.job_type.like("notifications.%")).order_by(Outbox.id)
    )
    return list(result.scalars())


# --- Creation rules ----------------------------------------------------------------------------


async def test_cod_order_is_priced_on_the_server(
    client: AsyncClient, session: AsyncSession
) -> None:
    owner, cake, cookie = await _shop(
        client, fulfillment_modes=["pickup", "delivery"], delivery_fee_paise=5000
    )
    body = order_body(
        [cake, cookie, cake],  # duplicate lines are merged
        fulfillment_mode="delivery",
        delivery_address="12 MG Road",
        customer_email="priya@example.com",
        notes="Happy birthday on the cake",
    )
    res = await client.post(f"/api/v1/public/b/{owner.slug}/orders", json=body)
    assert res.status_code == 201, res.text
    out = res.json()
    assert out["order"]["status"] == "placed"
    assert out["order"]["payment_status"] == "pending"
    assert out["order"]["totals"] == {
        "subtotal_paise": 65000 * 2 + 24000,
        "delivery_fee_paise": 5000,
        "total_paise": 65000 * 2 + 24000 + 5000,
    }
    assert out["order"]["code"] == 1001
    assert out["tracking_url"] == f"http://localhost:3000/o/{out['order']['public_token']}"
    assert out["payment"] is None

    jobs = await _outbox(session)
    assert [(j.job_type, j.idempotency_key.split(":")[0]) for j in jobs] == [
        ("notifications.order_placed_owner", "order_placed_owner"),
        ("notifications.order_status_customer", "order_status_customer"),
    ]
    assert jobs[1].payload["status"] == "placed"


async def test_client_prices_are_rejected(client: AsyncClient) -> None:
    owner, cake, _ = await _shop(client)
    body = order_body([cake])
    body["items"] = [{"menu_item_id": cake, "quantity": 1, "price_paise": 1}]
    res = await client.post(f"/api/v1/public/b/{owner.slug}/orders", json=body)
    assert res.status_code == 422
    body = order_body([cake], total_paise=1)
    assert (
        await client.post(f"/api/v1/public/b/{owner.slug}/orders", json=body)
    ).status_code == 422


async def test_no_customer_email_means_no_customer_job(
    client: AsyncClient, session: AsyncSession
) -> None:
    owner, cake, _ = await _shop(client)
    await place_order(client, owner.slug, [cake])
    assert [j.job_type for j in await _outbox(session)] == ["notifications.order_placed_owner"]


async def test_store_closed(client: AsyncClient) -> None:
    owner, cake, _ = await _shop(client, accepts_orders=False)
    res = await client.post(f"/api/v1/public/b/{owner.slug}/orders", json=order_body([cake]))
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "STORE_CLOSED"


async def test_items_must_be_available_and_belong_to_store(client: AsyncClient) -> None:
    owner, cake, cookie = await _shop(client)
    _other, other_cake, _ = await _shop(client)
    gone = await create_item(client, owner, "Gone", 1000)
    await client.delete(f"/api/v1/menu/items/{gone}", headers=owner.headers)
    await client.patch(
        f"/api/v1/menu/items/{cookie}", headers=owner.headers, json={"is_available": False}
    )
    missing = str(uuid.uuid4())
    res = await client.post(
        f"/api/v1/public/b/{owner.slug}/orders",
        json=order_body([cake, cookie, gone, other_cake, missing]),
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "ORDER_ITEMS_INVALID"
    assert set(res.json()["error"]["details"]["item_ids"]) == {cookie, gone, other_cake, missing}


@pytest.mark.parametrize(
    ("items", "status"),
    [
        ([], 422),
        ([{"quantity": 51}], 422),
        ([{"quantity": 0}], 422),
        ([{"quantity": 30}, {"quantity": 30}], 422),  # merged total over 50
    ],
)
async def test_line_limits(client: AsyncClient, items: list[dict[str, int]], status: int) -> None:
    owner, cake, _ = await _shop(client)
    body = order_body([cake])
    body["items"] = [{"menu_item_id": cake, **i} for i in items]
    res = await client.post(f"/api/v1/public/b/{owner.slug}/orders", json=body)
    assert res.status_code == status


async def test_too_many_lines(client: AsyncClient) -> None:
    owner, cake, _ = await _shop(client)
    body = order_body([cake] * 31)
    assert (
        await client.post(f"/api/v1/public/b/{owner.slug}/orders", json=body)
    ).status_code == 422


async def test_minimum_order(client: AsyncClient) -> None:
    owner, _, cookie = await _shop(client, min_order_paise=30000)
    res = await client.post(f"/api/v1/public/b/{owner.slug}/orders", json=order_body([cookie]))
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "ORDER_BELOW_MINIMUM"
    assert res.json()["error"]["details"] == {"min_order_paise": 30000, "subtotal_paise": 24000}


async def test_fulfilment_rules(client: AsyncClient) -> None:
    owner, cake, _ = await _shop(client)  # pickup only
    url = f"/api/v1/public/b/{owner.slug}/orders"
    res = await client.post(
        url, json=order_body([cake], fulfillment_mode="delivery", delivery_address="X")
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "FULFILLMENT_INVALID"

    await client.patch(
        "/api/v1/tenant",
        headers=owner.headers,
        json={"fulfillment_modes": ["delivery"], "delivery_areas": ["Koramangala", "HSR Layout"]},
    )
    for extra in (
        {},  # no address
        {"delivery_address": "12 Road"},  # no area
        {"delivery_address": "12 Road", "delivery_area": "Whitefield"},
    ):
        res = await client.post(url, json=order_body([cake], fulfillment_mode="delivery", **extra))
        assert res.status_code == 422, extra
    res = await client.post(
        url,
        json=order_body(
            [cake],
            fulfillment_mode="delivery",
            delivery_address="12 Road",
            delivery_area="hsr layout",
        ),
    )
    assert res.status_code == 201, res.text
    token = res.json()["order"]["public_token"]
    tracked = (await client.get(f"/api/v1/public/orders/{token}")).json()
    assert tracked["delivery_area"] == "HSR Layout"


@pytest.mark.parametrize(
    ("raw", "ok"),
    [("98765 43210", True), ("+91 98765-43210", True), ("12345", False), ("abcdefghij", False)],
)
async def test_phone_normalisation(client: AsyncClient, raw: str, ok: bool) -> None:
    owner, cake, _ = await _shop(client)
    res = await client.post(
        f"/api/v1/public/b/{owner.slug}/orders", json=order_body([cake], customer_phone=raw)
    )
    assert (res.status_code == 201) is ok
    if ok:
        order_id = await order_id_by_code(client, owner, res.json()["order"]["code"])
        detail = (await client.get(f"/api/v1/orders/{order_id}", headers=owner.headers)).json()
        assert detail["customer_phone"] == "+919876543210"
    else:
        assert res.json()["error"]["code"] == "PHONE_INVALID"


# --- Idempotency and concurrency ---------------------------------------------------------------


async def test_idempotent_resubmit_returns_same_order(
    client: AsyncClient, session: AsyncSession
) -> None:
    owner, cake, _ = await _shop(client)
    body = order_body([cake])
    first = await client.post(f"/api/v1/public/b/{owner.slug}/orders", json=body)
    second = await client.post(f"/api/v1/public/b/{owner.slug}/orders", json=body)
    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json() == second.json()
    assert len(await _outbox(session)) == 1


async def test_concurrent_resubmits_create_one_order(client: AsyncClient) -> None:
    owner, cake, _ = await _shop(client)
    body = order_body([cake])
    results = await asyncio.gather(
        *[client.post(f"/api/v1/public/b/{owner.slug}/orders", json=body) for _ in range(5)]
    )
    assert sorted(r.status_code for r in results) == [200, 200, 200, 200, 201]
    assert len({r.json()["order"]["public_token"] for r in results}) == 1
    listing = (await client.get("/api/v1/orders", headers=owner.headers)).json()
    assert len(listing["items"]) == 1


async def test_twenty_concurrent_orders_get_unique_codes(client: AsyncClient) -> None:
    owner, cake, _ = await _shop(client)
    results = await asyncio.gather(
        *[
            client.post(f"/api/v1/public/b/{owner.slug}/orders", json=order_body([cake]))
            for _ in range(20)
        ]
    )
    assert all(r.status_code == 201 for r in results), [
        r.text for r in results if r.status_code != 201
    ]
    codes = [r.json()["order"]["code"] for r in results]
    assert len(set(codes)) == 20
    assert min(codes) >= 1001


# --- Tracking ----------------------------------------------------------------------------------


async def test_public_tracking(client: AsyncClient) -> None:
    owner, cake, _ = await _shop(client, phone="9876500009")
    out = await place_order(client, owner.slug, [cake])
    res = await client.get(f"/api/v1/public/orders/{out['order']['public_token']}")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "placed"
    assert body["items"] == [
        {
            "menu_item_id": cake,
            "name": "Truffle Cake",
            "unit_price_paise": 65000,
            "quantity": 1,
            "line_total_paise": 65000,
        }
    ]
    assert body["timeline"][0]["to_status"] == "placed"
    assert body["business"]["phone"] == "+919876500009"
    assert body["is_terminal"] is False
    assert "customer_phone" not in body
    assert (await client.get("/api/v1/public/orders/not-a-token")).status_code == 404


# --- Merchant transitions ----------------------------------------------------------------------


async def test_full_pickup_lifecycle_by_staff(client: AsyncClient, session: AsyncSession) -> None:
    owner, cake, _ = await _shop(client)
    staff = await add_staff(client, owner)
    out = await place_order(client, owner.slug, [cake], customer_email="c@example.com")
    order_id = await order_id_by_code(client, owner, out["order"]["code"])

    detail = (await client.get(f"/api/v1/orders/{order_id}", headers=staff.headers)).json()
    assert detail["allowed_transitions"] == ["confirmed", "cancelled"]

    for to in ("confirmed", "preparing", "ready", "completed"):
        res = await client.post(
            f"/api/v1/orders/{order_id}/transition", headers=staff.headers, json={"to_status": to}
        )
        assert res.status_code == 200, res.text
        assert res.json()["status"] == to
    detail = res.json()
    assert detail["allowed_transitions"] == []
    assert [e["to_status"] for e in detail["timeline"]] == [
        "placed",
        "confirmed",
        "preparing",
        "ready",
        "completed",
    ]
    customer_jobs = [j for j in await _outbox(session) if j.job_type.endswith("status_customer")]
    assert [j.payload["status"] for j in customer_jobs] == [
        "placed",
        "confirmed",
        "preparing",
        "ready",
        "completed",
    ]

    tracked = (await client.get(f"/api/v1/public/orders/{out['order']['public_token']}")).json()
    assert tracked["is_terminal"] is True


async def test_invalid_transition_is_409(client: AsyncClient) -> None:
    owner, cake, _ = await _shop(client)
    out = await place_order(client, owner.slug, [cake])
    order_id = await order_id_by_code(client, owner, out["order"]["code"])
    for to in ("completed", "out_for_delivery", "pending_payment"):
        res = await client.post(
            f"/api/v1/orders/{order_id}/transition", headers=owner.headers, json={"to_status": to}
        )
        assert res.status_code == 409
        err = res.json()["error"]
        assert err["code"] == "ORDER_INVALID_TRANSITION"
        assert err["details"]["allowed"] == ["cancelled", "confirmed"]


async def test_cancel_with_reason(client: AsyncClient) -> None:
    owner, cake, _ = await _shop(client)
    out = await place_order(client, owner.slug, [cake])
    order_id = await order_id_by_code(client, owner, out["order"]["code"])
    res = await client.post(
        f"/api/v1/orders/{order_id}/transition",
        headers=owner.headers,
        json={"to_status": "cancelled", "reason": "Out of chocolate"},
    )
    assert res.json()["timeline"][-1]["note"] == "Out of chocolate"
    assert res.json()["refund_required"] is False


async def test_mark_cod_paid(client: AsyncClient) -> None:
    owner, cake, _ = await _shop(client)
    out = await place_order(client, owner.slug, [cake])
    order_id = await order_id_by_code(client, owner, out["order"]["code"])
    for _ in range(2):  # idempotent
        res = await client.post(f"/api/v1/orders/{order_id}/mark-paid", headers=owner.headers)
        assert res.status_code == 200
        assert res.json()["payment_status"] == "paid"
    await client.post(
        f"/api/v1/orders/{order_id}/transition",
        headers=owner.headers,
        json={"to_status": "cancelled"},
    )
    detail = (await client.get(f"/api/v1/orders/{order_id}", headers=owner.headers)).json()
    assert detail["refund_required"] is True


# --- Listing -----------------------------------------------------------------------------------


async def test_list_filters_and_cursor_pagination(client: AsyncClient) -> None:
    owner, cake, _ = await _shop(client)
    codes = []
    for i in range(5):
        out = await place_order(
            client,
            owner.slug,
            [cake],
            customer_name=f"Customer {i}",
            customer_phone=f"98765000{i}0",
        )
        codes.append(out["order"]["code"])

    page1 = (await client.get("/api/v1/orders", headers=owner.headers, params={"limit": 2})).json()
    assert [o["code"] for o in page1["items"]] == codes[::-1][:2]
    page2 = (
        await client.get(
            "/api/v1/orders",
            headers=owner.headers,
            params={"limit": 2, "cursor": page1["next_cursor"]},
        )
    ).json()
    page3 = (
        await client.get(
            "/api/v1/orders",
            headers=owner.headers,
            params={"limit": 2, "cursor": page2["next_cursor"]},
        )
    ).json()
    seen = [o["code"] for p in (page1, page2, page3) for o in p["items"]]
    assert seen == codes[::-1]
    assert page3["next_cursor"] is None

    async def search(**params: str) -> list[int]:
        res = await client.get("/api/v1/orders", headers=owner.headers, params=params)
        assert res.status_code == 200, res.text
        return [o["code"] for o in res.json()["items"]]

    assert await search(q=f"#{codes[2]}") == [codes[2]]
    assert await search(q="customer 3") == [codes[3]]
    assert await search(q="9876500040") == [codes[4]]

    order_id = await order_id_by_code(client, owner, codes[0])
    await client.post(
        f"/api/v1/orders/{order_id}/transition",
        headers=owner.headers,
        json={"to_status": "confirmed"},
    )
    assert await search(status="confirmed") == [codes[0]]
    assert len(await search(status="placed,confirmed")) == 5
    today = (await client.get("/api/v1/dashboard/summary", headers=owner.headers)).json()["date"]
    assert len(await search(**{"from": today, "to": today})) == 5
    assert await search(**{"from": "2001-01-01", "to": "2001-01-02"}) == []

    res = await client.get("/api/v1/orders", headers=owner.headers, params={"status": "bogus"})
    assert res.status_code == 422
    res = await client.get("/api/v1/orders", headers=owner.headers, params={"cursor": "%%%"})
    assert res.status_code == 422


# --- Dashboard ---------------------------------------------------------------------------------


async def test_dashboard_summary_and_sales(client: AsyncClient) -> None:
    owner, cake, cookie = await _shop(client)
    o1 = await place_order(client, owner.slug, [cake, cookie])
    o2 = await place_order(client, owner.slug, [cookie])
    o3 = await place_order(client, owner.slug, [cake])
    ids = [await order_id_by_code(client, owner, o["order"]["code"]) for o in (o1, o2, o3)]
    await client.post(f"/api/v1/orders/{ids[0]}/mark-paid", headers=owner.headers)
    await client.post(f"/api/v1/orders/{ids[1]}/mark-paid", headers=owner.headers)
    await client.post(
        f"/api/v1/orders/{ids[1]}/transition",
        headers=owner.headers,
        json={"to_status": "cancelled"},
    )

    summary = (await client.get("/api/v1/dashboard/summary", headers=owner.headers)).json()
    assert summary["orders_total"] == 3
    assert summary["orders_by_status"] == {"placed": 2, "cancelled": 1}
    # Paid and not cancelled: only order 1.
    assert summary["revenue_paise"] == 65000 + 24000
    assert summary["top_items"][0] == {
        "name": "Truffle Cake",
        "quantity": 2,
        "revenue_paise": 130000,
    }
    assert summary["timezone"] == "Asia/Kolkata"

    sales = (await client.get("/api/v1/dashboard/sales", headers=owner.headers)).json()
    assert len(sales["series"]) == 30
    assert sales["series"][-1] == {
        "date": summary["date"],
        "orders": 2,
        "revenue_paise": 89000,
    }
    assert sum(p["orders"] for p in sales["series"]) == 2
    assert sales["top_items"][0] == {"name": "Truffle Cake", "quantity": 2, "revenue_paise": 130000}

    other_day = (
        await client.get(
            "/api/v1/dashboard/summary", headers=owner.headers, params={"date": "2020-01-01"}
        )
    ).json()
    assert other_day["orders_total"] == 0
