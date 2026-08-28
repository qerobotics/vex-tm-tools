"""Pydantic schemas mirroring `backend.models.timer` (plan §8)."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TimerInstanceBase(BaseModel):
    entity_id: str = Field(..., max_length=100)
    display_name: str = Field(..., max_length=150)
    field_set_id: int
    field_id: int
    tags: list[str] = Field(default_factory=list)
    enabled: bool = True


class TimerInstanceCreate(TimerInstanceBase):
    pass


class TimerInstanceUpdate(BaseModel):
    display_name: str | None = None
    field_set_id: int | None = None
    field_id: int | None = None
    tags: list[str] | None = None
    enabled: bool | None = None


class TimerInstanceRead(TimerInstanceBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime


class PrompterCueBase(BaseModel):
    timer_entity_id: str = Field(..., max_length=100)
    content: str
    type: str = Field(default="script", max_length=30)
    sort_order: int = 0
    is_active: bool = True


class PrompterCueCreate(PrompterCueBase):
    pass


class PrompterCueRead(PrompterCueBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_by: str | None = None
    created_at: datetime
