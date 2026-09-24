"""Worker entrypoint: `python -m app.queue.worker`. Implemented in Phase 4 (SPEC §12)."""

import asyncio

import structlog

from app.config import get_settings
from app.core.logging import configure_logging


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, json=settings.app_env != "local")
    structlog.get_logger("worker").info("worker_idle", reason="queue arrives in Phase 4")
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
