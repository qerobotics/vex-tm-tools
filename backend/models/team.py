"""ORM model for team_profiles (plan §8)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.db import Base


class TeamProfile(Base):
    __tablename__ = "team_profiles"

    team_number: Mapped[str] = mapped_column(String(20), primary_key=True)
    pit_location: Mapped[str | None] = mapped_column(String(100), nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    robot_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    video_360_s3_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    video_processing_status: Mapped[str] = mapped_column(String(20), server_default="NONE")
    cached_stats: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    extra_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )
