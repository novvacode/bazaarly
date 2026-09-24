# Decisions

Each entry: **context → decision → consequence**. Newest at the bottom. Deviations from
`docs/SPEC.md` are marked **(deviation)**.

---

### D-001 Stack as specified
**Context.** SPEC §3 fixes the stack. **Decision.** FastAPI + SQLAlchemy 2 (async) + Alembic +
Postgres/pgvector + Redis on the backend; Next.js App Router + Tailwind + shadcn/ui + TanStack
Query on the web. Exact versions are pinned by `api/uv.lock` and `web/pnpm-lock.yaml`.
**Consequence.** Next.js resolved to 16.x (Turbopack by default, async request APIs, `proxy.ts`
instead of `middleware.ts`); code follows the version-matched docs in
`web/node_modules/next/dist/docs/`.

### D-002 shadcn/ui components are vendored by hand
**Context.** The shadcn CLI downloads components from its registry. **Decision.** Components in
`web/components/ui/` are written directly (same source shape as shadcn's new-york v4 style, on
the unified `radix-ui` package). **Consequence.** No CLI step in setup; components are ordinary
source files that can be edited or re-synced with the CLI later.

### D-003 System font stack instead of `next/font/google`
**Context.** `next/font/google` fetches fonts at build time, which fails in network-restricted
builds. **Decision.** Use the platform UI font stack. **Consequence.** Builds are hermetic; no
font download; the look is native on each device, which suits a mobile-first storefront.

### D-004 Health endpoints mounted twice
**Context.** SPEC §9.1 lists `/health` and `/health/ready`; everything else is under `/api/v1`.
Hosting platforms probe the bare path, and the web app can only reach the API through its
`/api/*` rewrite. **Decision.** Mount the health router at `/` and at `/api/v1`.
**Consequence.** `GET /health` works for platform/Docker health checks, and
`GET /api/v1/health/ready` works from the browser.

### D-005 Test isolation by truncation (deviation)
**Context.** SPEC §19 suggests rolling back a transaction per test. Several mandatory suites
(20 concurrent order codes, concurrent `mark_paid`, queue relay with `SKIP LOCKED`) need real
commits on separate connections, which a per-test rollback cannot represent. **Decision.** Tests
run against a dedicated `bazaarly_test` database migrated once per session; an autouse fixture
`TRUNCATE`s every table and `FLUSHDB`s a dedicated Redis DB (index 15) before each test.
**Consequence.** One uniform strategy; concurrency tests exercise real Postgres locking. Cost is
a few milliseconds per test.

### D-006 Refresh tokens remember the active tenant
**Context.** Access tokens carry `tid` (SPEC §8), but the refresh endpoint only sees the cookie,
so after a refresh it wouldn't know which tenant the user was using. **Decision.** Add a nullable
`tenant_id` column to `refresh_tokens`; rotation copies it and `switch-tenant` updates it.
**Consequence.** Silent refresh keeps the user in the same tenant. If the membership was
removed, refresh falls back to the user's first remaining membership (or none).
