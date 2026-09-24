from httpx import AsyncClient


async def test_liveness(client: AsyncClient) -> None:
    res = await client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


async def test_readiness_checks_db_and_redis(client: AsyncClient) -> None:
    res = await client.get("/api/v1/health/ready")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "checks": {"database": "ok", "redis": "ok"}}


async def test_request_id_is_generated_and_echoed(client: AsyncClient) -> None:
    res = await client.get("/health")
    assert len(res.headers["x-request-id"]) == 32

    res = await client.get("/health", headers={"X-Request-ID": "abc-123"})
    assert res.headers["x-request-id"] == "abc-123"


async def test_security_headers(client: AsyncClient) -> None:
    res = await client.get("/health")
    assert res.headers["x-content-type-options"] == "nosniff"
    assert res.headers["x-frame-options"] == "DENY"


async def test_unknown_route_uses_error_envelope(client: AsyncClient) -> None:
    res = await client.get("/api/v1/nope")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "NOT_FOUND"


async def test_oversized_body_rejected_early(client: AsyncClient) -> None:
    res = await client.post(
        "/api/v1/auth/login",
        content=b"x",
        headers={"Content-Length": str(6 * 1024 * 1024), "Content-Type": "application/json"},
    )
    assert res.status_code == 413
    assert res.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"
