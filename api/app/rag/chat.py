"""Storefront assistant: retrieve → generate → parse → log (SPEC §13.3 to §13.5)."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

import structlog
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.assistant import AssistantLog, SourceType
from app.models.tenant import Tenant
from app.rag.embedder import Embedder
from app.rag.llm import ChatTurn, LLMClient, LLMError
from app.rag.prompts import fallback_answer, system_prompt, user_turn
from app.rag.retriever import Retrieved, retrieve
from app.schemas.assistant import AssistantReplyOut, SourceOut

log = structlog.get_logger("assistant")

HISTORY_TURNS = 6
HISTORY_TTL_S = 3600
RESTING = (
    "The assistant is resting for today — please browse the menu or contact {business}"
    "{phone_clause} directly."
)
_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class Parsed:
    answer: str
    answered: bool
    used_chunk_ids: list[str]


def parse_reply(raw: str) -> Parsed | None:
    """Parse the model's JSON defensively (code fences, stray text). None if unusable."""
    text = _FENCE.sub("", raw.strip())
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except ValueError:
        return None
    answer = data.get("answer")
    answered = data.get("answered")
    used = data.get("used_chunk_ids", [])
    if not isinstance(answer, str) or not answer.strip() or not isinstance(answered, bool):
        return None
    if not isinstance(used, list):
        used = []
    return Parsed(answer.strip(), answered, [str(u) for u in used])


def _history_key(tenant_id: object, session_id: str) -> str:
    return f"bz:chat:{tenant_id}:{session_id}"


def _cap_key(tenant: Tenant) -> str:
    day = datetime.now(ZoneInfo(tenant.timezone)).date().isoformat()
    return f"bz:assistant:count:{tenant.id}:{day}"


async def _history(redis: Redis, key: str) -> list[ChatTurn]:
    raw = await redis.lrange(key, -HISTORY_TURNS, -1)
    turns = []
    for item in raw:
        try:
            data = json.loads(item)
            turns.append(ChatTurn(role=data["role"], content=data["content"]))
        except (ValueError, KeyError):
            continue
    # The Messages API needs alternating turns starting with the user.
    while turns and turns[0].role != "user":
        turns.pop(0)
    return turns


async def _remember(redis: Redis, key: str, question: str, answer: str) -> None:
    pipe = redis.pipeline()
    pipe.rpush(
        key,
        json.dumps({"role": "user", "content": question}),
        json.dumps({"role": "assistant", "content": answer}),
    )
    pipe.ltrim(key, -HISTORY_TURNS, -1)
    pipe.expire(key, HISTORY_TTL_S)
    await pipe.execute()


def _source_title(chunk: Retrieved) -> str:
    return {SourceType.faq: "FAQ", SourceType.business_info: "Business info"}.get(
        chunk.source_type, chunk.title
    )


async def ask(
    session: AsyncSession,
    redis: Redis,
    embedder: Embedder,
    llm: LLMClient,
    tenant: Tenant,
    session_id: str,
    message: str,
) -> AssistantReplyOut:
    started = time.perf_counter()
    settings = get_settings()
    fallback = fallback_answer(tenant.name, tenant.phone)

    count = await redis.incr(_cap_key(tenant))
    if count == 1:
        await redis.expire(_cap_key(tenant), 2 * 86400)
    if count > settings.assistant_daily_cap:
        phone_clause = f" at {tenant.phone}" if tenant.phone else ""
        return AssistantReplyOut(
            answer=RESTING.format(business=tenant.name, phone_clause=phone_clause),
            answered=False,
            sources=[],
        )

    key = _history_key(tenant.id, session_id)
    history = await _history(redis, key)
    previous_question = next((t.content for t in reversed(history) if t.role == "user"), None)
    query = f"{previous_question}\n{message}" if previous_question else message

    chunks = await retrieve(
        session, embedder, tenant.id, query, min_similarity=settings.rag_min_similarity
    )
    by_id = {str(c.id): c for c in chunks}

    parsed: Parsed | None = None
    try:
        raw = await llm.complete(
            system_prompt(tenant.name, tenant.phone),
            [*history, ChatTurn("user", user_turn(chunks, message))],
        )
        parsed = parse_reply(raw)
        if parsed is None:
            log.warning("assistant_unparseable", raw=raw[:300])
    except LLMError as exc:
        log.warning("assistant_llm_error", error=str(exc))

    if parsed is None or not parsed.answered:
        # Never pass through a model's improvised "not answered" text: use the exact fallback.
        answer, answered, used = fallback, False, []
    else:
        answer, answered = parsed.answer, True
        used = [by_id[i] for i in parsed.used_chunk_ids if i in by_id]

    seen: set[tuple[str, str]] = set()
    sources = []
    for chunk in used:
        item = (chunk.source_type.value, _source_title(chunk))
        if item not in seen:
            seen.add(item)
            sources.append(SourceOut(type=item[0], title=item[1]))

    await _remember(redis, key, message, answer)
    latency_ms = int((time.perf_counter() - started) * 1000)
    session.add(
        AssistantLog(
            tenant_id=tenant.id,
            session_id=session_id,
            question=message,
            answer=answer,
            answered=answered,
            retrieved_chunk_ids=[c.id for c in chunks],
            top_score=max((c.score for c in chunks), default=None),
            latency_ms=latency_ms,
            model=llm.model,
        )
    )
    await session.commit()
    log.info("assistant_reply", answered=answered, chunks=len(chunks), latency_ms=latency_ms)
    return AssistantReplyOut(answer=answer, answered=answered, sources=sources)
