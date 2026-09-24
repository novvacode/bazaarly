"""Helpers that create realistic state through the public API (so tests exercise real flows)."""

from __future__ import annotations

import itertools
import uuid
from dataclasses import dataclass, field

from httpx import AsyncClient

PASSWORD = "correct-horse-battery"
_seq = itertools.count(1)


@dataclass
class Actor:
    """A signed-in user acting in one tenant."""

    user_id: uuid.UUID
    tenant_id: uuid.UUID
    slug: str
    email: str
    access_token: str
    refresh_token: str
    role: str = "owner"
    extra: dict[str, object] = field(default_factory=dict)

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"}


def unique(prefix: str) -> str:
    return f"{prefix}{next(_seq)}{uuid.uuid4().hex[:6]}"


async def signup_owner(
    client: AsyncClient, *, business: str | None = None, slug: str | None = None
) -> Actor:
    slug = slug or unique("shop-")
    email = f"{unique('owner')}@example.com"
    res = await client.post(
        "/api/v1/auth/signup",
        json={
            "name": "Owner Person",
            "email": email,
            "password": PASSWORD,
            "business_name": business or f"Business {slug}",
            "slug": slug,
        },
    )
    assert res.status_code == 201, res.text
    body = res.json()
    refresh = res.cookies["bz_refresh"]
    client.cookies.clear()
    return Actor(
        user_id=uuid.UUID(body["user"]["id"]),
        tenant_id=uuid.UUID(body["tenant"]["id"]),
        slug=slug,
        email=email,
        access_token=body["access_token"],
        refresh_token=refresh,
    )


async def add_staff(client: AsyncClient, owner: Actor) -> Actor:
    res = await client.post("/api/v1/team/invites", headers=owner.headers, json={"role": "staff"})
    assert res.status_code == 201, res.text
    token = res.json()["token"]
    email = f"{unique('staff')}@example.com"
    res = await client.post(
        f"/api/v1/auth/invites/{token}/accept",
        json={"email": email, "password": PASSWORD, "name": "Staff Person"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    refresh = res.cookies["bz_refresh"]
    client.cookies.clear()
    return Actor(
        user_id=uuid.UUID(body["user"]["id"]),
        tenant_id=owner.tenant_id,
        slug=owner.slug,
        email=email,
        access_token=body["access_token"],
        refresh_token=refresh,
        role="staff",
    )


def refresh_cookie(token: str) -> dict[str, str]:
    return {"Cookie": f"bz_refresh={token}"}


async def create_item(
    client: AsyncClient,
    owner: Actor,
    name: str = "Test Cake",
    price_paise: int = 50000,
    **extra: object,
) -> str:
    res = await client.post(
        "/api/v1/menu/items",
        headers=owner.headers,
        json={"name": name, "price_paise": price_paise, **extra},
    )
    assert res.status_code == 201, res.text
    return str(res.json()["id"])


def order_body(item_ids: list[str], **overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "idempotency_key": uuid.uuid4().hex,
        "items": [{"menu_item_id": i, "quantity": 1} for i in item_ids],
        "customer_name": "Priya Customer",
        "customer_phone": "9876543210",
        "fulfillment_mode": "pickup",
        "payment_method": "cod",
    }
    body.update(overrides)
    return body


async def place_order(
    client: AsyncClient, slug: str, item_ids: list[str], **overrides: object
) -> dict[str, object]:
    res = await client.post(
        f"/api/v1/public/b/{slug}/orders", json=order_body(item_ids, **overrides)
    )
    assert res.status_code == 201, res.text
    return dict(res.json())


async def order_id_by_code(client: AsyncClient, owner: Actor, code: int) -> str:
    res = await client.get("/api/v1/orders", headers=owner.headers, params={"q": str(code)})
    return str(next(o["id"] for o in res.json()["items"] if o["code"] == code))
