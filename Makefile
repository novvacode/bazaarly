# Bazaarly — developer commands (SPEC §21). Run `make help` for a list.
SHELL := /bin/bash
API := cd api &&
WEB := cd web &&

.DEFAULT_GOAL := help
.PHONY: help up down install migrate migration seed api worker web dev test test-api test-web \
        lint fmt e2e eval audit

help: ## Show this help
	@grep -hE '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

up: ## Start infra containers (postgres, redis, minio, mailpit)
	docker compose up -d postgres redis minio minio-init mailpit

down: ## Stop infra containers
	docker compose down

install: ## Install backend (uv) and frontend (pnpm) dependencies
	$(API) uv sync
	$(WEB) pnpm install

migrate: ## Apply database migrations
	$(API) uv run alembic upgrade head

migration: ## Autogenerate a migration: make migration m="add foo"
	$(API) uv run alembic revision --autogenerate -m "$(m)"

seed: ## Create platform admin + demo tenants and print credentials
	$(API) uv run python -m scripts.seed

api: ## Run the API with hot reload
	$(API) uv run uvicorn app.main:app --reload --port 8000

worker: ## Run the job worker
	$(API) uv run python -m app.queue.worker

web: ## Run the web app with hot reload
	$(WEB) pnpm dev

dev: ## Run api, worker and web together
	$(API) uv run honcho -d .. -f ../Procfile start

test: test-api test-web ## Backend tests + frontend lint/typecheck

test-api:
	$(API) uv run pytest --cov --cov-report=term-missing:skip-covered

test-web:
	$(WEB) pnpm lint && pnpm typecheck

lint: ## Lint everything (ruff, mypy, eslint, prettier)
	$(API) uv run ruff check . && uv run ruff format --check . && uv run mypy
	$(WEB) pnpm lint && pnpm format:check

fmt: ## Format everything
	$(API) uv run ruff check --fix . && uv run ruff format .
	$(WEB) pnpm format

e2e: ## Playwright E2E against a running stack
	$(WEB) pnpm e2e

eval: ## Run the assistant eval: make eval t=demo-bakery
	$(API) uv run python -m evals.run --tenant $(t)

audit: ## Dependency audit (non-blocking in CI)
	$(API) uv run pip-audit || true
	$(WEB) pnpm audit --prod || true
