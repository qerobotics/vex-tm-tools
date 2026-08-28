"""Pydantic schemas mirroring `backend.models.team` (plan §8)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TeamProfileBase(BaseModel):
    pit_location: str | None = Field(default=None, max_length=100)
    bio: str | None = None
    robot_name: str | None = Field(default=None, max_length=100)
    extra_notes: str | None = None


class TeamProfileUpdate(TeamProfileBase):
    pass


class TeamProfileRead(TeamProfileBase):
    model_config = ConfigDict(from_attributes=True)

    team_number: str
    video_360_s3_key: str | None = None
    video_processing_status: str = "NONE"
    cached_stats: dict[str, Any] | None = None
    updated_at: datetime
