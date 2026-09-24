"""Test fixtures: real Postgres + Redis (SPEC §19).

The test database is migrated once per session. Every test starts from empty tables
(TRUNCATE) and an empty Redis test DB, so tests can use real commits and real
concurrency. See docs/DECISIONS.md ("Test isolation by truncation").
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://bazaarly:bazaarly@localhost:5432/bazaarly_test"
)
os.environ["REDIS_URL"] = os.environ.get("TEST_REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("LLM_PROVIDER", "fake")
os.environ.setdefault("EMBEDDER", "fake")
os.environ.setdefault("EMAIL_PROVIDER", "memory")
os.environ.setdefault("JWT_SECRET", "test-secret-" + "x" * 40)
os.environ.setdefault("RAZORPAY_KEY_ID", "rzp_test_key")
os.environ.setdefault("RAZORPAY_KEY_SECRET", "rzp_test_secret")
os.environ.setdefault("RAZORPAY_WEBHOOK_SECRET", "rzp_webhook_secret")
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("APP_BASE_URL", "http://localhost:3000")

import pytest
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from alembic import command
from app.config import get_settings
from app.db import dispose_engine, get_engine, get_sessionmaker
from app.integrations.storage import MemoryStorage, get_storage
from app.main import create_app
from app.models.base import Base
from app.redis import close_redis, get_redis

API_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _migrate() -> None:
    cfg = Config(os.path.join(API_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(API_DIR, "alembic"))
    cfg.set_main_option("sqlalchemy.url", get_settings().database_url)
    command.upgrade(cfg, "head")


@pytest.fixture(scope="session", autouse=True)
def _migrated_db() -> None:
    _migrate()


@pytest.fixture(scope="session")
async def _engine_lifecycle() -> AsyncIterator[None]:
    yield
    await dispose_engine()
    await close_redis()


@pytest.fixture
async def clean_state(_engine_lifecycle: None) -> None:
    """Empty every table and the Redis test DB (autouse for tests/integration)."""
    tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    async with get_engine().begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    await get_redis().flushdb()


@pytest.fixture
async def session(clean_state: None) -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as s:
        yield s


@pytest.fixture
def storage() -> MemoryStorage:
    return MemoryStorage()


@pytest.fixture(scope="session")
def app():  # type: ignore[no-untyped-def]
    return create_app()


@pytest.fixture(autouse=True)
def _override_storage(app, storage: MemoryStorage):  # type: ignore[no-untyped-def]
    app.dependency_overrides[get_storage] = lambda: storage
    yield
    app.dependency_overrides.pop(get_storage, None)


@pytest.fixture
def rate_limits_on():  # type: ignore[no-untyped-def]
    settings = get_settings()
    settings.rate_limit_enabled = True
    yield
    settings.rate_limit_enabled = False


@pytest.fixture
async def client(app, clean_state: None) -> AsyncIterator[AsyncClient]:  # type: ignore[no-untyped-def]
    transport = ASGITransport(app=app, client=("127.0.0.1", 12345))
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c
