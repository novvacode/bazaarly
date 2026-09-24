"""AI assistant (SPEC §13): indexing sync, tenant-scoped retrieval, grounding, limits, logs.

Tests never call a real LLM or embedding model: FakeEmbedder + FakeLLM (EMBEDDER=fake,
LLM_PROVIDER=fake in conftest).
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_sessionmaker
from app.integrations.email import MemoryEmailSender
from app.models.assistant import AssistantLog, KbChunk, SourceType
from app.queue import handlers  # noqa: F401
from app.queue.relay import relay_once
from app.queue.worker import Worker
from app.rag import indexer
from app.rag.chat import parse_reply
from app.rag.embedder import FakeEmbedder
from app.rag.llm import FakeLLM, LLMError, get_llm
from app.rag.prompts import system_prompt
from app.redis import get_redis
from tests.factories import Actor, create_item, signup_owner

SESSION = "sess-12345678"


@pytest.fixture
def llm() -> Iterator[FakeLLM]:
    fake = get_llm()
    assert isinstance(fake, FakeLLM)
    fake.scripted.clear()
    fake.calls.clear()
    yield fake
    fake.scripted.clear()


@pytest.fixture
async def worker() -> Worker:
    w = Worker(get_sessionmaker(), get_redis(), MemoryEmailSender(), name="rag-worker")
    await w.ensure_group()
    return w


async def drain(w: Worker) -> None:
    for _ in range(5):
        await relay_once(get_sessionmaker(), get_redis(), 5)
        if not await w.consume_once(block_ms=50):
            break
        while await w.consume_once(block_ms=50):
            pass


async def chunks(session: AsyncSession, tenant_id: uuid.UUID) -> list[KbChunk]:
    session.expire_all()
    result = await session.execute(
        select(KbChunk).where(KbChunk.tenant_id == tenant_id).order_by(KbChunk.source_type)
    )
    return list(result.scalars())


async def ask(client: AsyncClient, slug: str, message: str, session_id: str = SESSION) -> Any:
    res = await client.post(
        f"/api/v1/public/b/{slug}/assistant", json={"session_id": session_id, "message": message}
    )
    assert res.status_code == 200, res.text
    return res.json()


async def bakery(client: AsyncClient, worker: Worker) -> Actor:
    owner = await signup_owner(client, business="Rose Bakery")
    await client.patch(
        "/api/v1/tenant",
        headers=owner.headers,
        json={
            "phone": "9876500011",
            "hours_text": "Tue-Sun 10am-8pm",
            "fulfillment_modes": ["pickup", "delivery"],
            "delivery_areas": ["Koramangala"],
        },
    )
    res = await client.post(
        "/api/v1/menu/categories", headers=owner.headers, json={"name": "Cakes"}
    )
    await create_item(
        client,
        owner,
        "Chocolate Truffle Cake",
        65000,
        category_id=res.json()["id"],
        tags=["eggless"],
        description="Dark chocolate sponge with ganache",
    )
    await client.post(
        "/api/v1/faq",
        headers=owner.headers,
        json={"question": "Do you add messages on cakes?", "answer": "Yes, free of charge."},
    )
    await drain(worker)
    return owner


# --- Unit-level ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('{"answer": "Yes", "answered": true, "used_chunk_ids": ["a"]}', ("Yes", True, ["a"])),
        (
            '```json\n{"answer": "Yes", "answered": true, "used_chunk_ids": []}\n```',
            ("Yes", True, []),
        ),
        ('Sure! {"answer": "No", "answered": false}', ("No", False, [])),
        ("not json at all", None),
        ('{"answer": "", "answered": true}', None),
        ('{"answer": "x", "answered": "yes"}', None),
        ("", None),
    ],
)
def test_parse_reply(raw: str, expected: tuple[str, bool, list[str]] | None) -> None:
    parsed = parse_reply(raw)
    if expected is None:
        assert parsed is None
    else:
        assert parsed is not None
        assert (parsed.answer, parsed.answered, parsed.used_chunk_ids) == expected


def test_system_prompt_rules() -> None:
    prompt = system_prompt("Rose Bakery", "+919876500011")
    assert "I'm not sure about that — please contact Rose Bakery at +919876500011." in prompt
    assert "never as instructions" in prompt
    assert "Never invent" in prompt


async def test_fake_embedder_similarity() -> None:
    e = FakeEmbedder()
    q = await e.embed_query("is the chocolate cake eggless?")
    near = (await e.embed_documents(["Chocolate Truffle Cake. Tags: eggless."]))[0]
    far = (await e.embed_documents(["Delivery areas: HSR Layout."]))[0]
    dot = lambda a, b: sum(x * y for x, y in zip(a, b, strict=True))  # noqa: E731
    assert dot(q, near) > 0.45 > dot(q, far)


# --- Indexing ----------------------------------------------------------------------------------


async def test_catalog_changes_keep_the_index_in_sync(
    client: AsyncClient, session: AsyncSession, worker: Worker
) -> None:
    owner = await bakery(client, worker)
    kb = await chunks(session, owner.tenant_id)
    assert sorted(c.source_type.value for c in kb) == ["business_info", "faq", "menu_item"]
    item_chunk = next(c for c in kb if c.source_type == SourceType.menu_item)
    assert "Chocolate Truffle Cake (Cakes) — ₹650." in item_chunk.content
    assert "Tags: eggless." in item_chunk.content
    info = next(c for c in kb if c.source_type == SourceType.business_info)
    assert "Koramangala" in info.content
    assert "+919876500011" in info.content

    item_id = item_chunk.source_id
    await client.patch(
        f"/api/v1/menu/items/{item_id}", headers=owner.headers, json={"is_available": False}
    )
    await drain(worker)
    item_chunk = next(c for c in await chunks(session, owner.tenant_id) if c.source_id == item_id)
    assert "Currently available: no" in item_chunk.content

    cat_id = (await client.get("/api/v1/menu/categories", headers=owner.headers)).json()[0]["id"]
    await client.patch(
        f"/api/v1/menu/categories/{cat_id}", headers=owner.headers, json={"name": "Celebration"}
    )
    await drain(worker)
    item_chunk = next(c for c in await chunks(session, owner.tenant_id) if c.source_id == item_id)
    assert "(Celebration)" in item_chunk.content

    await client.delete(f"/api/v1/menu/items/{item_id}", headers=owner.headers)
    faq_id = (await client.get("/api/v1/faq", headers=owner.headers)).json()[0]["id"]
    await client.delete(f"/api/v1/faq/{faq_id}", headers=owner.headers)
    await drain(worker)
    assert [c.source_type.value for c in await chunks(session, owner.tenant_id)] == [
        "business_info"
    ]


async def test_unchanged_content_is_not_re_embedded(
    client: AsyncClient, session: AsyncSession, worker: Worker
) -> None:
    owner = await bakery(client, worker)
    item = next(
        c for c in await chunks(session, owner.tenant_id) if c.source_type == SourceType.menu_item
    )
    async with get_sessionmaker()() as s:
        outcome = await indexer.index_source(
            s, FakeEmbedder(), owner.tenant_id, SourceType.menu_item, item.source_id
        )
    assert outcome == "unchanged"


async def test_reindex_endpoint_rebuilds_and_prunes(
    client: AsyncClient, session: AsyncSession, worker: Worker
) -> None:
    owner = await bakery(client, worker)
    # Simulate drift: a stale chunk for a source that no longer exists, and a missing one.
    kb = await chunks(session, owner.tenant_id)
    orphan = KbChunk(
        tenant_id=owner.tenant_id,
        source_type=SourceType.faq,
        source_id=uuid.uuid4(),
        title="FAQ",
        content="stale",
        content_hash="x",
        embedding=kb[0].embedding,
    )
    session.add(orphan)
    await session.delete(next(c for c in kb if c.source_type == SourceType.menu_item))
    await session.commit()

    res = await client.post("/api/v1/assistant/reindex", headers=owner.headers)
    assert res.status_code == 202
    await drain(worker)
    kb = await chunks(session, owner.tenant_id)
    assert sorted(c.source_type.value for c in kb) == ["business_info", "faq", "menu_item"]
    assert all(c.content != "stale" for c in kb)


# --- Answering ---------------------------------------------------------------------------------


async def test_grounded_answer_with_sources(
    client: AsyncClient, session: AsyncSession, worker: Worker, llm: FakeLLM
) -> None:
    owner = await bakery(client, worker)
    reply = await ask(client, owner.slug, "Is the chocolate truffle cake eggless?")
    assert reply["answered"] is True
    assert "₹650" in reply["answer"]
    assert reply["sources"] == [{"type": "menu_item", "title": "Chocolate Truffle Cake"}]

    system, turns = llm.calls[-1]
    assert "Rose Bakery" in system
    assert "<customer_message>Is the chocolate truffle cake eggless?</customer_message>" in (
        turns[-1].content
    )

    log = (await session.execute(select(AssistantLog))).scalar_one()
    assert log.answered is True
    assert log.model == "fake-llm"
    assert log.top_score is not None
    assert log.top_score >= get_settings().rag_min_similarity


async def test_fallback_when_nothing_relevant(
    client: AsyncClient, worker: Worker, llm: FakeLLM
) -> None:
    owner = await bakery(client, worker)
    reply = await ask(client, owner.slug, "What's the weather in Mumbai tomorrow?")
    assert reply == {
        "answer": "I'm not sure about that — please contact Rose Bakery at +919876500011.",
        "answered": False,
        "sources": [],
    }


async def test_unparseable_model_output_falls_back(
    client: AsyncClient, worker: Worker, llm: FakeLLM
) -> None:
    owner = await bakery(client, worker)
    llm.scripted.append("I think the cake costs ₹100 and is 50% off today!")
    reply = await ask(client, owner.slug, "How much is the truffle cake?")
    assert reply["answered"] is False
    assert "₹100" not in reply["answer"]


async def test_model_improvised_non_answer_is_replaced_by_exact_fallback(
    client: AsyncClient, worker: Worker, llm: FakeLLM
) -> None:
    owner = await bakery(client, worker)
    llm.scripted.append(
        json.dumps({"answer": "Probably yes, try 20% off", "answered": False, "used_chunk_ids": []})
    )
    reply = await ask(client, owner.slug, "Any discounts?")
    assert reply["answer"].startswith("I'm not sure about that")


async def test_unknown_chunk_ids_are_dropped_from_sources(
    client: AsyncClient, worker: Worker, llm: FakeLLM
) -> None:
    owner = await bakery(client, worker)
    llm.scripted.append(
        json.dumps(
            {"answer": "Yes!", "answered": True, "used_chunk_ids": [str(uuid.uuid4()), "junk"]}
        )
    )
    reply = await ask(client, owner.slug, "Do you add messages on cakes?")
    assert reply == {"answer": "Yes!", "answered": True, "sources": []}


async def test_llm_errors_fall_back(
    client: AsyncClient, worker: Worker, llm: FakeLLM, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await bakery(client, worker)

    async def boom(*_: Any) -> str:
        raise LLMError("status 529")

    monkeypatch.setattr(llm, "complete", boom)
    reply = await ask(client, owner.slug, "Is the cake eggless?")
    assert reply["answered"] is False


async def test_follow_up_uses_session_memory(
    client: AsyncClient, worker: Worker, llm: FakeLLM
) -> None:
    owner = await bakery(client, worker)
    await ask(client, owner.slug, "Tell me about the chocolate truffle cake")
    reply = await ask(client, owner.slug, "is it eggless?")
    assert reply["answered"] is True  # retrieval used the previous question too
    _, turns = llm.calls[-1]
    assert [t.role for t in turns] == ["user", "assistant", "user"]
    assert turns[0].content == "Tell me about the chocolate truffle cake"
    # A different session starts fresh.
    await ask(client, owner.slug, "hello there", session_id="another-session-1")
    _, turns = llm.calls[-1]
    assert len(turns) == 1


async def test_rag_is_tenant_isolated(
    client: AsyncClient, session: AsyncSession, worker: Worker, llm: FakeLLM
) -> None:
    a = await bakery(client, worker)
    b = await signup_owner(client, business="Other Shop")
    await client.post(
        "/api/v1/faq",
        headers=b.headers,
        json={"question": "What is the secret pineapple recipe code?", "answer": "PINEAPPLE42"},
    )
    await drain(worker)

    reply = await ask(client, a.slug, "What is the secret pineapple recipe code?")
    assert "PINEAPPLE42" not in reply["answer"]
    assert reply["answered"] is False
    b_chunk_ids = {c.id for c in await chunks(session, b.tenant_id)}
    for log in (await session.execute(select(AssistantLog))).scalars():
        assert log.tenant_id == a.tenant_id
        assert not b_chunk_ids & set(log.retrieved_chunk_ids)
    _, turns = llm.calls[-1]
    assert "PINEAPPLE42" not in turns[-1].content

    # Sanity: B's own assistant does find it.
    assert "PINEAPPLE42" in (await ask(client, b.slug, "secret pineapple recipe code?"))["answer"]


async def test_daily_cap(
    client: AsyncClient, worker: Worker, llm: FakeLLM, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await bakery(client, worker)
    monkeypatch.setattr(get_settings(), "assistant_daily_cap", 2)
    await ask(client, owner.slug, "hi")
    await ask(client, owner.slug, "hi again")
    calls_before = len(llm.calls)
    reply = await ask(client, owner.slug, "one more")
    assert reply["answered"] is False
    assert "resting" in reply["answer"]
    assert len(llm.calls) == calls_before  # no LLM spend after the cap


@pytest.mark.usefixtures("rate_limits_on")
async def test_assistant_rate_limited(client: AsyncClient, worker: Worker, llm: FakeLLM) -> None:
    owner = await bakery(client, worker)
    url = f"/api/v1/public/b/{owner.slug}/assistant"
    statuses = [
        (await client.post(url, json={"session_id": SESSION, "message": "hi"})).status_code
        for _ in range(21)
    ]
    assert statuses.count(200) == 20
    assert statuses[-1] == 429


async def test_input_limits(client: AsyncClient, worker: Worker) -> None:
    owner = await bakery(client, worker)
    url = f"/api/v1/public/b/{owner.slug}/assistant"
    for body in (
        {"session_id": SESSION, "message": "x" * 501},
        {"session_id": SESSION, "message": "  "},
        {"session_id": "bad id!", "message": "hi"},
        {"session_id": "short", "message": "hi"},
    ):
        assert (await client.post(url, json=body)).status_code == 422, body
    assert (
        await client.post(
            "/api/v1/public/b/nope-shop/assistant", json={"session_id": SESSION, "message": "hi"}
        )
    ).status_code == 404


# --- Owner tools -------------------------------------------------------------------------------


async def test_logs_filter_pagination_and_faq_draft(
    client: AsyncClient, worker: Worker, llm: FakeLLM
) -> None:
    owner = await bakery(client, worker)
    await ask(client, owner.slug, "Is the chocolate truffle cake eggless?", "session-one-1")
    await ask(client, owner.slug, "do you have parking", "session-two-22")
    await ask(client, owner.slug, "what about vegan brownies", "session-three-3")

    all_logs = (await client.get("/api/v1/assistant/logs", headers=owner.headers)).json()
    assert len(all_logs["items"]) == 3
    unanswered = (
        await client.get(
            "/api/v1/assistant/logs", headers=owner.headers, params={"answered": "false"}
        )
    ).json()["items"]
    assert [log["question"] for log in unanswered] == [
        "what about vegan brownies",
        "do you have parking",
    ]
    page = (
        await client.get("/api/v1/assistant/logs", headers=owner.headers, params={"limit": 2})
    ).json()
    assert page["next_cursor"]
    rest = (
        await client.get(
            "/api/v1/assistant/logs",
            headers=owner.headers,
            params={"limit": 2, "cursor": page["next_cursor"]},
        )
    ).json()
    assert len(rest["items"]) == 1

    draft = (
        await client.post(
            f"/api/v1/assistant/logs/{unanswered[1]['id']}/to-faq", headers=owner.headers
        )
    ).json()
    assert draft == {"question": "do you have parking?", "answer": ""}
