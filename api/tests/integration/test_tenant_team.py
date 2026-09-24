from __future__ import annotations

import io

from httpx import AsyncClient
from PIL import Image

from app.integrations.storage import MemoryStorage
from tests.factories import PASSWORD, add_staff, signup_owner


def _png(size: tuple[int, int] = (2400, 1200), exif: bool = False) -> bytes:
    img = Image.new("RGB", size, (200, 120, 40))
    out = io.BytesIO()
    if exif:
        ex = Image.Exif()
        ex[0x010F] = "SecretCameraMaker"
        img.save(out, format="JPEG", exif=ex)
    else:
        img.save(out, format="PNG")
    return out.getvalue()


async def test_get_and_patch_tenant(client: AsyncClient) -> None:
    owner = await signup_owner(client)
    res = await client.get("/api/v1/tenant", headers=owner.headers)
    assert res.status_code == 200
    assert res.json()["fulfillment_modes"] == ["pickup"]
    assert res.json()["timezone"] == "Asia/Kolkata"

    res = await client.patch(
        "/api/v1/tenant",
        headers=owner.headers,
        json={
            "phone": "98765 43210",
            "fulfillment_modes": ["delivery", "pickup", "pickup"],
            "delivery_areas": ["Koramangala", "koramangala", "HSR Layout"],
            "min_order_paise": 20000,
            "delivery_fee_paise": 4000,
            "hours_text": "Tue-Sun, 10am-8pm",
            "accepts_orders": False,
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["phone"] == "+919876543210"
    assert body["fulfillment_modes"] == ["delivery", "pickup"]
    assert body["delivery_areas"] == ["Koramangala", "HSR Layout"]
    assert body["accepts_orders"] is False


async def test_patch_tenant_validation(client: AsyncClient) -> None:
    owner = await signup_owner(client)
    cases = [
        {"timezone": "Mars/Olympus"},
        {"fulfillment_modes": []},
        {"fulfillment_modes": ["drone"]},
        {"min_order_paise": -1},
        {"phone": "12"},
        {"slug": "new-slug"},
        {"name": None},
    ]
    for payload in cases:
        res = await client.patch("/api/v1/tenant", headers=owner.headers, json=payload)
        assert res.status_code == 422, payload


async def test_staff_cannot_manage_tenant_or_team(client: AsyncClient) -> None:
    owner = await signup_owner(client)
    staff = await add_staff(client, owner)
    for method, url in [
        ("GET", "/api/v1/tenant"),
        ("PATCH", "/api/v1/tenant"),
        ("GET", "/api/v1/team"),
        ("POST", "/api/v1/team/invites"),
    ]:
        res = await client.request(method, url, headers=staff.headers, json={})
        assert res.status_code == 403, (method, url)


async def test_logo_upload_normalises_to_webp(client: AsyncClient, storage: MemoryStorage) -> None:
    owner = await signup_owner(client)
    res = await client.post(
        "/api/v1/tenant/logo",
        headers=owner.headers,
        files={"file": ("logo.jpg", _png(exif=True), "image/jpeg")},
    )
    assert res.status_code == 200, res.text
    url = res.json()["logo_url"]
    key = url.removeprefix(storage.base_url + "/")
    assert key.startswith(f"tenants/{owner.tenant_id}/logo/")
    assert key.endswith(".webp")
    data, content_type = storage.objects[key]
    assert content_type == "image/webp"
    img = Image.open(io.BytesIO(data))
    assert img.format == "WEBP"
    assert max(img.size) == 1200
    assert not img.getexif()


async def test_logo_upload_rejects_bad_files(client: AsyncClient) -> None:
    owner = await signup_owner(client)
    res = await client.post(
        "/api/v1/tenant/logo",
        headers=owner.headers,
        files={"file": ("logo.png", b"not really an image", "image/png")},
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "UPLOAD_INVALID"

    gif = io.BytesIO()
    Image.new("RGB", (10, 10)).save(gif, format="GIF")
    res = await client.post(
        "/api/v1/tenant/logo",
        headers=owner.headers,
        files={"file": ("logo.png", gif.getvalue(), "image/png")},
    )
    assert res.status_code == 422

    res = await client.post(
        "/api/v1/tenant/logo",
        headers=owner.headers,
        files={"file": ("big.png", b"\x89PNG" + b"0" * (2 * 1024 * 1024), "image/png")},
    )
    assert res.status_code == 413
    assert res.json()["error"]["code"] == "UPLOAD_TOO_LARGE"


async def test_invite_lifecycle(client: AsyncClient) -> None:
    owner = await signup_owner(client, business="Chai Corner")
    res = await client.post("/api/v1/team/invites", headers=owner.headers, json={})
    assert res.status_code == 201
    invite = res.json()
    assert invite["url"].startswith("http://localhost:3000/invite/")

    team = (await client.get("/api/v1/team", headers=owner.headers)).json()
    assert len(team["pending_invites"]) == 1

    res = await client.get(f"/api/v1/auth/invites/{invite['token']}")
    assert res.status_code == 200
    assert res.json()["business_name"] == "Chai Corner"
    assert res.json()["role"] == "staff"

    # A brand-new user needs a name.
    res = await client.post(
        f"/api/v1/auth/invites/{invite['token']}/accept",
        json={"email": "new-staff@example.com", "password": PASSWORD},
    )
    assert res.status_code == 422

    res = await client.post(
        f"/api/v1/auth/invites/{invite['token']}/accept",
        json={"email": "new-staff@example.com", "password": PASSWORD, "name": "Ravi"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["tenant"]["role"] == "staff"
    client.cookies.clear()

    # One-time use.
    res = await client.get(f"/api/v1/auth/invites/{invite['token']}")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "INVITE_INVALID"

    team = (await client.get("/api/v1/team", headers=owner.headers)).json()
    assert sorted(m["role"] for m in team["members"]) == ["owner", "staff"]
    assert team["pending_invites"] == []


async def test_invite_accept_with_existing_account_checks_password(client: AsyncClient) -> None:
    a = await signup_owner(client)
    b = await signup_owner(client)
    token = (await client.post("/api/v1/team/invites", headers=b.headers, json={})).json()["token"]
    res = await client.post(
        f"/api/v1/auth/invites/{token}/accept",
        json={"email": a.email, "password": "wrong-password"},
    )
    assert res.status_code == 401
    res = await client.post(
        f"/api/v1/auth/invites/{token}/accept", json={"email": a.email, "password": PASSWORD}
    )
    assert res.status_code == 200
    client.cookies.clear()


async def test_invite_accept_by_existing_member_conflicts(client: AsyncClient) -> None:
    owner = await signup_owner(client)
    token = (await client.post("/api/v1/team/invites", headers=owner.headers, json={})).json()[
        "token"
    ]
    res = await client.post(f"/api/v1/auth/invites/{token}/accept", json={}, headers=owner.headers)
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "ALREADY_MEMBER"


async def test_cannot_remove_last_owner(client: AsyncClient) -> None:
    owner = await signup_owner(client)
    team = (await client.get("/api/v1/team", headers=owner.headers)).json()
    membership_id = team["members"][0]["membership_id"]
    res = await client.delete(f"/api/v1/team/memberships/{membership_id}", headers=owner.headers)
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "LAST_OWNER"
