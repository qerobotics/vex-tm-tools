"""ORM models for timer_instances and prompter_cues (plan §8).

Wave 2b addendum: the plan's §8 schema for `timer_instances` did not include
a countdown-duration column even though Appendix A.3 explicitly resolves
"Countdown duration" as "Configurable per Timer instance in the UI (a number
field, in seconds)". `duration_s` (and `token_nonce`, needed for Appendix
B.8's regeneratable teleprompter HMAC token) are added here via a new Alembic
migration (`alembic/versions/..._add_timer_duration_and_token_nonce.py`)
rather than hand-editing Wave 1's already-merged initial migration.
"""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.db import Base

#: Default countdown duration (seconds) for newly created Timer instances
#: when the operator doesn't specify one. Chosen to match a typical VEX
#: match length (15s autonomous + 105s driver control).
DEFAULT_TIMER_DURATION_S = 120


class TimerInstance(Base):
    __tablename__ = "timer_instances"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    entity_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(150), nullable=False)
    field_set_id: Mapped[int] = mapped_column(Integer, nullable=False)
    field_id: Mapped[int] = mapped_column(Integer, nullable=False)
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    enabled: Mapped[bool] = mapped_column(Boolean, server_default="true")
    # ── Wave 2b additions (see module docstring) ────────────────────────
    duration_s: Mapped[int] = mapped_column(
        Integer, server_default=str(DEFAULT_TIMER_DURATION_S), nullable=False
    )
    token_nonce: Mapped[str] = mapped_column(
        String(64), default=lambda: secrets.token_urlsafe(16), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (Index("ix_timer_instances_tags", "tags", postgresql_using="gin"),)


class PrompterCue(Base):
    __tablename__ = "prompter_cues"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    timer_entity_id: Mapped[str] = mapped_column(String(100), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(String(30), server_default="script")
    sort_order: Mapped[int] = mapped_column(Integer, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true")
    created_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
