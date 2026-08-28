"""Pydantic schemas mirroring `backend.models.automation` (plan §8)."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AutomationFolderBase(BaseModel):
    name: str = Field(..., max_length=150)
    parent_id: UUID | None = None


class AutomationFolderCreate(AutomationFolderBase):
    pass


class AutomationFolderRead(AutomationFolderBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime


class AutomationBase(BaseModel):
    folder_id: UUID | None = None
    alias: str = Field(..., max_length=200)
    enabled: bool = True
    trigger_yaml: str
    condition_yaml: str | None = None
    action_yaml: str


class AutomationCreate(AutomationBase):
    pass


class AutomationUpdate(BaseModel):
    folder_id: UUID | None = None
    alias: str | None = None
    enabled: bool | None = None
    trigger_yaml: str | None = None
    condition_yaml: str | None = None
    action_yaml: str | None = None


class AutomationRead(AutomationBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    last_triggered_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ScriptBase(BaseModel):
    name: str = Field(..., max_length=150)
    description: str | None = None
    action_yaml: str


class ScriptCreate(ScriptBase):
    pass


class ScriptUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    action_yaml: str | None = None


class ScriptRead(ScriptBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime
