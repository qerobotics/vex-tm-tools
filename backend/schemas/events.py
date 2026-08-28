"""Canonical event bus message schema (plan §C.4).

FROZEN INTERFACE — every wave depends on this exact shape. Do not rename
fields or change types without coordinating all dependent agents.

Per Appendix C.2, `backend/schemas/` may import ONLY stdlib + pydantic —
nothing else from `backend/`.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EventBusMessage(BaseModel):
    """The exact JSON schema that must be used for every message published to
    the `qecomp:events` Redis pub/sub channel (plan §C.4).

    Standard `payload` fields by event `type` are documented in the plan's
    §C.4 table (matchStarted, timer_milestone, config_change, etc.) — this
    schema intentionally keeps `payload` as a free-form dict since the set of
    event types is open-ended and owned by later waves.
    """

    model_config = ConfigDict(extra="forbid")

    entity_id: str = Field(
        ..., description="Who fired the event, e.g. 'vex_tm.division_1'."
    )
    entity_tags: list[str] = Field(
        default_factory=list, description="Tags of the firing entity at event time."
    )
    type: str = Field(
        ..., description="What happened, e.g. 'matchStarted', 'timer_milestone'."
    )
    timestamp: float = Field(..., description="Unix epoch float (time.time()).")
    payload: dict[str, Any] = Field(
        default_factory=dict, description="Event-specific data."
    )
