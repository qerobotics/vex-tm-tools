"""Pydantic schemas mirroring `backend.models.integration` (plan §8)."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class IntegrationInstanceBase(BaseModel):
    entity_id: str = Field(..., max_length=100)
    domain: str = Field(..., max_length=50)
    display_name: str = Field(..., max_length=150)
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    tags: list[str] = Field(default_factory=list)


class IntegrationInstanceCreate(IntegrationInstanceBase):
    pass


class IntegrationInstanceUpdate(BaseModel):
    display_name: str | None = None
    config: dict[str, Any] | None = None
    enabled: bool | None = None
    tags: list[str] | None = None


class IntegrationInstanceRead(IntegrationInstanceBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: str
    created_at: datetime
    updated_at: datetime


class IntegrationTestResult(BaseModel):
    """Response shape for `POST /{entity_id}/test` (plan §12 Integrations
    page "Test Connection" button, finding 1.11)."""

    ok: bool
    message: str | None = None
    detail: str | None = None


class ZerosPresetBase(BaseModel):
    preset_number: int
    preset_name: str = Field(..., max_length=100)
    description: str | None = None


class ZerosPresetCreate(ZerosPresetBase):
    integration_id: UUID


class ZerosPresetRead(ZerosPresetBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    integration_id: UUID
