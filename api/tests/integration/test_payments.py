"""Online payments (SPEC §11): signatures, verify, webhooks, idempotent mark_paid, expiry.

Razorpay is never called for real: respx mocks its REST API.
"""

from __future__ import annotations

import asyncio
import itertools
import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
import respx
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_sessionmaker
from app.integrations.email import MemoryEmailSender
from app.integrations.razorpay import (
    payment_signature,
    verify_payment_signature,
    verify_webhook_signature,
    webhook_signature,
)
from app.models.order import Outbox
from app.models.payment import Payment, WebhookEvent
from app.queue import handlers  # noqa: F401
from app.queue.relay import relay_once
from app.queue.worker import Worker
from app.redis import get_redis
from app.services import payments as payment_service
from tests.factories import create_item, order_body, order_id_by_code, signup_owner

RZP = "https://api.razorpay.com"
_ids = itertools.count(1)


class FakeRazorpay:
    def __init__(self, router: respx.MockRouter) -> None:
        self.router = router
        self.captured: dict[str, list[dict[str, Any]]] = {}
        self.fail_create = False
        self.create_route = router.post(f"{RZP}/v1/orders").mock(side_effect=self._create)
        router.get(url__regex=rf"{RZP}/v1/orders/(?P<oid>[^/]+)/payments").mock(
            side_effect=self._payments
        )

    def _create(self, request: httpx.Request) -> httpx.Response:
        if self.fail_create:
            return httpx.Response(500, json={"error": {"description": "down"}})
        body = json.loads(request.content)
        assert request.headers["authorization"].startswith("Basic ")
        oid = f"order_test{next(_ids)}"
        return httpx.Response(
            200, json={"id": oid, "amount": body["amount"], "currency": "INR", "status": "created"}
        )

    def _payments(self, request: httpx.Request, oid: str) -> httpx.Response:
        return httpx.Response(200, json={"count": 0, "items": self.captured.get(oid, [])})


@pytest.fixture
def rzp() -> Iterator[FakeRazorpay]:
    with respx.mock(assert_all_called=False) as router:
        router.route(host="testserver").pass_through()
        yield FakeRazorpay(router)


@pytest.fixture
async def worker() -> Worker:
    w = Worker(get_sessionmaker(), get_redis(), MemoryEmailSender(), name="pay-worker")
    await w.ensure_group()
    return w


async def _drain(w: Worker) -> None:
    await relay_once(get_sessionmaker(), get_redis(), 5)
    while await w.consume_once(block_ms=50):
        pass


async def _shop(client: AsyncClient) -> tuple[Any, str]:
    owner = await signup_owner(client)
    return owner, await create_item(client, owner, "Cake", 65000)


async def _online_order(client: AsyncClient, slug: str, item: str, **kw: Any) -> dict[str, Any]:
    res = await client.post(
        f"/api/v1/public/b/{slug}/orders", json=order_body([item], payment_method="online", **kw)
    )
    assert res.status_code == 201, res.text
    return dict(res.json())


def _signed_verify(params: dict[str, Any], payment_id: str = "pay_1") -> dict[str, str]:
    oid = params["razorpay_order_id"]
    return {
        "razorpay_order_id": oid,
        "razorpay_payment_id": payment_id,
        "razorpay_signature": payment_signature(
            oid, payment_id, get_settings().razorpay_key_secret
        ),
    }


def _webhook(event: str, order_id: str, payment_id: str) -> bytes:
    return json.dumps(
        {
            "event": event,
            "payload": {"payment": {"entity": {"id": payment_id, "order_id": order_id}}},
        }
    ).encode()


async def _post_webhook(
    client: AsyncClient, body: bytes, event_id: str, secret: str | None = None
) -> httpx.Response:
    sig = webhook_signature(body, secret or get_settings().razorpay_webhook_secret)
    return await client.post(
        "/api/v1/webhooks/razorpay",
        content=body,
        headers={
            "X-Razorpay-Signature": sig,
            "X-Razorpay-Event-Id": event_id,
            "Content-Type": "application/json",
        },
    )


async def _jobs(session: AsyncSession, job_type: str) -> list[Outbox]:
    result = await session.execute(select(Outbox).where(Outbox.job_type == job_type))
    return list(result.scalars())


# --- Signatures --------------------------------------------------------------------------------


def test_payment_signature_valid_invalid_tampered() -> None:
    sig = payment_signature("order_1", "pay_1", "secret")
    assert verify_payment_signature("order_1", "pay_1", sig, "secret")
    assert not verify_payment_signature("order_1", "pay_1", sig, "other-secret")
    assert not verify_payment_signature("order_2", "pay_1", sig, "secret")  # tampered order
    assert not verify_payment_signature("order_1", "pay_2", sig, "secret")  # tampered payment
    assert not verify_payment_signature("order_1", "pay_1", "", "secret")


def test_webhook_signature_valid_invalid_tampered() -> None:
    body = b'{"event":"payment.captured"}'
    sig = webhook_signature(body, "whsec")
    assert verify_webhook_signature(body, sig, "whsec")
    assert not verify_webhook_signature(body + b" ", sig, "whsec")
    assert not verify_webhook_signature(body, sig, "other")
    assert not verify_webhook_signature(body, sig, "")


# --- Order creation ----------------------------------------------------------------------------


async def test_online_order_starts_pending_with_checkout_params(
    client: AsyncClient, session: AsyncSession, rzp: FakeRazorpay
) -> None:
    owner, item = await _shop(client)
    out = await _online_order(client, owner.slug, item, customer_email="c@example.com")
    assert out["order"]["status"] == "pending_payment"
    payment = out["payment"]
    assert payment["key_id"] == get_settings().razorpay_key_id
    assert payment["amount_paise"] == 65000
    assert payment["razorpay_order_id"].startswith("order_test")
    assert payment["prefill"] == {
        "name": "Priya Customer",
        "contact": "+919876543210",
        "email": "c@example.com",
    }
    sent = json.loads(rzp.create_route.calls.last.request.content)
    assert sent["notes"]["tenant_id"] == str(owner.tenant_id)

    # No notifications until paid; expiry scheduled ~30 min out.
    assert await _jobs(session, "notifications.order_placed_owner") == []
    (expiry,) = await _jobs(session, "orders.expire_unpaid")
    assert expiry.run_at is not None
    delta = expiry.run_at - datetime.now(UTC)
    assert timedelta(minutes=29) < delta <= timedelta(minutes=30)

    storefront = (await client.get(f"/api/v1/public/b/{owner.slug}")).json()
    assert storefront["business"]["accepts_online_payments"] is True


async def test_idempotent_resubmit_reuses_provider_order(
    client: AsyncClient, rzp: FakeRazorpay
) -> None:
    owner, item = await _shop(client)
    body = order_body([item], payment_method="online")
    first = await client.post(f"/api/v1/public/b/{owner.slug}/orders", json=body)
    second = await client.post(f"/api/v1/public/b/{owner.slug}/orders", json=body)
    assert (first.status_code, second.status_code) == (201, 200)
    assert first.json() == second.json()
    assert rzp.create_route.call_count == 1


async def test_provider_failure_is_502_and_recoverable(
    client: AsyncClient, rzp: FakeRazorpay
) -> None:
    owner, item = await _shop(client)
    rzp.fail_create = True
    body = order_body([item], payment_method="online")
    res = await client.post(f"/api/v1/public/b/{owner.slug}/orders", json=body)
    assert res.status_code == 502
    assert res.json()["error"]["code"] == "PAYMENT_PROVIDER_ERROR"
    rzp.fail_create = False
    res = await client.post(f"/api/v1/public/b/{owner.slug}/orders", json=body)
    assert res.status_code == 200
    assert res.json()["order"]["status"] == "pending_payment"
    assert res.json()["payment"]["razorpay_order_id"]


async def test_online_disabled_without_keys(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, item = await _shop(client)
    monkeypatch.setattr(get_settings(), "razorpay_key_id", "")
    res = await client.post(
        f"/api/v1/public/b/{owner.slug}/orders", json=order_body([item], payment_method="online")
    )
    assert res.status_code == 422


# --- Verify ------------------------------------------------------------------------------------


async def test_verify_marks_paid_and_notifies(
    client: AsyncClient, session: AsyncSession, rzp: FakeRazorpay
) -> None:
    owner, item = await _shop(client)
    out = await _online_order(client, owner.slug, item)
    token = out["order"]["public_token"]

    bad = _signed_verify(out["payment"]) | {"razorpay_signature": "0" * 64}
    res = await client.post(f"/api/v1/public/orders/{token}/payment/verify", json=bad)
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "PAYMENT_SIGNATURE_INVALID"

    res = await client.post(
        f"/api/v1/public/orders/{token}/payment/verify", json=_signed_verify(out["payment"])
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert (body["status"], body["payment_status"]) == ("placed", "paid")
    assert [e["to_status"] for e in body["timeline"]] == ["pending_payment", "placed"]
    assert len(await _jobs(session, "notifications.order_placed_owner")) == 1

    # Verifying again is a no-op.
    res = await client.post(
        f"/api/v1/public/orders/{token}/payment/verify", json=_signed_verify(out["payment"])
    )
    assert res.status_code == 200
    assert len(await _jobs(session, "notifications.order_placed_owner")) == 1


async def test_verify_rejects_other_orders_payment(client: AsyncClient, rzp: FakeRazorpay) -> None:
    owner, item = await _shop(client)
    a = await _online_order(client, owner.slug, item)
    b = await _online_order(client, owner.slug, item)
    # A validly signed payment for order B presented on order A's tracking token.
    res = await client.post(
        f"/api/v1/public/orders/{a['order']['public_token']}/payment/verify",
        json=_signed_verify(b["payment"]),
    )
    assert res.status_code == 404


async def test_payment_params_endpoint(client: AsyncClient, rzp: FakeRazorpay) -> None:
    owner, item = await _shop(client)
    out = await _online_order(client, owner.slug, item)
    token = out["order"]["public_token"]
    res = await client.get(f"/api/v1/public/orders/{token}/payment")
    assert res.json()["razorpay_order_id"] == out["payment"]["razorpay_order_id"]
    await client.post(
        f"/api/v1/public/orders/{token}/payment/verify", json=_signed_verify(out["payment"])
    )
    assert (await client.get(f"/api/v1/public/orders/{token}/payment")).status_code == 409


# --- Webhooks ----------------------------------------------------------------------------------


async def test_webhook_signature_required(client: AsyncClient) -> None:
    body = _webhook("payment.captured", "order_x", "pay_x")
    res = await _post_webhook(client, body, "evt_1", secret="wrong")
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "WEBHOOK_SIGNATURE_INVALID"
    res = await client.post("/api/v1/webhooks/razorpay", content=body)
    assert res.status_code == 400


async def test_webhook_dedupe_and_processing(
    client: AsyncClient, session: AsyncSession, rzp: FakeRazorpay, worker: Worker
) -> None:
    owner, item = await _shop(client)
    out = await _online_order(client, owner.slug, item)
    body = _webhook("payment.captured", out["payment"]["razorpay_order_id"], "pay_w1")

    assert (await _post_webhook(client, body, "evt_1")).json() == {"status": "accepted"}
    assert (await _post_webhook(client, body, "evt_1")).json() == {"status": "duplicate"}
    assert len(await _jobs(session, "payments.process_webhook")) == 1

    await _drain(worker)
    tracked = (await client.get(f"/api/v1/public/orders/{out['order']['public_token']}")).json()
    assert (tracked["status"], tracked["payment_status"]) == ("placed", "paid")
    event = (await session.execute(select(WebhookEvent))).scalar_one()
    assert event.processed_at is not None
    payment = (await session.execute(select(Payment))).scalar_one()
    assert payment.provider_payment_id == "pay_w1"


async def test_duplicate_webhooks_with_new_ids_transition_once(
    client: AsyncClient, session: AsyncSession, rzp: FakeRazorpay, worker: Worker
) -> None:
    owner, item = await _shop(client)
    out = await _online_order(client, owner.slug, item)
    oid = out["payment"]["razorpay_order_id"]
    await _post_webhook(client, _webhook("payment.captured", oid, "pay_d"), "evt_a")
    await _post_webhook(client, _webhook("order.paid", oid, "pay_d"), "evt_b")
    await _drain(worker)
    assert len(await _jobs(session, "notifications.order_placed_owner")) == 1
    order_id = await order_id_by_code(client, owner, out["order"]["code"])
    detail = (await client.get(f"/api/v1/orders/{order_id}", headers=owner.headers)).json()
    assert [e["to_status"] for e in detail["timeline"]] == ["pending_payment", "placed"]


async def test_verify_and_webhook_race(
    client: AsyncClient, session: AsyncSession, rzp: FakeRazorpay
) -> None:
    """Checkout callback and webhook (and a retry of each) hit mark_paid concurrently."""
    owner, item = await _shop(client)
    out = await _online_order(client, owner.slug, item)
    oid = out["payment"]["razorpay_order_id"]

    async def via_mark_paid() -> bool:
        async with get_sessionmaker()() as s:
            return await payment_service.mark_paid(s, oid, "pay_race")

    async def via_verify() -> int:
        res = await client.post(
            f"/api/v1/public/orders/{out['order']['public_token']}/payment/verify",
            json=_signed_verify(out["payment"], "pay_race"),
        )
        return res.status_code

    results = await asyncio.gather(via_mark_paid(), via_verify(), via_mark_paid(), via_verify())
    assert sum(1 for r in results if r is True) <= 1
    assert [r for r in results if isinstance(r, int) and not isinstance(r, bool)] == [200, 200]
    assert len(await _jobs(session, "notifications.order_placed_owner")) == 1
    order_id = await order_id_by_code(client, owner, out["order"]["code"])
    detail = (await client.get(f"/api/v1/orders/{order_id}", headers=owner.headers)).json()
    assert [e["to_status"] for e in detail["timeline"]] == ["pending_payment", "placed"]
    assert detail["payment_status"] == "paid"


async def test_payment_failed_webhook_keeps_order_payable(
    client: AsyncClient, session: AsyncSession, rzp: FakeRazorpay, worker: Worker
) -> None:
    owner, item = await _shop(client)
    out = await _online_order(client, owner.slug, item)
    oid = out["payment"]["razorpay_order_id"]
    await _post_webhook(client, _webhook("payment.failed", oid, "pay_f1"), "evt_f1")
    await _drain(worker)
    payment = (await session.execute(select(Payment))).scalar_one()
    assert payment.status == "failed"
    token = out["order"]["public_token"]
    tracked = (await client.get(f"/api/v1/public/orders/{token}")).json()
    assert tracked["status"] == "pending_payment"
    assert tracked["can_pay"] is True
    # The customer retries and succeeds.
    res = await client.post(
        f"/api/v1/public/orders/{token}/payment/verify",
        json=_signed_verify(out["payment"], "pay_ok"),
    )
    assert res.json()["status"] == "placed"


# --- Expiry ------------------------------------------------------------------------------------


async def _expire(owner: Any, out: dict[str, Any], client: AsyncClient) -> str:
    import uuid

    order_id = await order_id_by_code(client, owner, out["order"]["code"])
    async with get_sessionmaker()() as s:
        return await payment_service.expire_unpaid(s, owner.tenant_id, uuid.UUID(order_id))


async def test_expiry_cancels_unpaid_order(
    client: AsyncClient, session: AsyncSession, rzp: FakeRazorpay
) -> None:
    owner, item = await _shop(client)
    out = await _online_order(client, owner.slug, item, customer_email="c@example.com")
    assert await _expire(owner, out, client) == "cancelled"
    tracked = (await client.get(f"/api/v1/public/orders/{out['order']['public_token']}")).json()
    assert tracked["status"] == "cancelled"
    assert tracked["timeline"][-1]["note"] == "Payment not completed in time"
    jobs = await _jobs(session, "notifications.order_status_customer")
    assert [j.payload["status"] for j in jobs] == ["cancelled"]
    assert await _expire(owner, out, client) == "noop"


async def test_expiry_skips_paid_order(client: AsyncClient, rzp: FakeRazorpay) -> None:
    owner, item = await _shop(client)
    out = await _online_order(client, owner.slug, item)
    await client.post(
        f"/api/v1/public/orders/{out['order']['public_token']}/payment/verify",
        json=_signed_verify(out["payment"]),
    )
    assert await _expire(owner, out, client) == "noop"


async def test_expiry_checks_provider_before_cancelling(
    client: AsyncClient, rzp: FakeRazorpay
) -> None:
    """The webhook is late but Razorpay already captured the payment: mark paid, don't cancel."""
    owner, item = await _shop(client)
    out = await _online_order(client, owner.slug, item)
    rzp.captured[out["payment"]["razorpay_order_id"]] = [{"id": "pay_late", "status": "captured"}]
    assert await _expire(owner, out, client) == "paid"
    tracked = (await client.get(f"/api/v1/public/orders/{out['order']['public_token']}")).json()
    assert (tracked["status"], tracked["payment_status"]) == ("placed", "paid")


async def test_payment_after_cancellation_flags_refund(
    client: AsyncClient, rzp: FakeRazorpay
) -> None:
    owner, item = await _shop(client)
    out = await _online_order(client, owner.slug, item)
    assert await _expire(owner, out, client) == "cancelled"
    async with get_sessionmaker()() as s:
        assert await payment_service.mark_paid(s, out["payment"]["razorpay_order_id"], "pay_x")
    order_id = await order_id_by_code(client, owner, out["order"]["code"])
    detail = (await client.get(f"/api/v1/orders/{order_id}", headers=owner.headers)).json()
    assert detail["status"] == "cancelled"
    assert detail["refund_required"] is True


async def test_expiry_job_runs_through_the_queue(
    client: AsyncClient, rzp: FakeRazorpay, worker: Worker
) -> None:
    import time

    from app.queue.scheduler import promote_once

    owner, item = await _shop(client)
    out = await _online_order(client, owner.slug, item)
    await _drain(worker)  # expiry is delayed, nothing runs yet
    token = out["order"]["public_token"]
    assert (await client.get(f"/api/v1/public/orders/{token}")).json()[
        "status"
    ] == "pending_payment"
    await promote_once(worker.scripts, now_ms=int(time.time() * 1000) + 31 * 60 * 1000)
    await _drain(worker)
    assert (await client.get(f"/api/v1/public/orders/{token}")).json()["status"] == "cancelled"
