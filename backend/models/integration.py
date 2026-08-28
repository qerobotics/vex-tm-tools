"""ORM models for integration_instances and zeros_presets (plan §8)."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.db import Base


class IntegrationInstance(Base):
    __tablename__ = "integration_instances"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    entity_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    domain: Mapped[str] = mapped_column(String(50), nullable=False)
    display_name: Mapped[str] = mapped_column(String(150), nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, server_default="true")
    status: Mapped[str] = mapped_column(String(20), server_default="DISCONNECTED")
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    zeros_presets: Mapped[list["ZerosPreset"]] = relationship(
        back_populates="integration", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_integration_instances_tags", "tags", postgresql_using="gin"),)


class ZerosPreset(Base):
    __tablename__ = "zeros_presets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    integration_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("integration_instances.id"), nullable=False
    )
    preset_number: Mapped[int] = mapped_column(Integer, nullable=False)
    preset_name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    integration: Mapped["IntegrationInstance"] = relationship(back_populates="zeros_presets")

    __table_args__ = (
        UniqueConstraint("integration_id", "preset_number"),
        UniqueConstraint("integration_id", "preset_name"),
    )
