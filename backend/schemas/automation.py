"""Pydantic schemas mirroring `backend.models.automation` (plan §8).

Wave 3a additions: `AutomationRunRead` (Appendix A.7 execution history),
`ValidateRequest`/`ValidateResponse` (Appendix A.7's "Validate" button — YAML
+ Jinja2 syntax check, no service execution), and `TriggerResponse` (the
result shape returned by `POST /api/v1/automations/{id}/trigger`, which
delegates to `AutomationEngine.trigger()`).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AutomationFolderBase(BaseModel):
    name: str = Field(..., max_length=150)
    parent_id: UUID | None = None


class AutomationFolderCreate(AutomationFolderBase):
    pass


class AutomationFolderUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=150)
    parent_id: UUID | None = None


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


class AutomationRunRead(BaseModel):
    """One row of an automation's execution history (Appendix A.7)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    automation_id: UUID
    triggered_at: datetime
    trigger_event: dict[str, Any] | None = None
    status: str
    failed_action_index: int | None = None
    error: str | None = None
    created_at: datetime


class ValidateRequest(BaseModel):
    """Body for the "Validate" button's backend (Appendix A.7): checks YAML
    syntax + Jinja2 expression syntax without executing any services."""

    trigger_yaml: str
    condition_yaml: str | None = None
    action_yaml: str


class ValidateResponse(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)


class TriggerResponse(BaseModel):
    """Result of `AutomationEngine.trigger()` (Test Run button, plan §12)."""

    automation_id: UUID
    status: str
    failed_action_index: int | None = None
    error: str | None = None
    actions_executed: int = 0
