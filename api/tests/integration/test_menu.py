from __future__ import annotations

import io

import pytest
from httpx import AsyncClient
from PIL import Image

from tests.factories import Actor, add_staff, signup_owner


async def _category(client: AsyncClient, owner: Actor, name: str) -> str:
    res = await client.post("/api/v1/menu/categories", headers=owner.headers, json={"name": name})
    assert res.status_code == 201, res.text
    return str(res.json()["id"])


async def _item(client: AsyncClient, owner: Actor, **fields: object) -> dict[str, object]:
    body = {"name": "Chocolate Truffle Cake", "price_paise": 65000, **fields}
    res = await client.post("/api/v1/menu/items", headers=owner.headers, json=body)
    assert res.status_code == 201, res.text
    return dict(res.json())


async def test_category_crud_and_positions(client: AsyncClient) -> None:
    owner = await signup_owner(client)
    cakes = await _category(client, owner, "Cakes")
    cookies = await _category(client, owner, "Cookies")
    res = await client.get("/api/v1/menu/categories", headers=owner.headers)
    assert [(c["name"], c["position"]) for c in res.json()] == [("Cakes", 0), ("Cookies", 1)]

    res = await client.patch(
        f"/api/v1/menu/categories/{cakes}",
        headers=owner.headers,
        json={"name": "Celebration cakes"},
    )
    assert res.json()["name"] == "Celebration cakes"

    item = await _item(client, owner, category_id=cookies)
    res = await client.delete(f"/api/v1/menu/categories/{cookies}", headers=owner.headers)
    assert res.status_code == 204
    items = (await client.get("/api/v1/menu/items", headers=owner.headers)).json()
    assert items[0]["id"] == item["id"]
    assert items[0]["category_id"] is None


async def test_item_crud_and_validation(client: AsyncClient) -> None:
    owner = await signup_owner(client)
    item = await _item(client, owner, tags=["Eggless", "eggless", "best seller"], is_veg=True)
    assert item["tags"] == ["eggless", "best seller"]
    assert item["position"] == 0

    res = await client.patch(
        f"/api/v1/menu/items/{item['id']}",
        headers=owner.headers,
        json={"price_paise": 70000, "is_available": False, "description": "Rich and dark"},
    )
    assert res.status_code == 200
    assert res.json()["price_paise"] == 70000
    assert res.json()["is_available"] is False

    bad_bodies = [
        {"name": "X", "price_paise": 0},
        {"name": "X", "price_paise": -5},
        {"name": "", "price_paise": 100},
        {"name": "X", "price_paise": 100, "tags": ["!!"]},
        {"name": "X", "price_paise": 100, "tags": [f"t{i}" for i in range(11)]},
        {"name": "X", "price_paise": 100, "unknown": 1},
        {"name": "X" * 101, "price_paise": 100},
    ]
    for body in bad_bodies:
        res = await client.post("/api/v1/menu/items", headers=owner.headers, json=body)
        assert res.status_code == 422, body
    res = await client.patch(
        f"/api/v1/menu/items/{item['id']}", headers=owner.headers, json={"price_paise": None}
    )
    assert res.status_code == 422

    res = await client.delete(f"/api/v1/menu/items/{item['id']}", headers=owner.headers)
    assert res.status_code == 204
    assert (await client.get("/api/v1/menu/items", headers=owner.headers)).json() == []
    # Soft-deleted items are gone everywhere, including for further edits.
    res = await client.patch(
        f"/api/v1/menu/items/{item['id']}", headers=owner.headers, json={"price_paise": 1}
    )
    assert res.status_code == 404


async def test_reorder_moves_items_between_categories(client: AsyncClient) -> None:
    owner = await signup_owner(client)
    a = await _category(client, owner, "A")
    b = await _category(client, owner, "B")
    i1 = (await _item(client, owner, name="One", category_id=a))["id"]
    i2 = (await _item(client, owner, name="Two", category_id=a))["id"]
    i3 = (await _item(client, owner, name="Three"))["id"]

    res = await client.post(
        "/api/v1/menu/reorder",
        headers=owner.headers,
        json={"categories": [b, a], "items": {b: [i2, i3], a: [i1], "uncategorized": []}},
    )
    assert res.status_code == 204, res.text
    cats = (await client.get("/api/v1/menu/categories", headers=owner.headers)).json()
    assert [c["id"] for c in cats] == [b, a]
    items = {
        i["id"]: i for i in (await client.get("/api/v1/menu/items", headers=owner.headers)).json()
    }
    assert (items[i2]["category_id"], items[i2]["position"]) == (b, 0)
    assert (items[i3]["category_id"], items[i3]["position"]) == (b, 1)
    assert (items[i1]["category_id"], items[i1]["position"]) == (a, 0)

    res = await client.post(
        "/api/v1/menu/reorder", headers=owner.headers, json={"items": {a: [i1], b: [i1]}}
    )
    assert res.status_code == 422


async def test_item_image_upload(client: AsyncClient) -> None:
    owner = await signup_owner(client)
    item = await _item(client, owner)
    buf = io.BytesIO()
    Image.new("RGB", (800, 600), "white").save(buf, format="PNG")
    res = await client.post(
        f"/api/v1/menu/items/{item['id']}/image",
        headers=owner.headers,
        files={"file": ("cake.png", buf.getvalue(), "image/png")},
    )
    assert res.status_code == 200, res.text
    assert res.json()["image_url"].endswith(".webp")
    assert f"/tenants/{owner.tenant_id}/items/" in res.json()["image_url"]


async def test_staff_can_read_but_not_write_menu(client: AsyncClient) -> None:
    owner = await signup_owner(client)
    staff = await add_staff(client, owner)
    await _item(client, owner)
    assert (await client.get("/api/v1/menu/items", headers=staff.headers)).status_code == 200
    assert (await client.get("/api/v1/menu/categories", headers=staff.headers)).status_code == 200
    res = await client.post(
        "/api/v1/menu/items", headers=staff.headers, json={"name": "X", "price_paise": 100}
    )
    assert res.status_code == 403
    assert (await client.get("/api/v1/faq", headers=staff.headers)).status_code == 403


async def test_faq_crud_and_reorder(client: AsyncClient) -> None:
    owner = await signup_owner(client)
    ids = []
    for q in ("Do you deliver?", "Is everything eggless?"):
        res = await client.post(
            "/api/v1/faq", headers=owner.headers, json={"question": q, "answer": "Yes."}
        )
        assert res.status_code == 201
        ids.append(res.json()["id"])
    res = await client.post("/api/v1/faq/reorder", headers=owner.headers, json={"ids": ids[::-1]})
    assert res.status_code == 204
    faq = (await client.get("/api/v1/faq", headers=owner.headers)).json()
    assert [f["id"] for f in faq] == ids[::-1]

    res = await client.patch(
        f"/api/v1/faq/{ids[0]}", headers=owner.headers, json={"answer": "Within 5 km."}
    )
    assert res.json()["answer"] == "Within 5 km."
    assert (
        await client.post(
            "/api/v1/faq", headers=owner.headers, json={"question": "?", "answer": ""}
        )
    ).status_code == 422
    assert (await client.delete(f"/api/v1/faq/{ids[1]}", headers=owner.headers)).status_code == 204
    assert len((await client.get("/api/v1/faq", headers=owner.headers)).json()) == 1


# --- Public storefront -------------------------------------------------------------------------


async def test_public_storefront_excludes_deleted_and_unavailable(client: AsyncClient) -> None:
    owner = await signup_owner(client, business="Demo Bakery", slug="demo-bakery-test")
    cakes = await _category(client, owner, "Cakes")
    await _category(client, owner, "Empty")
    shown = await _item(client, owner, name="Shown", category_id=cakes)
    hidden = await _item(client, owner, name="Hidden", category_id=cakes)
    deleted = await _item(client, owner, name="Deleted", category_id=cakes)
    loose = await _item(client, owner, name="Loose")
    await client.patch(
        f"/api/v1/menu/items/{hidden['id']}", headers=owner.headers, json={"is_available": False}
    )
    await client.delete(f"/api/v1/menu/items/{deleted['id']}", headers=owner.headers)

    res = await client.get("/api/v1/public/b/Demo-Bakery-Test")
    assert res.status_code == 200
    body = res.json()
    assert body["business"]["name"] == "Demo Bakery"
    assert "order_seq" not in body["business"]
    assert "email" not in body["business"]
    assert [c["name"] for c in body["categories"]] == ["Cakes", "Other"]
    assert [i["id"] for i in body["categories"][0]["items"]] == [shown["id"]]
    assert [i["id"] for i in body["categories"][1]["items"]] == [loose["id"]]
    assert "is_available" not in body["categories"][0]["items"][0]


async def test_public_storefront_cache_is_invalidated_on_change(client: AsyncClient) -> None:
    owner = await signup_owner(client)
    item = await _item(client, owner, name="Before")
    url = f"/api/v1/public/b/{owner.slug}"
    assert (await client.get(url)).json()["categories"][0]["items"][0]["name"] == "Before"

    await client.patch(
        f"/api/v1/menu/items/{item['id']}", headers=owner.headers, json={"name": "After"}
    )
    assert (await client.get(url)).json()["categories"][0]["items"][0]["name"] == "After"

    await client.patch("/api/v1/tenant", headers=owner.headers, json={"accepts_orders": False})
    assert (await client.get(url)).json()["business"]["accepts_orders"] is False


async def test_public_storefront_unknown_slug(client: AsyncClient) -> None:
    res = await client.get("/api/v1/public/b/nope-not-here")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.usefixtures("rate_limits_on")
async def test_public_storefront_rate_limited(client: AsyncClient) -> None:
    owner = await signup_owner(client)
    statuses = [
        (await client.get(f"/api/v1/public/b/{owner.slug}")).status_code for _ in range(121)
    ]
    assert statuses[-1] == 429
    assert statuses.count(200) == 120
