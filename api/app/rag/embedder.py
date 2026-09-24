"""Text embeddings behind one interface (SPEC §13.2).

Production uses fastembed's `BAAI/bge-small-en-v1.5` (384-dim ONNX on CPU), loaded once per
process. Tests use `FakeEmbedder`: deterministic hashed bag-of-words vectors, so texts that
share words are genuinely similar and retrieval tests stay meaningful.
"""

from __future__ import annotations

import asyncio
import hashlib
import math
import re
from functools import lru_cache
from typing import Any, Protocol

from app.config import get_settings
from app.models.assistant import EMBEDDING_DIM

MODEL_NAME = "BAAI/bge-small-en-v1.5"


class Embedder(Protocol):
    name: str

    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]: ...


class FastEmbedEmbedder:
    name = MODEL_NAME

    def __init__(self) -> None:
        from fastembed import TextEmbedding

        self._model: Any = TextEmbedding(MODEL_NAME)

    def _embed(self, texts: list[str]) -> list[list[float]]:
        return [vec.tolist() for vec in self._model.embed(texts)]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return await asyncio.to_thread(self._embed, texts)

    async def embed_query(self, text: str) -> list[float]:
        # bge models recommend this instruction prefix for short retrieval queries.
        prefixed = f"Represent this sentence for searching relevant passages: {text}"
        return (await asyncio.to_thread(self._embed, [prefixed]))[0]


_WORD = re.compile(r"[a-z0-9₹]+")
_STOP = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "can",
        "do",
        "does",
        "for",
        "from",
        "have",
        "i",
        "in",
        "is",
        "it",
        "me",
        "my",
        "of",
        "on",
        "or",
        "our",
        "the",
        "to",
        "you",
        "your",
        "we",
        "with",
        "what",
        "which",
        "how",
        "this",
        "that",
    ]
)


def _tokens(text: str) -> list[str]:
    return [w for w in _WORD.findall(text.lower()) if w not in _STOP]


class FakeEmbedder:
    name = "fake-hash-embedder"

    def _vector(self, text: str) -> list[float]:
        vec = [0.0] * EMBEDDING_DIM
        for token in _tokens(text):
            digest = hashlib.sha256(token.encode()).digest()
            vec[int.from_bytes(digest[:4], "big") % EMBEDDING_DIM] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    if get_settings().embedder == "fake":
        return FakeEmbedder()
    return FastEmbedEmbedder()
