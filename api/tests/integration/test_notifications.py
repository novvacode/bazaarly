"""Notification handlers end to end: order → outbox → relay → consumer → email."""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_sessionmaker
from app.integrations.email import MemoryEmailSender
from app.models.tenant import Tenant
from app.queue import handlers  # noqa: F401 - registers handlers
from app.queue.envelope import Envelope
from app.queue.relay import publish, relay_once
from app.queue.worker import Worker
from app.redis import get_redis
from app.services.money import format_inr
from tests.factories import create_item, order_id_by_code, place_order, signup_owner


async def make_tenant(session: AsyncSession, email: str | None = None) -> Tenant:
    tenant = Tenant(name="Cron Cakes", slug=f"cron-{uuid.uuid4().hex[:8]}", email=email)
    session.add(tenant)
    await session.commit()
    return tenant


@pytest.fixture
async def mail_worker() -> tuple[Worker, MemoryEmailSender]:
    mail = MemoryEmailSender()
    w = Worker(get_sessionmaker(), get_redis(), mail, name="mail-worker")
    await w.ensure_group()
    return w, mail


async def _drain(w: Worker) -> None:
    await relay_once(get_sessionmaker(), get_redis(), 5)
    while await w.consume_once(block_ms=50):
        pass


def test_format_inr() -> None:
    assert format_inr(65000) == "₹650"
    assert format_inr(123450) == "₹1,234.50"
    assert format_inr(10_000_000) == "₹1,00,000"
    assert format_inr(123_456_789) == "₹12,34,567.89"
    assert format_inr(5) == "₹0.05"


async def test_order_emails_flow_through_the_queue(
    client: AsyncClient, mail_worker: tuple[Worker, MemoryEmailSender]
) -> None:
    worker, mail = mail_worker
    owner = await signup_owner(client, business="Mail Bakery")
    cake = await create_item(client, owner, "Truffle Cake <b>", 65000)
    out = await place_order(
        client,
        owner.slug,
        [cake],
        customer_email="priya@example.com",
        customer_name="Priya",
        notes="No nuts please",
    )
    await _drain(worker)

    owner_mail = next(m for m in mail.sent if m.to == owner.email)
    assert owner_mail.subject == f"New order #{out['order']['code']} · ₹650"
    assert "Priya" in owner_mail.text
    assert "No nuts please" in owner_mail.text
    assert "Truffle Cake &lt;b&gt;" in owner_mail.html  # escaped in HTML
    assert "/dashboard/orders/" in owner_mail.html

    customer_mail = next(m for m in mail.sent if m.to == "priya@example.com")
    assert customer_mail.subject.startswith(f"Order #{out['order']['code']} received")
    assert out["order"]["public_token"] in customer_mail.text

    order_id = await order_id_by_code(client, owner, out["order"]["code"])
    await client.post(
        f"/api/v1/orders/{order_id}/transition",
        headers=owner.headers,
        json={"to_status": "cancelled", "reason": "Oven broke"},
    )
    await _drain(worker)
    cancel = mail.sent[-1]
    assert cancel.subject.startswith(f"Order #{out['order']['code']} was cancelled")
    assert "Oven broke" in cancel.text
    assert len(mail.sent) == 3

    # Re-publishing an already-completed job doesn't email twice.
    await publish(
        get_redis(),
        Envelope(
            type="notifications.order_placed_owner",
            payload={"tenant_id": str(owner.tenant_id), "order_id": order_id},
            idempotency_key=f"order_placed_owner:{order_id}",
        ),
    )
    await _drain(worker)
    assert len(mail.sent) == 3


async def test_daily_summary_email(
    client: AsyncClient, mail_worker: tuple[Worker, MemoryEmailSender]
) -> None:
    worker, mail = mail_worker
    owner = await signup_owner(client, business="Summary Shop")
    cake = await create_item(client, owner, "Cake", 50000)
    await place_order(client, owner.slug, [cake])
    await _drain(worker)
    mail.sent.clear()

    today = (await client.get("/api/v1/dashboard/summary", headers=owner.headers)).json()["date"]
    await publish(
        get_redis(),
        Envelope(
            type="summary.daily",
            payload={"tenant_id": str(owner.tenant_id), "date": today},
            idempotency_key=f"summary.daily:{owner.tenant_id}:{today}",
        ),
    )
    await _drain(worker)
    (summary,) = mail.sent
    assert summary.to == owner.email
    assert summary.subject.startswith("Summary Shop: 1 orders today")
    assert "Cake" in summary.text
    assert date.fromisoformat(today).strftime("%d %b %Y") in summary.text
