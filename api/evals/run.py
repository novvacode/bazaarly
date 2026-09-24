"""Assistant eval harness (SPEC §13.6).

    python -m evals.run --tenant demo-bakery            # real embedder + real LLM (costs a little)
    python -m evals.run --tenant demo-bakery --fake     # FakeEmbedder + FakeLLM: harness check only

Runs every question in `evals/datasets/<tenant>.yaml` against the seeded tenant, each in a fresh
chat session, and writes a Markdown report to `evals/reports/<date>-<tenant>[-fake].md` with:
answerability accuracy, must-include pass rate, must-not-include violations, retrieval hit
rate@6 and p50/p95 latency.
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from app.config import get_settings
from app.core.logging import configure_logging
from app.db import dispose_engine, get_sessionmaker
from app.models.assistant import SourceType
from app.rag import indexer
from app.rag.chat import ask
from app.rag.embedder import Embedder, FakeEmbedder, get_embedder
from app.rag.llm import FakeLLM, LLMClient, get_llm
from app.rag.retriever import Retrieved, retrieve
from app.redis import close_redis, get_redis
from app.repositories import tenants as tenant_repo

EVALS = Path(__file__).resolve().parent
TARGETS = {"answerability": 0.90, "retrieval_hit": 0.90}


@dataclass
class Result:
    question: str
    answerable: bool
    answered: bool
    answer: str
    must_include_ok: bool | None
    violations: list[str]
    retrieval_hit: bool | None
    latency_ms: int
    sources: list[str] = field(default_factory=list)


def matches_source(expected: str, chunks: list[Retrieved]) -> bool:
    kind, _, name = expected.partition(":")
    for c in chunks:
        if c.source_type.value != kind:
            continue
        if kind == SourceType.business_info.value:
            return True
        if kind == SourceType.menu_item.value and c.title == name:
            return True
        if kind == SourceType.faq.value and c.content.startswith(f"Q: {name}"):
            return True
    return False


def load_dataset(tenant: str) -> list[dict[str, Any]]:
    data = yaml.safe_load((EVALS / "datasets" / f"{tenant}.yaml").read_text())
    return list(data["items"])


async def run(tenant_slug: str, embedder: Embedder, llm: LLMClient) -> list[Result]:
    settings = get_settings()
    settings.assistant_daily_cap = 10**9  # evals shouldn't hit the per-tenant cap
    items = load_dataset(tenant_slug)
    redis = get_redis()
    results: list[Result] = []
    async with get_sessionmaker()() as session:
        tenant = await tenant_repo.get_by_slug(session, tenant_slug)
        if tenant is None:
            raise SystemExit(f"Tenant {tenant_slug!r} not found — run `make seed` first.")
        # Make sure the index is current for this embedder (no-op when it already is).
        for source_type, source_id in await indexer.all_sources(session, tenant.id):
            await indexer.index_source(session, embedder, tenant.id, source_type, source_id)

        for item in items:
            question = item["question"]
            chunks = await retrieve(
                session,
                embedder,
                tenant.id,
                question,
                min_similarity=settings.rag_min_similarity,
            )
            started = time.perf_counter()
            reply = await ask(
                session, redis, embedder, llm, tenant, f"eval-{uuid.uuid4().hex}", question
            )
            latency = int((time.perf_counter() - started) * 1000)
            answer = reply.answer.lower()
            must = [s.lower() for s in item.get("must_include", [])]
            must_not = [s.lower() for s in item.get("must_not_include", [])]
            expected = item.get("expected_source")
            results.append(
                Result(
                    question=question,
                    answerable=bool(item["answerable"]),
                    answered=reply.answered,
                    answer=reply.answer,
                    must_include_ok=(
                        all(s in answer for s in must) if must and reply.answered else None
                    ),
                    violations=[s for s in must_not if s in answer],
                    retrieval_hit=matches_source(expected, chunks) if expected else None,
                    latency_ms=latency,
                    sources=[f"{s.type}:{s.title}" for s in reply.sources],
                )
            )
    return results


def _pct(values: list[bool]) -> str:
    return (
        f"{100 * sum(values) / len(values):.1f}% ({sum(values)}/{len(values)})" if values else "n/a"
    )


def summarize(results: list[Result]) -> dict[str, Any]:
    latencies = sorted(r.latency_ms for r in results)
    p95_index = max(0, round(0.95 * len(latencies)) - 1)
    return {
        "answerability": [r.answered == r.answerable for r in results],
        "must_include": [r.must_include_ok for r in results if r.must_include_ok is not None],
        "violations": sum(len(r.violations) for r in results),
        "retrieval": [r.retrieval_hit for r in results if r.retrieval_hit is not None],
        "p50": statistics.median(latencies) if latencies else 0,
        "p95": latencies[p95_index] if latencies else 0,
    }


def report(tenant: str, results: list[Result], model: str, embedder: str, fake: bool) -> str:
    s = summarize(results)
    answerability = sum(s["answerability"]) / len(s["answerability"])
    retrieval = sum(s["retrieval"]) / len(s["retrieval"]) if s["retrieval"] else 0.0
    status = (
        "PASS"
        if answerability >= TARGETS["answerability"]
        and retrieval >= TARGETS["retrieval_hit"]
        and s["violations"] == 0
        else "FAIL"
    )
    lines = [
        f"# Assistant eval — {tenant}",
        "",
        f"- Date: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}",
        f"- Model: `{model}` · Embedder: `{embedder}` · Similarity threshold: "
        f"{get_settings().rag_min_similarity}",
    ]
    if fake:
        lines.append(
            "- **Mode: fake (FakeEmbedder + FakeLLM).** This checks the harness only; the "
            "numbers say nothing about real answer quality."
        )
    lines += [
        f"- Result vs targets: **{status}**",
        "",
        "| Metric | Value | Target |",
        "|---|---|---|",
        f"| Answerability accuracy | {_pct(s['answerability'])} | ≥ 90% |",
        f"| Must-include pass rate | {_pct(s['must_include'])} | — |",
        f"| Must-not-include violations | {s['violations']} | 0 |",
        f"| Retrieval hit rate @6 | {_pct(s['retrieval'])} | ≥ 90% |",
        f"| Latency p50 / p95 | {s['p50']:.0f} ms / {s['p95']} ms | — |",
        "",
        "## Failures",
        "",
    ]
    failures = [
        r
        for r in results
        if r.answered != r.answerable
        or r.violations
        or r.must_include_ok is False
        or r.retrieval_hit is False
    ]
    if not failures:
        lines.append("None.")
    for r in failures:
        problems = []
        if r.answered != r.answerable:
            problems.append(f"answered={r.answered}, expected {r.answerable}")
        if r.must_include_ok is False:
            problems.append("missing must_include")
        if r.violations:
            problems.append(f"must_not_include violated: {r.violations}")
        if r.retrieval_hit is False:
            problems.append("expected source not retrieved")
        lines += [f"- **{r.question}** — {'; '.join(problems)}", f"  - Answer: {r.answer}"]
    return "\n".join(lines) + "\n"


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant", required=True, help="tenant slug, e.g. demo-bakery")
    parser.add_argument("--fake", action="store_true", help="FakeEmbedder + FakeLLM (no API cost)")
    args = parser.parse_args()
    configure_logging("WARNING", json=False)

    embedder: Embedder = FakeEmbedder() if args.fake else get_embedder()
    llm: LLMClient = FakeLLM() if args.fake else get_llm()
    try:
        results = await run(args.tenant, embedder, llm)
    finally:
        await dispose_engine()
        await close_redis()
    text = report(args.tenant, results, llm.model, embedder.name, args.fake)
    out = (
        EVALS
        / "reports"
        / (f"{datetime.now(UTC):%Y-%m-%d}-{args.tenant}{'-fake' if args.fake else ''}.md")
    )
    out.parent.mkdir(exist_ok=True)
    out.write_text(text)
    print(text)
    print(f"Report written to {out.relative_to(EVALS.parent)}")


if __name__ == "__main__":
    asyncio.run(main())
