"""Pydantic schemas for /healthz and /readyz responses."""
from __future__ import annotations

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str = "ok"


class ReadyResponse(BaseModel):
    status: str  # "ok" | "degraded"
    db: bool
    redis: bool
