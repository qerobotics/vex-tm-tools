"""Pydantic schema mirroring `backend.models.audit` (plan §8)."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator


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

    @field_validator("ip_address", mode="before")
    @classmethod
    def _stringify_ip_address(cls, value: object) -> str | None:
        """`AuditLog.ip_address` is a Postgres `INET` column — with the
        asyncpg driver this round-trips as an `ipaddress.IPv4Address`/
        `IPv6Address` object, not a `str`, which fails this field's `str`
        validation. Previously invisible because the column was always
        NULL (see `backend.core.audit.current_request_ip`); now that
        real requests populate it, coerce non-string address objects to
        their string form here instead."""
        return value if value is None or isinstance(value, str) else str(value)
