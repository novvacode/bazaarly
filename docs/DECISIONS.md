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

### D-018 Why a hand-built queue instead of Celery / RQ / arq / Dramatiq
**Context.** SPEC §12 asks for a custom queue. **Decision.** Build it on Redis Streams:
consumer groups give at-least-once delivery and crash recovery (`XPENDING`/`XAUTOCLAIM`), a
sorted set gives delayed jobs, and three small Lua scripts make the state changes atomic.
Reasons: (1) learning value and a strong interview story, (2) exact control over the delivery
semantics (dedupe keys, jittered backoff, dead-letter contents), (3) fewer moving parts — no
separate broker config, beat process or result backend, and (4) the transactional outbox
integrates naturally, whereas Celery would still need an outbox to be correct.
**Consequence.** ~400 lines of queue code we own and test directly (SPEC §12.8 suite). Features
we don't need (chains, chords, rate-limited queues, priorities) are simply absent.

### D-019 Recovered deliveries count as an attempt
**Context.** A job whose handler crashes the worker would otherwise be reclaimed forever.
**Decision.** Reclaimed entries are processed with `attempt + 1`; if that exhausts
`max_attempts` they go to the dead-letter stream as `WorkerCrashed`. **Consequence.** Poison
messages end up visible on `/admin` instead of looping.

### D-020 Email in tests and local development
**Context.** Tests must never call real providers (SPEC §19). **Decision.** `EMAIL_PROVIDER`
also accepts `memory`, used by tests; local development uses SMTP to Mailpit as specified.
**Consequence.** Handler tests assert on rendered subject, text and escaped HTML.

### D-021 Platform-level Razorpay keys (known limitation)
**Context.** SPEC §11 scopes the MVP to Razorpay test mode with the platform's own keys.
**Decision.** All online payments go to one Razorpay account; `notes` carry `tenant_id` and
`order_id`. **Consequence.** Real payouts to each merchant (Razorpay Route or per-merchant
keys) are out of scope (§25); going live needs one of those before real money flows.

### D-022 Payment params endpoint for retries
**Context.** A failed or abandoned payment leaves the order `pending_payment` so the customer
can retry until expiry (§11), but the tracking page needs Checkout parameters to retry.
**Decision.** Add `GET /public/orders/{token}/payment`, returning the existing Razorpay order's
params (creating it if the first attempt failed); 409 once the order no longer needs payment.
**Consequence.** The tracking page shows "Pay now" while payment is pending.

### D-023 Storefront advertises whether online payment is available
**Context.** Online payment requires Razorpay keys; local setups usually have none.
**Decision.** `PublicBusiness.accepts_online_payments` is true only when keys are configured;
checkout disables the option otherwise, and the API rejects `payment_method=online` with 422.
**Consequence.** Local development works end to end with cash on delivery.

### D-024 Webhook processing is marked done only after its effect commits
**Context.** A handler that set `processed_at` before calling `mark_paid` could lose the payment
if the worker crashed in between. **Decision.** Apply the effect first (idempotent), then set
`processed_at` in a separate update. **Consequence.** Crashes cause a harmless re-run, never a
lost payment.

### D-025 Assistant chunks carry a title
**Context.** API `sources` must show "item name / FAQ / Business info" (SPEC §13.4) but
`kb_chunks` (§6.5) has no title. **Decision.** Add `title` to `kb_chunks` (the item name, or
"FAQ" / "Business info"). **Consequence.** Sources render without extra joins.

### D-026 Content hash includes the embedding model
**Context.** Re-embedding is skipped when `content_hash` is unchanged (§13.1), but vectors from
different models are not comparable. **Decision.** Hash `embedder name + text`. **Consequence.**
Switching `EMBEDDER` (or upgrading the model) re-embeds everything on the next reindex instead
of silently mixing vector spaces.

### D-027 Grounded output via structured outputs, with defensive parsing kept
**Context.** SPEC §13.4 asks for JSON `{answer, answered, used_chunk_ids}` parsed defensively.
**Decision.** Request it with `output_config.format` (JSON schema; supported by the default
`claude-haiku-4-5`) and still parse defensively (fences, stray text), treating refusals,
truncation and API errors as "not answered". When the model says `answered: false`, the API
always returns the exact fallback sentence rather than the model's wording, and `sources` only
include chunk ids that were actually retrieved. **Consequence.** No invented non-answers reach
customers; bad output degrades to the fallback, never to an error.

### D-028 Temperature through `extra_body`
**Context.** SPEC §13.4 sets temperature 0.2. The Anthropic Python SDK 1.x removed sampling
parameters from `messages.create()`; newer models reject them. **Decision.** Send
`extra_body={"temperature": 0.2}` only for models that still accept sampling parameters (the
default Haiku 4.5 does); omit it for models that reject it. **Consequence.** `LLM_MODEL` can be
switched to a newer model without a code change.

### D-029 First eval report is pending a real run
**Context.** SPEC §24 Phase 6 asks for a committed first eval report, which needs the real
embedding model and an Anthropic API key. **Decision.** The harness, both ~40-question datasets
and a `--fake` mode (used by the test suite to check the harness) are committed; no fake-mode
report is committed because its numbers don't measure answer quality. **Consequence.** Run
`make eval t=demo-bakery` and `make eval t=demo-tiffin` with `ANTHROPIC_API_KEY` set after
`make seed` and one worker pass, then commit `api/evals/reports/*.md`.
