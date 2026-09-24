api: cd api && uv run uvicorn app.main:app --reload --port 8000
worker: cd api && uv run python -m app.queue.worker
web: cd web && pnpm dev
