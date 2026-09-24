"""Tenant isolation harness (SPEC §7.7).

Every tenant-scoped route is called as tenant A's owner against tenant B's resources and must
answer 404 (or an empty/A-only result for list routes, or leave B untouched for writes).

`test_every_tenant_scoped_route_is_covered` enumerates the app's routes: adding a new
tenant-scoped route without registering a case below fails the build.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import pytest
from httpx import AsyncClient

from app.main import create_app
from tests.factories import Actor, signup_owner

# Route prefixes that are not tenant-scoped by an access token.
EXEMPT_PREFIXES = (
    "/health",
    "/api/v1/health",
    "/api/v1/auth/",
    "/api/v1/public/",
    "/api/v1/webhooks/",
    "/api/v1/admin/",
)


@dataclass
class World:
    a: Actor
    b: Actor
    b_ids: dict[str, str] = field(default_factory=dict)


Check = Callable[[AsyncClient, World], Awaitable[None]]
CASES: dict[tuple[str, str], Check] = {}


def case(method: str, path: str) -> Callable[[Check], Check]:
    def register(fn: Check) -> Check:
        CASES[(method, path)] = fn
        return fn

    return register


def _path(template: str, **ids: str) -> str:
    return template.format(**ids)


async def _expect_404(client: AsyncClient, w: World, method: str, url: str, **kw: Any) -> None:
    res = await client.request(method, url, headers=w.a.headers, **kw)
    assert res.status_code == 404, f"{method} {url} -> {res.status_code} {res.text}"
    assert res.json()["error"]["code"] in {"NOT_FOUND"}


# --- Tenant & team -----------------------------------------------------------------------------


@case("GET", "/api/v1/tenant")
async def _get_tenant(client: AsyncClient, w: World) -> None:
    res = await client.get("/api/v1/tenant", headers=w.a.headers)
    assert res.json()["id"] == str(w.a.tenant_id)


@case("PATCH", "/api/v1/tenant")
async def _patch_tenant(client: AsyncClient, w: World) -> None:
    await client.patch("/api/v1/tenant", headers=w.a.headers, json={"name": "Renamed A"})
    res = await client.get("/api/v1/tenant", headers=w.b.headers)
    assert res.json()["name"] != "Renamed A"


@case("POST", "/api/v1/tenant/logo")
async def _logo(client: AsyncClient, w: World) -> None:
    # Uploading as A only ever writes A's tenant row (the route takes no tenant id).
    before = (await client.get("/api/v1/tenant", headers=w.b.headers)).json()["logo_url"]
    await client.post(
        "/api/v1/tenant/logo", headers=w.a.headers, files={"file": ("x.png", b"x", "image/png")}
    )
    after = (await client.get("/api/v1/tenant", headers=w.b.headers)).json()["logo_url"]
    assert before == after


@case("GET", "/api/v1/team")
async def _team(client: AsyncClient, w: World) -> None:
    res = await client.get("/api/v1/team", headers=w.a.headers)
    user_ids = {m["user_id"] for m in res.json()["members"]}
    assert user_ids == {str(w.a.user_id)}


@case("POST", "/api/v1/team/invites")
async def _invite(client: AsyncClient, w: World) -> None:
    await client.post("/api/v1/team/invites", headers=w.a.headers, json={})
    res = await client.get("/api/v1/team", headers=w.b.headers)
    assert res.json()["pending_invites"] == []


@case("DELETE", "/api/v1/team/memberships/{membership_id}")
async def _remove_member(client: AsyncClient, w: World) -> None:
    url = _path("/api/v1/team/memberships/{membership_id}", membership_id=w.b_ids["membership"])
    await _expect_404(client, w, "DELETE", url)


# --- Harness -----------------------------------------------------------------------------------


@pytest.fixture
async def world(client: AsyncClient) -> World:
    a = await signup_owner(client, business="Tenant A")
    b = await signup_owner(client, business="Tenant B")
    w = World(a=a, b=b)
    team = (await client.get("/api/v1/team", headers=b.headers)).json()
    w.b_ids["membership"] = team["members"][0]["membership_id"]
    return w


def _tenant_scoped_routes() -> set[tuple[str, str]]:
    schema = create_app().openapi()
    routes: set[tuple[str, str]] = set()
    for path, ops in schema["paths"].items():
        if path.startswith(EXEMPT_PREFIXES):
            continue
        for method in ops:
            routes.add((method.upper(), path))
    return routes


def test_every_tenant_scoped_route_is_covered() -> None:
    routes = _tenant_scoped_routes()
    missing = routes - CASES.keys()
    stale = CASES.keys() - routes
    assert not missing, f"Add isolation cases for: {sorted(missing)}"
    assert not stale, f"Isolation cases for routes that no longer exist: {sorted(stale)}"


@pytest.mark.parametrize("route", sorted(CASES), ids=lambda r: f"{r[0]} {r[1]}")
async def test_cross_tenant_access_is_denied(
    route: tuple[str, str], client: AsyncClient, world: World
) -> None:
    await CASES[route](client, world)
