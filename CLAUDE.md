# CLAUDE.md — Bazaarly

Multi-tenant ordering platform for small local businesses (storefront, orders, Razorpay payments, hand-built Redis job queue, tenant-scoped RAG assistant).

## Read first
- **`docs/SPEC.md` is the source of truth.** Read §0 (instructions) and the current phase in §24 before doing anything.
- `docs/DECISIONS.md` records every deviation or judgement call. Add to it; don't silently diverge from the spec.

## Current phase
Phase 3 — Orders (COD) and dashboard. (Update this line when a phase completes.)

## Working rules
1. Build one phase at a time. Start each phase by writing a short plan (files + order), then implement.
2. Don't start the next phase until the current phase's checklist in SPEC §24 is fully ticked and `make test` + `make lint` pass.
3. Layering: routers → services → repositories → models. Only repositories build queries. Every tenant-scoped repository method takes a `TenantContext`.
4. Every new tenant-scoped route must be added to `tests/integration/test_tenant_isolation.py`.
5. Money is integer paise. Times are UTC `timestamptz`. IDs are UUIDs.
6. Jobs are enqueued only via `enqueue_in_tx` (outbox). Never send email or call external APIs inside a request handler.
7. Tests never call real Razorpay, Resend, or Anthropic — use respx, `FakeLLM`, `FakeEmbedder`.
8. Nothing from SPEC §25 (Out of scope).
9. Ask the human only for irreversible decisions, spending money, or credentials. Otherwise decide, record in DECISIONS.md, continue.
10. Conventional Commits, one logical change per commit.

## Commands
```
make up            # infra containers (postgres, redis, minio, mailpit)
make install       # uv sync + pnpm install
make migrate       # alembic upgrade head
make seed          # demo data + credentials
make dev           # api + worker + web with hot reload
make test          # backend tests + web lint/typecheck
make lint / fmt
make e2e           # Playwright
make eval t=demo-bakery
```

Local URLs: web http://localhost:3000 · API docs http://localhost:8000/docs · Mailpit http://localhost:8025 · MinIO console http://localhost:9001
