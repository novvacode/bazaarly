from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from app.schemas.common import Schema


class AdminTenantOut(Schema):
    id: uuid.UUID
    name: str
    slug: str
    email: str | None
    accepts_orders: bool
    created_at: datetime
    members: int
    orders: int
    orders_last_7_days: int


class ConsumerOut(Schema):
    name: str
    pending: int
    idle_ms: int


class JobStatsOut(Schema):
    stream_length: int
    pending: int
    delayed: int
    dead: int
    consumers: list[ConsumerOut]
    counters: dict[str, int]


class DeadJobOut(Schema):
    entry_id: str
    type: str
    payload: dict[str, Any]
    attempt: int
    job_id: str | None
    idempotency_key: str | None
    error_type: str | None
    error: str | None
    traceback: str | None
    failed_at: str | None
