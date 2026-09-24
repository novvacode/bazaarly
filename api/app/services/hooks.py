"""Cross-cutting reactions to domain changes (cache invalidation, re-indexing).

Kept in one place so later phases can extend them without touching every service.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession


async def on_tenant_changed(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    """Called inside the transaction that changed tenant settings."""
    return None
