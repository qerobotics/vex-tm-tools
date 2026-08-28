"""Pydantic schema mirroring `backend.models.audit` (plan §8)."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: str | None = None
    action: str
    resource_type: str | None = None
    resource_id: str | None = None
    changes: dict[str, Any] | None = None
    ip_address: str | None = None
    created_at: datetime
