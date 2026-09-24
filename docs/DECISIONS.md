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

### D-007 Invite acceptance identifies the invitee by email
**Context.** SPEC §8 says the invitee "sets name + password (or logs in if the email exists)",
but invites carry no email (§6.1). **Decision.** `POST /auth/invites/{token}/accept` takes
`{email, password, name?}`: an existing email must present its password; a new email needs a
name and a password that passes the password policy. A signed-in user can instead send an empty
body with their bearer token. **Consequence.** One endpoint covers all three cases; invites stay
shareable links that aren't tied to an address.

### D-008 Common-password list
**Context.** SPEC §8 asks to reject the top 1,000 common passwords. **Decision.** Ship
`api/app/core/common_passwords.txt`: the 1,000 most common passwords of 8+ characters from
SecLists' `10k-most-common.txt` (MIT). Shorter ones are already rejected by the length rule.
**Consequence.** The list covers passwords that would otherwise pass the length check.

### D-009 Refresh-token reuse detection is strict
**Context.** Rotation on every use means two tabs refreshing at once could present the same
token twice. **Decision.** Keep strict family revocation (as specified) and have the web client
share one in-flight refresh promise across the page. **Consequence.** Replay of any rotated
token logs every session in that family out, which is the intended theft signal.

### D-010 DTOs keep snake_case on the web
**Context.** SPEC §26 asks to pick either mapping to camelCase at the API client boundary or
keeping snake_case in DTO types. **Decision.** Keep snake_case in `web/lib/types.ts`.
**Consequence.** No mapping layer to maintain; field names match the OpenAPI schema and backend
tests one-to-one. camelCase is still used for local variables and props.

### D-011 Session bootstrap is lazy
**Context.** SPEC §8 says the web app calls `POST /auth/refresh` on page load. Most traffic is
customers on public storefront pages, who never have a session. **Decision.** The refresh runs
the first time a page that needs the session mounts (`useSession()`: dashboard, admin, auth
pages, invites). **Consequence.** Storefront and tracking pages make no auth calls.

### D-012 Storefront caching in two layers
**Context.** SPEC §9.1/§14.2 ask for a cached public storefront and 60 s revalidation on the
web. **Decision.** The API caches the storefront JSON per tenant in Redis for 60 s and deletes
the key after any committed change to settings, menu or availability; slug → tenant id is cached
separately (slugs are immutable). The Next.js page uses `revalidate = 60`. **Consequence.**
Owners see changes on the API immediately; customers see them within a minute (ISR window).

### D-013 Menu reorder within categories; moving between categories via edit
**Context.** SPEC §14.1 asks for drag-to-reorder. **Decision.** Categories and the items inside
each category are reordered by drag (dnd-kit, with keyboard support). Moving an item to another
category is done from its edit dialog. The API's `/menu/reorder` still accepts cross-category
moves. **Consequence.** Simpler, accessible drag interactions on mobile.

### D-014 Public storefront shows only available items
**Context.** SPEC §9.1 says the storefront returns "available, non-deleted items".
**Decision.** Follow it literally: sold-out items are hidden rather than shown as sold out.
**Consequence.** Toggling availability is the owner's "sold out" switch.

### D-015 Status events keep an optional note
**Context.** `POST /orders/{id}/transition` accepts `{to_status, reason?}` (SPEC §9.1), but
`order_status_events` (§6.3) has nowhere to store the reason. **Decision.** Add a nullable
`note` column. **Consequence.** Cancellation reasons show on the merchant timeline and on the
customer's tracking page.

### D-016 Effects of the state machine map to outbox jobs
**Context.** SPEC §10.1 wants `transition(order, to, actor) -> list[Effect]`. **Decision.**
Effects are `NotifyOwnerNewOrder`, `NotifyCustomerStatus(status)` and `RefundRequired`.
`services.orders.apply_effects` turns the first two into outbox rows (customer emails only when
the customer gave an email); `RefundRequired` surfaces as `refund_required` on the order.
The initial `placed` status also emails the customer a confirmation. **Consequence.** The state
machine stays pure and exhaustively tested; all I/O sits in one translation function.

### D-017 Analytics top items over the whole range
**Context.** `/dashboard/summary` returns top items for one day, but the analytics page shows
top items for the chart's range. **Decision.** `/dashboard/sales` also returns `top_items` for
its window. Two separate column charts (revenue, orders) instead of one dual-axis chart.
**Consequence.** One request per range change; charts follow the dataviz single-axis rule.
