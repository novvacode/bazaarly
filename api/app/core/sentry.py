"""Optional Sentry wiring: a no-op unless `SENTRY_DSN` is set (SPEC §18)."""

from __future__ import annotations

from app.config import Settings


def init_sentry(settings: Settings, *, component: str) -> bool:
    if not settings.sentry_dsn:
        return False
    import sentry_sdk

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.app_env,
        traces_sample_rate=0.1,
        send_default_pii=False,
    )
    sentry_sdk.set_tag("component", component)
    return True
