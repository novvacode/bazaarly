"""ASGI middleware: request ID, access log with duration, security headers."""

from __future__ import annotations

import time
import uuid

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

log = structlog.get_logger("access")

REQUEST_ID_HEADER = b"x-request-id"
MAX_BODY_BYTES = 5 * 1024 * 1024  # uploads are capped at 2 MB; nothing legitimate is larger

SECURITY_HEADERS: list[tuple[bytes, bytes]] = [
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"strict-origin-when-cross-origin"),
    (b"x-frame-options", b"DENY"),
    (b"cross-origin-opener-policy", b"same-origin"),
]


class RequestContextMiddleware:
    """Assigns/propagates `X-Request-ID`, binds it to the log context, logs each request."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = dict(scope["headers"]).get(REQUEST_ID_HEADER, b"").decode("latin-1")
        request_id = incoming[:64] if incoming.isprintable() and incoming else uuid.uuid4().hex
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        scope.setdefault("state", {})["request_id"] = request_id

        start = time.perf_counter()
        status = 500

        declared = dict(scope["headers"]).get(b"content-length")
        if declared is not None and (not declared.isdigit() or int(declared) > MAX_BODY_BYTES):
            await _reject_too_large(send, request_id)
            status = 413
            log.info("request", method=scope.get("method"), route=scope.get("path"), status=413)
            return

        async def send_wrapper(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = list(message.get("headers", []))
                headers.append((REQUEST_ID_HEADER, request_id.encode()))
                existing = {k.lower() for k, _ in headers}
                headers += [(k, v) for k, v in SECURITY_HEADERS if k not in existing]
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            path = scope.get("path", "")
            if not path.endswith("/health"):
                log.info(
                    "request",
                    method=scope.get("method"),
                    route=path,
                    status=status,
                    duration_ms=round((time.perf_counter() - start) * 1000, 1),
                )


async def _reject_too_large(send: Send, request_id: str) -> None:
    body = b'{"error":{"code":"PAYLOAD_TOO_LARGE","message":"Request body too large","details":{}}}'
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                (REQUEST_ID_HEADER, request_id.encode()),
                *SECURITY_HEADERS,
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})
