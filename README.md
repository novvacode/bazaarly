# Bazaarly

Multi-tenant online ordering for small local businesses: home bakeries, tiffin services, small
studios and craft shops. Each business gets a public storefront customers open from a WhatsApp
or Instagram link, an owner dashboard, online payments or cash on delivery, email notifications,
and an AI assistant that answers customer questions using only that business's own data.

> **Status:** under active development, built phase by phase from [`docs/SPEC.md`](docs/SPEC.md).
> See the phase checklist in SPEC §24 for what's done.

## Stack

| Layer | Tech |
|---|---|
| Web | Next.js (App Router) · TypeScript · Tailwind · shadcn/ui · TanStack Query |
| API | Python 3.12 · FastAPI · SQLAlchemy 2 (async) · Alembic · Pydantic v2 |
| Data | PostgreSQL 16 + pgvector · Redis 7 (cache, rate limits, job queue) |
| Infra | Docker Compose locally · GitHub Actions CI · Vercel + Railway |

Architecture: [`docs/architecture.md`](docs/architecture.md). Design decisions:
[`docs/DECISIONS.md`](docs/DECISIONS.md).

## Quick start

Prerequisites: Docker, [uv](https://docs.astral.sh/uv/), Node 22 with pnpm.

```bash
git clone https://github.com/novvacode/SDD.git bazaarly && cd bazaarly
cp .env.example .env
make up install migrate seed
make dev
```

| URL | What |
|---|---|
| http://localhost:3000 | Web app |
| http://localhost:8000/docs | API docs (OpenAPI) |
| http://localhost:8025 | Mailpit (local email inbox) |
| http://localhost:9001 | MinIO console (minioadmin / minioadmin) |

### Demo accounts (after `make seed`)

| Who | Email | Password |
|---|---|---|
| Platform admin | admin@example.com | admin-password-123 |
| Demo Bakery owner / staff | bakery.owner@example.com / bakery.staff@example.com | demo-password-123 |
| Demo Tiffin owner / staff | tiffin.owner@example.com / tiffin.staff@example.com | demo-password-123 |

Storefronts: http://localhost:3000/b/demo-bakery and http://localhost:3000/b/demo-tiffin.
The businesses are fictional.

## Common commands

```bash
make help          # list all targets
make test          # backend tests + web lint/typecheck
make lint / fmt    # ruff, mypy, eslint, prettier
make migration m="add foo"
```

Backend tests need Postgres and Redis running (`make up`); they use a separate `bazaarly_test`
database and Redis DB 15, so they never touch your dev data.

## Online payments locally (optional)

Online payments use Razorpay **test mode**. Set `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`
and `RAZORPAY_WEBHOOK_SECRET` in `.env`. Without them the storefront offers cash on
delivery only.

To receive webhooks on your machine, expose the API with a tunnel and point a Razorpay test
webhook (events `payment.captured`, `payment.failed`, `order.paid`) at it:

```bash
cloudflared tunnel --url http://localhost:3000
# webhook URL: https://<random>.trycloudflare.com/api/v1/webhooks/razorpay
```

## AI assistant

Each storefront has a chat assistant that answers only from that business's own menu, FAQ
and details (tenant-scoped retrieval over pgvector, answers from `claude-haiku-4-5` by
default). The worker keeps the knowledge base in sync as the menu changes.

- Locally without keys: set `LLM_PROVIDER=fake` and `EMBEDDER=fake` in `.env`.
- Real answers: set `ANTHROPIC_API_KEY` (and keep `EMBEDDER=fastembed`; the model downloads
  on first use and is baked into the API Docker image).
- Evals: `make eval t=demo-bakery` writes `api/evals/reports/<date>-demo-bakery.md`
  (`--fake` checks the harness without API cost).

## Repository layout

```
api/     FastAPI app, worker, migrations, tests, evals
web/     Next.js app
docs/    SPEC, architecture, decisions
infra/   container init scripts
```
