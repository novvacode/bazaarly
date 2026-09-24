"""structlog JSON logging (SPEC §18) with request/tenant context bound via contextvars."""

from __future__ import annotations

import logging
import re
import sys
from typing import Any

import structlog
from structlog.types import EventDict, WrappedLogger

_SENSITIVE_KEYS = {
    "password",
    "password_hash",
    "token",
    "access_token",
    "refresh_token",
    "authorization",
    "cookie",
    "secret",
    "razorpay_signature",
    "api_key",
}
_PHONE_KEYS = {"phone", "customer_phone"}
_PHONE_RE = re.compile(r"\+?\d[\d\s-]{7,}\d")


def mask_phone(value: str) -> str:
    """Keep only the last 4 digits: `+919876543210` → `******3210`."""
    digits = re.sub(r"\D", "", value)
    return "******" + digits[-4:] if len(digits) >= 4 else "****"


def _scrub(_: WrappedLogger, __: str, event_dict: EventDict) -> EventDict:
    for key in list(event_dict):
        lk = key.lower()
        if lk in _SENSITIVE_KEYS or lk.endswith(("_secret", "_token", "_password")):
            event_dict[key] = "[redacted]"
        elif lk in _PHONE_KEYS and isinstance(event_dict[key], str):
            event_dict[key] = mask_phone(event_dict[key])
    event = event_dict.get("event")
    if isinstance(event, str) and _PHONE_RE.search(event):
        event_dict["event"] = _PHONE_RE.sub(lambda m: mask_phone(m.group()), event)
    return event_dict


def configure_logging(level: str = "INFO", *, json: bool = True) -> None:
    lvl = logging.getLevelNamesMapping().get(level.upper(), logging.INFO)
    shared: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _scrub,
    ]
    renderer: Any = structlog.processors.JSONRenderer() if json else structlog.dev.ConsoleRenderer()
    structlog.configure(
        processors=[*shared, structlog.processors.format_exc_info, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(lvl),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=False,
    )
    logging.basicConfig(level=lvl, stream=sys.stdout, format="%(message)s")
    for noisy in ("uvicorn.access", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
