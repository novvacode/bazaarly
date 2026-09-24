"""Razorpay REST client over httpx (no SDK, so tests mock it with respx). SPEC §11."""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import get_settings


class RazorpayError(Exception):
    pass


def _hmac_hex(secret: str, message: bytes) -> str:
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def payment_signature(order_id: str, payment_id: str, secret: str) -> str:
    """Signature Razorpay Checkout returns: HMAC_SHA256(order_id + "|" + payment_id)."""
    return _hmac_hex(secret, f"{order_id}|{payment_id}".encode())


def verify_payment_signature(order_id: str, payment_id: str, signature: str, secret: str) -> bool:
    expected = payment_signature(order_id, payment_id, secret)
    return hmac.compare_digest(expected, signature or "")


def webhook_signature(raw_body: bytes, secret: str) -> str:
    return _hmac_hex(secret, raw_body)


def verify_webhook_signature(raw_body: bytes, signature: str, secret: str) -> bool:
    """Verify `X-Razorpay-Signature` against the raw request body (constant-time)."""
    if not secret:
        return False
    return hmac.compare_digest(webhook_signature(raw_body, secret), signature or "")


@dataclass(frozen=True, slots=True)
class ProviderOrder:
    id: str
    amount: int
    raw: dict[str, Any]


class RazorpayClient:
    def __init__(self, key_id: str, key_secret: str, base_url: str) -> None:
        self.key_id = key_id
        self._auth = (key_id, key_secret)
        self._base = base_url.rstrip("/")

    async def _request(self, method: str, path: str, **kw: Any) -> Any:
        try:
            async with httpx.AsyncClient(timeout=10, auth=self._auth) as client:
                res = await client.request(method, f"{self._base}{path}", **kw)
        except httpx.HTTPError as exc:
            raise RazorpayError(f"Razorpay unreachable: {exc}") from exc
        if res.status_code >= 400:
            raise RazorpayError(f"Razorpay {method} {path} → {res.status_code}: {res.text[:300]}")
        return res.json()

    async def create_order(
        self, *, amount_paise: int, receipt: str, notes: dict[str, str]
    ) -> ProviderOrder:
        data = await self._request(
            "POST",
            "/v1/orders",
            json={
                "amount": amount_paise,
                "currency": "INR",
                "receipt": receipt[:40],
                "notes": notes,
            },
        )
        return ProviderOrder(id=data["id"], amount=int(data["amount"]), raw=data)

    async def order_payments(self, provider_order_id: str) -> list[dict[str, Any]]:
        data = await self._request("GET", f"/v1/orders/{provider_order_id}/payments")
        return list(data.get("items", []))


def get_razorpay() -> RazorpayClient:
    s = get_settings()
    return RazorpayClient(s.razorpay_key_id, s.razorpay_key_secret, s.razorpay_base_url)


def online_payments_configured() -> bool:
    s = get_settings()
    return bool(s.razorpay_key_id and s.razorpay_key_secret)
