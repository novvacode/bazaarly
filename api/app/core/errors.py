"""Error codes and the uniform error envelope (SPEC §9).

Every error response has the shape
`{"error": {"code": "UPPER_SNAKE", "message": "...", "details": {...}}}`.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = structlog.get_logger()

# --- Error codes -----------------------------------------------------------------------------
VALIDATION_ERROR = "VALIDATION_ERROR"
NOT_FOUND = "NOT_FOUND"
UNAUTHORIZED = "UNAUTHORIZED"
FORBIDDEN = "FORBIDDEN"
RATE_LIMITED = "RATE_LIMITED"
INTERNAL_ERROR = "INTERNAL_ERROR"
CONFLICT = "CONFLICT"

INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
EMAIL_TAKEN = "EMAIL_TAKEN"
SLUG_TAKEN = "SLUG_TAKEN"
SLUG_INVALID = "SLUG_INVALID"
WEAK_PASSWORD = "WEAK_PASSWORD"
REFRESH_INVALID = "REFRESH_INVALID"
REFRESH_REUSED = "REFRESH_REUSED"
INVITE_INVALID = "INVITE_INVALID"
ALREADY_MEMBER = "ALREADY_MEMBER"
LAST_OWNER = "LAST_OWNER"

UPLOAD_INVALID = "UPLOAD_INVALID"
UPLOAD_TOO_LARGE = "UPLOAD_TOO_LARGE"

STORE_CLOSED = "STORE_CLOSED"
ORDER_INVALID_TRANSITION = "ORDER_INVALID_TRANSITION"
ORDER_ITEMS_INVALID = "ORDER_ITEMS_INVALID"
ORDER_BELOW_MINIMUM = "ORDER_BELOW_MINIMUM"
FULFILLMENT_INVALID = "FULFILLMENT_INVALID"
PHONE_INVALID = "PHONE_INVALID"
NOT_COD_ORDER = "NOT_COD_ORDER"
ALREADY_PAID = "ALREADY_PAID"

PAYMENT_PROVIDER_ERROR = "PAYMENT_PROVIDER_ERROR"
PAYMENT_SIGNATURE_INVALID = "PAYMENT_SIGNATURE_INVALID"
WEBHOOK_SIGNATURE_INVALID = "WEBHOOK_SIGNATURE_INVALID"

ASSISTANT_UNAVAILABLE = "ASSISTANT_UNAVAILABLE"

_STATUS_CODES = {
    400: "BAD_REQUEST",
    401: UNAUTHORIZED,
    403: FORBIDDEN,
    404: NOT_FOUND,
    405: "METHOD_NOT_ALLOWED",
    409: CONFLICT,
    413: UPLOAD_TOO_LARGE,
    422: VALIDATION_ERROR,
    429: RATE_LIMITED,
}


class AppError(Exception):
    """An expected, client-facing error. Raise from services; rendered by the handler below."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        self.headers = headers


def not_found(what: str = "Resource") -> AppError:
    return AppError(NOT_FOUND, f"{what} not found", 404)


def error_body(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or {}}}


async def _app_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    return JSONResponse(
        error_body(exc.code, exc.message, exc.details),
        status_code=exc.status_code,
        headers=exc.headers,
    )


async def _validation_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    fields: dict[str, str] = {}
    for err in exc.errors():
        loc = [str(p) for p in err.get("loc", ()) if p not in ("body", "query", "path")]
        fields[".".join(loc) or "body"] = str(err.get("msg", "invalid"))
    return JSONResponse(
        error_body(VALIDATION_ERROR, "Request validation failed", {"fields": fields}),
        status_code=422,
    )


async def _http_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    code = _STATUS_CODES.get(exc.status_code, "HTTP_ERROR")
    message = exc.detail if isinstance(exc.detail, str) else code.replace("_", " ").title()
    return JSONResponse(error_body(code, message), status_code=exc.status_code, headers=exc.headers)


async def _unhandled_handler(_: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled_error", exc_info=exc)
    return JSONResponse(error_body(INTERNAL_ERROR, "Something went wrong"), status_code=500)


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_handler)
    app.add_exception_handler(StarletteHTTPException, _http_handler)
    app.add_exception_handler(Exception, _unhandled_handler)
