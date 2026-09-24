"""Database engine and session factory (SQLAlchemy 2.0 async + asyncpg)."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Any

import structlog
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings

log = structlog.get_logger("db")

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _install_slow_query_logger(engine: AsyncEngine, threshold_ms: int) -> None:
    sync_engine = engine.sync_engine

    @event.listens_for(sync_engine, "before_cursor_execute")
    def _before(conn: Any, cursor: Any, statement: str, *args: Any) -> None:
        conn.info.setdefault("query_start", []).append(time.perf_counter())

    @event.listens_for(sync_engine, "after_cursor_execute")
    def _after(conn: Any, cursor: Any, statement: str, *args: Any) -> None:
        started = conn.info["query_start"].pop()
        elapsed_ms = (time.perf_counter() - started) * 1000
        if elapsed_ms >= threshold_ms:
            log.warning("slow_query", duration_ms=round(elapsed_ms, 1), sql=statement[:500])


def get_engine() -> AsyncEngine:
    global _engine, _sessionmaker
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            pool_size=10,
            max_overflow=10,
            pool_pre_ping=True,
        )
        _install_slow_query_logger(_engine, settings.slow_query_ms)
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    get_engine()
    assert _sessionmaker is not None
    return _sessionmaker


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request. Services commit explicitly."""
    async with get_sessionmaker()() as session:
        yield session
