"""Tests for the frozen EventBusMessage schema (plan §C.4)."""
from __future__ import annotations

import time

import pytest
from pydantic import ValidationError

from backend.schemas.events import EventBusMessage


def test_event_bus_message_round_trip():
    msg = EventBusMessage(
        entity_id="vex_tm.division_1",
        entity_tags=["fs1"],
        type="matchStarted",
        timestamp=time.time(),
        payload={"fieldID": 1, "matchNum": 5, "round": "QUAL"},
    )
    data = msg.model_dump()
    assert data["entity_id"] == "vex_tm.division_1"
    restored = EventBusMessage.model_validate(data)
    assert restored == msg


def test_event_bus_message_requires_core_fields():
    with pytest.raises(ValidationError):
        EventBusMessage(entity_id="x")  # missing type/timestamp


def test_event_bus_message_defaults():
    msg = EventBusMessage(entity_id="timer.fs1_field1", type="timer_started", timestamp=1.0)
    assert msg.entity_tags == []
    assert msg.payload == {}
