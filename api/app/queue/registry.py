"""Handler registry: `@handler("notifications.order_placed_owner", max_attempts=5, timeout=30)`."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.queue.context import JobContext

HandlerFn = Callable[["JobContext", dict[str, Any]], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class HandlerSpec:
    type: str
    fn: HandlerFn
    max_attempts: int
    timeout_s: float


REGISTRY: dict[str, HandlerSpec] = {}


def handler(
    job_type: str, *, max_attempts: int = 5, timeout: float = 30
) -> Callable[[HandlerFn], HandlerFn]:
    def register(fn: HandlerFn) -> HandlerFn:
        if job_type in REGISTRY:
            raise ValueError(f"Duplicate handler for {job_type!r}")
        REGISTRY[job_type] = HandlerSpec(job_type, fn, max_attempts, timeout)
        return fn

    return register


def get(job_type: str) -> HandlerSpec | None:
    return REGISTRY.get(job_type)


def max_attempts_for(job_type: str, default: int) -> int:
    spec = REGISTRY.get(job_type)
    return spec.max_attempts if spec else default
