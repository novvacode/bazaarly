"""Tenant context passed to every tenant-scoped repository call (SPEC §7)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.models.user import Role


@dataclass(frozen=True, slots=True)
class TenantContext:
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    role: Role

    @property
    def is_owner(self) -> bool:
        return self.role == Role.owner
