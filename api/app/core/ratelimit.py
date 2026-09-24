"""Fixed-window rate limiter on Redis (INCR + EXPIRE), SPEC §17."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from fastapi import Request

from app.config import get_settings
from app.core.errors import RATE_LIMITED, AppError
from app.redis import get_redis


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def hit(name: str, key: str, limit: int, window_s: int) -> None:
    """Count one hit for `(name, key)`; raise 429 with `Retry-After` when over `limit`."""
    if not get_settings().rate_limit_enabled:
        return
    window = int(time.time()) // window_s
    redis_key = f"bz:rl:{name}:{key}:{window}"
    redis = get_redis()
    pipe = redis.pipeline(transaction=True)
    pipe.incr(redis_key)
    pipe.expire(redis_key, window_s + 1, nx=True)
    count, _ = await pipe.execute()
    if int(count) > limit:
        retry_after = window_s - int(time.time()) % window_s
        raise AppError(
            RATE_LIMITED,
            "Too many requests, please slow down",
            429,
            details={"retry_after": retry_after},
            headers={"Retry-After": str(retry_after)},
        )


def limit_by_ip(name: str, limit: int, window_s: int = 60) -> Callable[[Request], Awaitable[None]]:
    """FastAPI dependency factory: `Depends(limit_by_ip("signup", 3))`."""

    async def dependency(request: Request) -> None:
        await hit(name, client_ip(request), limit, window_s)

    return dependency
