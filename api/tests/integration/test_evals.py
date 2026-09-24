"""The eval harness runs end to end on seeded data (with fakes; real runs cost money)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.rag.embedder import FakeEmbedder
from app.rag.llm import FakeLLM
from evals.run import load_dataset, report, run, summarize
from scripts.seed import seed_tenant
from scripts.seed_data import TENANTS


def test_datasets_are_well_formed() -> None:
    for slug in ("demo-bakery", "demo-tiffin"):
        items = load_dataset(slug)
        assert 35 <= len(items) <= 50
        for item in items:
            assert isinstance(item["question"], str)
            assert isinstance(item["answerable"], bool)
            src = item.get("expected_source")
            assert (
                src is None
                or src == "business_info"
                or src.split(":")[0]
                in {
                    "menu_item",
                    "faq",
                }
            )


async def test_harness_runs_on_seeded_tenant(session: AsyncSession) -> None:
    spec = next(t for t in TENANTS if t["tenant"]["slug"] == "demo-tiffin")
    await seed_tenant(session, spec)
    results = await run("demo-tiffin", FakeEmbedder(), FakeLLM())
    assert len(results) == len(load_dataset("demo-tiffin"))
    summary = summarize(results)
    assert len(summary["answerability"]) == len(results)
    text = report("demo-tiffin", results, "fake-llm", "fake-hash-embedder", fake=True)
    assert "| Answerability accuracy |" in text
    assert "Mode: fake" in text
