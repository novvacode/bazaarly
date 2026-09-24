"""Queue observability and dead-letter management (SPEC §12.7)."""

from __future__ import annotations

from typing import Any

from redis.asyncio import Redis
from redis.exceptions import ResponseError

from app.queue import keys
from app.queue.envelope import Envelope
from app.queue.relay import publish


async def stats(redis: Redis) -> dict[str, Any]:
    stream_len = await redis.xlen(keys.JOBS)
    try:
        pending: Any = await redis.xpending(keys.JOBS, keys.GROUP)
        consumers: Any = await redis.xinfo_consumers(keys.JOBS, keys.GROUP)
    except ResponseError:  # stream or group not created yet
        pending, consumers = {"pending": 0}, []
    counters = await redis.hgetall(keys.STATS)
    return {
        "stream_length": int(stream_len),
        "pending": int(pending.get("pending", 0)),
        "delayed": int(await redis.zcard(keys.DELAYED)),
        "dead": int(await redis.xlen(keys.DEAD)),
        "consumers": [
            {"name": c["name"], "pending": int(c["pending"]), "idle_ms": int(c["idle"])}
            for c in consumers
        ],
        "counters": {k: int(v) for k, v in sorted(counters.items())},
    }


def _dead_entry(entry_id: str, fields: dict[str, str]) -> dict[str, Any]:
    try:
        env = Envelope.from_json(fields.get("envelope", ""))
        job = {
            "type": env.type,
            "payload": env.payload,
            "attempt": env.attempt,
            "job_id": env.job_id,
            "idempotency_key": env.idempotency_key,
        }
    except (KeyError, ValueError):
        job = {
            "type": "unknown",
            "payload": {},
            "attempt": 0,
            "job_id": None,
            "idempotency_key": None,
        }
    return {
        "entry_id": entry_id,
        **job,
        "error_type": fields.get("error_type"),
        "error": fields.get("error"),
        "traceback": fields.get("traceback"),
        "failed_at": fields.get("failed_at"),
    }


async def list_dead(redis: Redis, limit: int = 100) -> list[dict[str, Any]]:
    entries: Any = await redis.xrevrange(keys.DEAD, "+", "-", count=limit)
    return [_dead_entry(entry_id, fields) for entry_id, fields in entries]


async def _get_dead(redis: Redis, entry_id: str) -> dict[str, str] | None:
    entries: Any = await redis.xrange(keys.DEAD, entry_id, entry_id)
    return entries[0][1] if entries else None


async def retry_dead(redis: Redis, entry_id: str) -> bool:
    fields = await _get_dead(redis, entry_id)
    if fields is None:
        return False
    envelope = Envelope.from_json(fields["envelope"]).fresh()
    await publish(redis, envelope)
    await redis.xdel(keys.DEAD, entry_id)
    return True


async def delete_dead(redis: Redis, entry_id: str) -> bool:
    return bool(await redis.xdel(keys.DEAD, entry_id))
