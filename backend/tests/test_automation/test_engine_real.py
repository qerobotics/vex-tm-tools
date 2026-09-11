"""Integration-style tests for `AutomationEngine` against REAL Postgres +
Redis (the compose.yml services) — mirrors the pattern in
`backend/tests/test_loader_real.py` / `backend/tests/test_timer.py`: skip
gracefully if the real infra isn't reachable.

Covers: `reload()` loading a real `automations`/`scripts` row from Postgres,
`start()` picking up a matching `EventBusMessage` published to the real
`qecomp:events` Redis pub/sub channel and calling a mocked integration's
`call_service` (registered with the loader via monkeypatching its frozen
public API — the Loader itself is being exercised separately in
`test_loader_real.py`), execution history logging to `automation_runs`,
`trigger()`'s manual Test-Run path, and `reload()` hot-reload via
`qecomp:config_change`.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import pytest
import redis.asyncio as redis
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import backend.loader as loader_module
from backend.core.settings import settings
from backend.models.automation import Automation, AutomationRun, Script
from backend.modules.automation.engine import AutomationEngine
from backend.schemas.events import EventBusMessage

pytestmark = pytest.mark.asyncio


@dataclass
class FakeIntegration:
    entity_id: str
    tags: list[str] = field(default_factory=list)
    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    async def call_service(self, service: str, data: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((service, data))
        return {"ok": True}

    async def get_state(self) -> dict[str, Any]:
        return {}


@pytest.fixture
async def real_redis():
    client = redis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        await client.ping()
    except Exception:
        pytest.skip("Real Redis not reachable at REDIS_URL; skipping AutomationEngine real-infra tests")
    yield client
    await client.aclose()


@pytest.fixture
async def real_session_factory():
    engine = create_async_engine(settings.POSTGRES_DSN, pool_pre_ping=True)
    try:
        async with engine.connect() as conn:
            await conn.exec_driver_sql("SELECT 1")
    except Exception:
        await engine.dispose()
        pytest.skip("Real Postgres not reachable at POSTGRES_DSN; skipping AutomationEngine real-infra tests")
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
def patch_loader_with_fake(monkeypatch):
    registry: dict[str, FakeIntegration] = {}
    monkeypatch.setattr(loader_module, "get_instance", lambda eid: registry.get(eid))
    monkeypatch.setattr(
        loader_module, "get_instances_by_tag", lambda tag: [i for i in registry.values() if tag in i.tags]
    )
    monkeypatch.setattr(loader_module, "get_all_instances", lambda: list(registry.values()))
    return registry


async def _make_automation(
    session_factory,
    *,
    alias: str,
    trigger_yaml: str,
    action_yaml: str,
    condition_yaml: str | None = None,
    enabled: bool = True,
) -> uuid.UUID:
    async with session_factory() as session:
        row = Automation(
            alias=alias,
            enabled=enabled,
            trigger_yaml=trigger_yaml,
            condition_yaml=condition_yaml,
            action_yaml=action_yaml,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row.id


async def _cleanup_automation(session_factory, automation_id: uuid.UUID) -> None:
    async with session_factory() as session:
        await session.execute(delete(AutomationRun).where(AutomationRun.automation_id == automation_id))
        await session.execute(delete(Automation).where(Automation.id == automation_id))
        await session.commit()


async def test_start_picks_up_matching_event_and_calls_service_and_logs_history(
    real_redis, real_session_factory, patch_loader_with_fake
):
    fake = FakeIntegration(entity_id="atem.main_switcher")
    patch_loader_with_fake["atem.main_switcher"] = fake

    automation_id = await _make_automation(
        real_session_factory,
        alias="Match Start — real infra test",
        trigger_yaml=(
            "- platform: state\n"
            "  entity_id: vex_tm.real_engine_test\n"
            "  event_type: matchStarted\n"
        ),
        condition_yaml="- \"{{ trigger.payload.fieldID in [1, 2, 3] }}\"\n",
        action_yaml=(
            "- service: atem.switch_input\n"
            "  target: atem.main_switcher\n"
            "  data:\n"
            "    input_index: \"{{ trigger.payload.fieldID }}\"\n"
        ),
    )

    engine = AutomationEngine(redis=real_redis, session_factory=real_session_factory)
    try:
        await engine.start()
        await asyncio.sleep(0.2)  # let the pubsub subscription attach

        msg = EventBusMessage(
            entity_id="vex_tm.real_engine_test",
            entity_tags=["fs1"],
            type="matchStarted",
            timestamp=time.time(),
            payload={"fieldID": 2, "matchNum": 5, "round": "QUAL", "redTeams": [], "blueTeams": [], "divisionId": 1},
        )
        await real_redis.publish("qecomp:events", msg.model_dump_json())

        for _ in range(100):
            if fake.calls:
                break
            await asyncio.sleep(0.05)
        else:
            pytest.fail("AutomationEngine did not call the target service in time")

        assert fake.calls == [("switch_input", {"input_index": 2})]

        # Execution history (Appendix A.7) was logged.
        for _ in range(100):
            async with real_session_factory() as session:
                result = await session.execute(
                    select(AutomationRun).where(AutomationRun.automation_id == automation_id)
                )
                runs = list(result.scalars().all())
            if runs:
                break
            await asyncio.sleep(0.05)
        else:
            pytest.fail("No AutomationRun history row was logged in time")

        assert runs[0].status == "success"
        assert runs[0].trigger_event["type"] == "matchStarted"
    finally:
        await engine.stop()
        await _cleanup_automation(real_session_factory, automation_id)


async def test_condition_failure_prevents_action_and_no_run_logged(
    real_redis, real_session_factory, patch_loader_with_fake
):
    fake = FakeIntegration(entity_id="atem.main_switcher")
    patch_loader_with_fake["atem.main_switcher"] = fake

    automation_id = await _make_automation(
        real_session_factory,
        alias="Condition gate — real infra test",
        trigger_yaml=(
            "- platform: state\n  entity_id: vex_tm.real_engine_condition_test\n  event_type: matchStarted\n"
        ),
        condition_yaml="- \"{{ trigger.payload.fieldID in [1, 2, 3] }}\"\n",
        action_yaml=(
            "- service: atem.switch_input\n  target: atem.main_switcher\n  data: {}\n"
        ),
    )
    engine = AutomationEngine(redis=real_redis, session_factory=real_session_factory)
    try:
        await engine.start()
        await asyncio.sleep(0.2)

        msg = EventBusMessage(
            entity_id="vex_tm.real_engine_condition_test",
            entity_tags=[],
            type="matchStarted",
            timestamp=time.time(),
            payload={"fieldID": 99},  # not in [1, 2, 3] -> condition fails
        )
        await real_redis.publish("qecomp:events", msg.model_dump_json())
        await asyncio.sleep(0.5)

        assert fake.calls == []
    finally:
        await engine.stop()
        await _cleanup_automation(real_session_factory, automation_id)


async def test_trigger_manual_test_run_ignores_conditions(
    real_redis, real_session_factory, patch_loader_with_fake
):
    """The "Test Run" button (plan §12): fires regardless of trigger
    conditions — here the automation's own condition would normally block
    this (fieldID 99 not in [1,2,3]), but `trigger()` bypasses trigger
    matching AND condition evaluation entirely, running the action chain
    directly."""
    fake = FakeIntegration(entity_id="zeros.lighting_board")
    patch_loader_with_fake["zeros.lighting_board"] = fake

    automation_id = await _make_automation(
        real_session_factory,
        alias="Manual trigger test",
        trigger_yaml="- platform: state\n  entity_id: does.not_matter\n  event_type: never_happens\n",
        action_yaml="- service: zeros.set_preset\n  target: zeros.lighting_board\n  data:\n    preset_name: test\n",
    )
    engine = AutomationEngine(redis=real_redis, session_factory=real_session_factory)
    try:
        result = await engine.trigger(automation_id, {})
        assert result["status"] == "success"
        assert fake.calls == [("set_preset", {"preset_name": "test"})]

        with pytest.raises(ValueError):
            await engine.trigger(uuid.uuid4(), {})
    finally:
        await _cleanup_automation(real_session_factory, automation_id)


async def test_script_action_resolved_from_real_scripts_table(
    real_redis, real_session_factory, patch_loader_with_fake
):
    fake = FakeIntegration(entity_id="spotify.fs1_field1")
    patch_loader_with_fake["spotify.fs1_field1"] = fake

    async with real_session_factory() as session:
        script_row = Script(
            name=f"real_engine_test_script_{uuid.uuid4().hex[:8]}",
            action_yaml=(
                "- service: spotify.play_playlist_track\n"
                "  target: spotify.fs1_field1\n"
                "  data:\n    tag: \"{{ vars.field_tag }}\"\n"
            ),
        )
        session.add(script_row)
        await session.commit()
        await session.refresh(script_row)

    automation_id = await _make_automation(
        real_session_factory,
        alias="Script-calling automation",
        trigger_yaml="- platform: state\n  entity_id: irrelevant\n  event_type: irrelevant\n",
        action_yaml=f"- script: {script_row.name}\n  data:\n    field_tag: fs1\n",
    )

    engine = AutomationEngine(redis=real_redis, session_factory=real_session_factory)
    try:
        result = await engine.trigger(automation_id, {})
        assert result["status"] == "success"
        assert fake.calls == [("play_playlist_track", {"tag": "fs1"})]
    finally:
        await _cleanup_automation(real_session_factory, automation_id)
        async with real_session_factory() as session:
            await session.execute(delete(Script).where(Script.id == script_row.id))
            await session.commit()


async def test_reload_picks_up_newly_added_automation(real_redis, real_session_factory, patch_loader_with_fake):
    fake = FakeIntegration(entity_id="atem.main_switcher")
    patch_loader_with_fake["atem.main_switcher"] = fake

    engine = AutomationEngine(redis=real_redis, session_factory=real_session_factory)
    await engine.reload()
    assert len([a for a in engine._automations if a.alias == "reload-test-automation"]) == 0

    automation_id = await _make_automation(
        real_session_factory,
        alias="reload-test-automation",
        trigger_yaml="- platform: state\n  entity_id: x\n  event_type: y\n",
        action_yaml="- service: atem.switch_input\n  target: atem.main_switcher\n  data: {}\n",
    )
    try:
        await engine.reload()
        assert any(a.id == automation_id for a in engine._automations)
    finally:
        await _cleanup_automation(real_session_factory, automation_id)
