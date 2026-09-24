"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.core.sentry import init_sentry
from app.db import dispose_engine
from app.redis import close_redis
from app.routers import admin, auth, health, menu, orders, public, tenant

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await dispose_engine()
    await close_redis()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, json=settings.app_env != "local")
    init_sentry(settings, component="api")

    app = FastAPI(
        title="Bazaarly API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        openapi_url="/openapi.json",
    )
    install_error_handlers(app)

    # Liveness/readiness at the root for platform health checks, and under the API
    # prefix so the web app can reach them through its /api rewrite.
    app.include_router(health.router)
    app.include_router(health.router, prefix=API_PREFIX)
    for module in (auth, tenant, menu, orders, public, admin):
        app.include_router(module.router, prefix=API_PREFIX)

    if settings.cors_origin_list and not settings.is_production:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=["X-Request-ID"],
        )
    app.add_middleware(RequestContextMiddleware)
    return app


app = create_app()
