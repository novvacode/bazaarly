"""LLM access behind one interface (SPEC §13.4). Tests use FakeLLM and never call the API."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Protocol

import anthropic
import structlog
from anthropic.types import MessageParam

from app.config import get_settings

log = structlog.get_logger("llm")

# JSON shape the model must return (structured outputs guarantee it on supported models).
ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "answered": {"type": "boolean"},
        "used_chunk_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["answer", "answered", "used_chunk_ids"],
    "additionalProperties": False,
}

# Models on which temperature/top_p were removed (they 400 if sent).
_NO_SAMPLING_PREFIXES = (
    "claude-opus-4-7",
    "claude-opus-4-8",
    "claude-opus-5",
    "claude-sonnet-5",
    "claude-fable",
    "claude-mythos",
)


@dataclass(frozen=True, slots=True)
class ChatTurn:
    role: str  # "user" | "assistant"
    content: str


class LLMError(Exception):
    """The provider failed; callers answer with the fallback."""


class LLMClient(Protocol):
    model: str

    async def complete(self, system: str, turns: list[ChatTurn]) -> str:
        """Return the raw text of the model's reply (expected to be the JSON object)."""
        ...


class AnthropicClient:
    def __init__(self, api_key: str, model: str, temperature: float = 0.2, max_tokens: int = 400):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._client = anthropic.AsyncAnthropic(api_key=api_key, max_retries=2, timeout=20.0)

    async def complete(self, system: str, turns: list[ChatTurn]) -> str:
        messages: list[MessageParam] = [
            {"role": "user" if t.role == "user" else "assistant", "content": t.content}
            for t in turns
        ]
        samples = not self.model.startswith(_NO_SAMPLING_PREFIXES)
        try:
            response = await self._client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system,
                messages=messages,
                output_config={"format": {"type": "json_schema", "schema": ANSWER_SCHEMA}},
                # SDK 1.x dropped sampling params from its signature; models that still honour
                # them (e.g. the default claude-haiku-4-5) take them via extra_body.
                extra_body={"temperature": self.temperature} if samples else None,
            )
        except anthropic.RateLimitError as exc:
            raise LLMError("rate limited") from exc
        except anthropic.APIStatusError as exc:
            raise LLMError(f"status {exc.status_code}") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError("connection error") from exc
        if response.stop_reason in ("refusal", "max_tokens"):
            log.warning("llm_incomplete", stop_reason=response.stop_reason)
            return ""
        return "".join(b.text for b in response.content if b.type == "text")


@dataclass
class FakeLLM:
    """Deterministic stand-in: answers with the best non-business chunk, else falls back.

    Tests can queue exact raw replies in `scripted` to exercise parsing edge cases.
    """

    model: str = "fake-llm"
    scripted: list[str] = field(default_factory=list)
    calls: list[tuple[str, list[ChatTurn]]] = field(default_factory=list)

    async def complete(self, system: str, turns: list[ChatTurn]) -> str:
        import json

        self.calls.append((system, turns))
        if self.scripted:
            return self.scripted.pop(0)
        chunks = re.findall(
            r'<chunk id="([^"]+)" source="([^"]+)">(.*?)</chunk>', turns[-1].content
        )
        relevant = [(cid, text) for cid, source, text in chunks if source != "business_info"]
        if relevant:
            cid, text = relevant[0]
            return json.dumps({"answer": text[:300], "answered": True, "used_chunk_ids": [cid]})
        fallback = re.search(r'reply exactly: "([^"]+)"', system)
        return json.dumps(
            {
                "answer": fallback.group(1) if fallback else "I'm not sure.",
                "answered": False,
                "used_chunk_ids": [],
            }
        )


@lru_cache(maxsize=1)
def get_llm() -> LLMClient:
    s = get_settings()
    if s.llm_provider == "fake":
        return FakeLLM()
    return AnthropicClient(s.anthropic_api_key, s.llm_model)
