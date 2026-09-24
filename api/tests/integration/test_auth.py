from __future__ import annotations

import asyncio

import pytest
from httpx import AsyncClient

from app.core.security import decode_access_token
from tests.factories import PASSWORD, add_staff, refresh_cookie, signup_owner


async def test_signup_creates_user_tenant_and_owner_membership(client: AsyncClient) -> None:
    res = await client.post(
        "/api/v1/auth/signup",
        json={
            "name": "Asha",
            "email": "Asha@Example.com",
            "password": PASSWORD,
            "business_name": "Asha's Bakes",
            "slug": "Ashas-Bakes",
        },
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["tenant"]["slug"] == "ashas-bakes"
    assert body["tenant"]["role"] == "owner"
    assert body["token_type"] == "bearer"
    cookie = res.headers["set-cookie"]
    assert "bz_refresh=" in cookie
    assert "HttpOnly" in cookie
    assert "Path=/api/v1/auth" in cookie
    assert "SameSite=lax" in cookie

    claims = decode_access_token(body["access_token"])
    assert str(claims.tenant_id) == body["tenant"]["id"]
    assert claims.role == "owner"


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("password", "short", "WEAK_PASSWORD"),
        ("password", "iloveyou", "WEAK_PASSWORD"),
        ("slug", "admin", "SLUG_INVALID"),
        ("slug", "-bad", "SLUG_INVALID"),
        ("slug", "a", "SLUG_INVALID"),
        ("email", "not-an-email", "VALIDATION_ERROR"),
    ],
)
async def test_signup_validation(client: AsyncClient, field: str, value: str, code: str) -> None:
    payload = {
        "name": "A",
        "email": "a@example.com",
        "password": PASSWORD,
        "business_name": "B",
        "slug": "good-slug",
    }
    payload[field] = value
    res = await client.post("/api/v1/auth/signup", json=payload)
    assert res.status_code == 422
    assert res.json()["error"]["code"] == code


async def test_signup_rejects_duplicate_email_and_slug(client: AsyncClient) -> None:
    owner = await signup_owner(client, slug="taken-slug")
    res = await client.post(
        "/api/v1/auth/signup",
        json={
            "name": "X",
            "email": owner.email.upper(),
            "password": PASSWORD,
            "business_name": "X",
            "slug": "other-slug",
        },
    )
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "EMAIL_TAKEN"

    res = await client.post(
        "/api/v1/auth/signup",
        json={
            "name": "X",
            "email": "new@example.com",
            "password": PASSWORD,
            "business_name": "X",
            "slug": "taken-slug",
        },
    )
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "SLUG_TAKEN"


async def test_login_success_and_failure(client: AsyncClient) -> None:
    owner = await signup_owner(client)
    res = await client.post("/api/v1/auth/login", json={"email": owner.email, "password": PASSWORD})
    assert res.status_code == 200
    assert res.json()["tenant"]["id"] == str(owner.tenant_id)

    for email, pw in [(owner.email, "wrong-password"), ("nobody@example.com", PASSWORD)]:
        res = await client.post("/api/v1/auth/login", json={"email": email, "password": pw})
        assert res.status_code == 401
        assert res.json()["error"]["code"] == "INVALID_CREDENTIALS"


async def test_me_returns_memberships(client: AsyncClient) -> None:
    owner = await signup_owner(client, business="Tiffin Co")
    res = await client.get("/api/v1/auth/me", headers=owner.headers)
    assert res.status_code == 200
    body = res.json()
    assert body["active_tenant"]["name"] == "Tiffin Co"
    assert [m["role"] for m in body["memberships"]] == ["owner"]


async def test_protected_route_requires_valid_token(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/auth/me")).status_code == 401
    res = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer nope"})
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "UNAUTHORIZED"


async def test_refresh_rotates_token(client: AsyncClient) -> None:
    owner = await signup_owner(client)
    res = await client.post("/api/v1/auth/refresh", headers=refresh_cookie(owner.refresh_token))
    assert res.status_code == 200, res.text
    new_token = res.cookies["bz_refresh"]
    client.cookies.clear()
    assert new_token != owner.refresh_token
    assert res.json()["tenant"]["id"] == str(owner.tenant_id)

    # The new token works.
    res = await client.post("/api/v1/auth/refresh", headers=refresh_cookie(new_token))
    assert res.status_code == 200
    client.cookies.clear()


async def test_refresh_reuse_revokes_whole_family(client: AsyncClient) -> None:
    owner = await signup_owner(client)
    first = owner.refresh_token
    res = await client.post("/api/v1/auth/refresh", headers=refresh_cookie(first))
    second = res.cookies["bz_refresh"]
    client.cookies.clear()

    # An attacker replays the old token: reuse detected, family revoked, cookie cleared.
    res = await client.post("/api/v1/auth/refresh", headers=refresh_cookie(first))
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "REFRESH_REUSED"
    assert 'bz_refresh=""' in res.headers["set-cookie"] or "Max-Age=0" in res.headers["set-cookie"]
    client.cookies.clear()

    # The legitimate user's newer token is now dead too.
    res = await client.post("/api/v1/auth/refresh", headers=refresh_cookie(second))
    assert res.status_code == 401
    client.cookies.clear()


async def test_refresh_without_cookie(client: AsyncClient) -> None:
    res = await client.post("/api/v1/auth/refresh")
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "REFRESH_INVALID"


async def test_logout_revokes_refresh_token(client: AsyncClient) -> None:
    owner = await signup_owner(client)
    res = await client.post("/api/v1/auth/logout", headers=refresh_cookie(owner.refresh_token))
    assert res.status_code == 204
    client.cookies.clear()
    res = await client.post("/api/v1/auth/refresh", headers=refresh_cookie(owner.refresh_token))
    assert res.status_code == 401


async def test_switch_tenant_and_refresh_keeps_it(client: AsyncClient) -> None:
    a = await signup_owner(client)
    b = await signup_owner(client)
    # Make A's owner a staff member of B.
    res = await client.post("/api/v1/team/invites", headers=b.headers, json={"role": "staff"})
    token = res.json()["token"]
    res = await client.post(f"/api/v1/auth/invites/{token}/accept", json={}, headers=a.headers)
    assert res.status_code == 200, res.text
    client.cookies.clear()

    res = await client.post(
        "/api/v1/auth/switch-tenant",
        json={"tenant_id": str(b.tenant_id)},
        headers={**a.headers, **refresh_cookie(a.refresh_token)},
    )
    assert res.status_code == 200, res.text
    assert res.json()["tenant"]["role"] == "staff"

    res = await client.post("/api/v1/auth/refresh", headers=refresh_cookie(a.refresh_token))
    assert res.json()["tenant"]["id"] == str(b.tenant_id)
    client.cookies.clear()


async def test_switch_to_foreign_tenant_is_404(client: AsyncClient) -> None:
    a = await signup_owner(client)
    b = await signup_owner(client)
    res = await client.post(
        "/api/v1/auth/switch-tenant", json={"tenant_id": str(b.tenant_id)}, headers=a.headers
    )
    assert res.status_code == 404


async def test_removed_member_token_stops_working(client: AsyncClient) -> None:
    owner = await signup_owner(client)
    staff = await add_staff(client, owner)
    team = (await client.get("/api/v1/team", headers=owner.headers)).json()
    staff_membership = next(m for m in team["members"] if m["role"] == "staff")

    # Warm the membership cache, then remove: the cache must be invalidated.
    res = await client.get("/api/v1/auth/me", headers=staff.headers)
    assert res.status_code == 200
    res = await client.delete(
        f"/api/v1/team/memberships/{staff_membership['membership_id']}", headers=owner.headers
    )
    assert res.status_code == 204
    res = await client.get("/api/v1/team", headers=staff.headers)
    assert res.status_code == 401


# --- Rate limits -------------------------------------------------------------------------------


@pytest.mark.usefixtures("rate_limits_on")
async def test_login_rate_limited_per_ip_and_email(client: AsyncClient) -> None:
    body = {"email": "victim@example.com", "password": "wrong-password"}
    codes = [(await client.post("/api/v1/auth/login", json=body)).status_code for _ in range(6)]
    assert codes == [401] * 5 + [429]
    res = await client.post("/api/v1/auth/login", json=body)
    assert res.json()["error"]["code"] == "RATE_LIMITED"
    assert int(res.headers["retry-after"]) > 0

    # A different email from the same IP has its own bucket.
    other = {"email": "other@example.com", "password": "wrong-password"}
    assert (await client.post("/api/v1/auth/login", json=other)).status_code == 401


@pytest.mark.usefixtures("rate_limits_on")
async def test_signup_rate_limited_per_ip(client: AsyncClient) -> None:
    async def attempt(i: int) -> int:
        res = await client.post(
            "/api/v1/auth/signup",
            json={
                "name": "N",
                "email": f"rl{i}@example.com",
                "password": PASSWORD,
                "business_name": "B",
                "slug": f"rate-limit-{i}",
            },
        )
        return res.status_code

    codes = [await attempt(i) for i in range(4)]
    assert codes == [201, 201, 201, 429]
    client.cookies.clear()


@pytest.mark.usefixtures("rate_limits_on")
async def test_refresh_rate_limited(client: AsyncClient) -> None:
    codes = await asyncio.gather(*[client.post("/api/v1/auth/refresh") for _ in range(31)])
    statuses = sorted(r.status_code for r in codes)
    assert statuses.count(429) == 1
