"""Job envelope carried through Redis (SPEC §12.3)."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class Envelope:
    type: str
    payload: dict[str, Any]
    idempotency_key: str
    max_attempts: int = 5
    attempt: int = 0
    job_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    enqueued_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_json(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"), sort_keys=True)

    @classmethod
    def from_json(cls, raw: str | bytes) -> Envelope:
        data = json.loads(raw)
        return cls(
            type=data["type"],
            payload=data.get("payload") or {},
            idempotency_key=data["idempotency_key"],
            max_attempts=int(data.get("max_attempts", 5)),
            attempt=int(data.get("attempt", 0)),
            job_id=data.get("job_id") or str(uuid.uuid4()),
            enqueued_at=data.get("enqueued_at") or datetime.now(UTC).isoformat(),
        )

    def next_attempt(self) -> Envelope:
        return replace(self, attempt=self.attempt + 1)

    def fresh(self) -> Envelope:
        """For manual retries from the dead-letter queue: attempt counter reset."""
        return replace(self, attempt=0)
