"""Tests for `backend.modules.timer.manager.TimerManager` (plan §14
`test_timer.py`): countdown start/tick/milestone emission timing accuracy,
multi-instance isolation, the match-running state transition at T-0, and
transition to "match complete" on observing a `matchStopped` event, plus
reset/stop correctness.

Uses `fakeredis` (in-memory, no real Redis needed per plan §14) for the
Redis side, and a real test Postgres (the `qecomp_wave2b` database created
for this wave against the shared `compose.yml` Postgres instance) for the
`timer_instances` rows TimerManager loads via `reload()`.
"""
from __future__ import annotations

import asyncio
import json
import time

import fakeredis
import pytest
from fakeredis import aioredis as fake_aioredis
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.core.settings import settings
from backend.models.timer import TimerInstance
from backend.modules.timer.manager import (
    PHASE_COUNTDOWN,
    PHASE_MATCH_COMPLETE,
    PHASE_MATCH_RUNNING,
    TimerManager,
)
from backend.schemas.events import EventBusMessage

pytestmark = pytest.mark.asyncio

# Fast tick interval so tests don't take real wall-clock seconds per tick.
FAST_TICK = 0.05


@pytest.fixture
async def db_session_factory():
    """A dedicated async session factory against the isolated test Postgres
    database used for this wave (`qecomp_wave2b`), independent from the
    shared `qecomp` database other parallel-wave agents may be migrating."""
    engine = create_async_engine(settings.POSTGRES_DSN, future=True)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    try:
        async with engine.connect() as conn:
            await conn.exec_driver_sql("SELECT 1")
    except Exception:
        pytest.skip("Test Postgres not reachable at POSTGRES_DSN; skipping TimerManager tests")
    yield factory
    await engine.dispose()


@pytest.fixture
async def redis_client():
    server = fakeredis.FakeServer()
    client = fake_aioredis.FakeRedis(server=server, decode_responses=True)
    yield client
    await client.aclose()


async def _make_timer(session_factory, entity_id: str, *, field_id: int, duration_s: int, tags=None):
    async with session_factory() as session:
        row = TimerInstance(
            entity_id=entity_id,
            display_name=entity_id,
            field_set_id=1,
            field_id=field_id,
            duration_s=duration_s,
            tags=tags or [],
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row


async def _cleanup_timers(session_factory, entity_ids: list[str]) -> None:
    from sqlalchemy import delete

    async with session_factory() as session:
        await session.execute(delete(TimerInstance).where(TimerInstance.entity_id.in_(entity_ids)))
        await session.commit()


async def _collect_events(redis_client, channel: str, predicate, timeout: float = 5.0):
    """Collects pub/sub messages on `channel` until `predicate(event_dict)`
    returns True, or `timeout` elapses. Returns the list of all messages
    seen (in order)."""
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(channel)
    seen = []
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.2)
            if msg is None:
                continue
            data = json.loads(msg["data"])
            seen.append(data)
            if predicate(data):
                return seen
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()
    return seen


async def test_countdown_start_and_milestone_ticks(db_session_factory, redis_client):
    entity_id = "timer.test_countdown_ticks"
    await _make_timer(db_session_factory, entity_id, field_id=1, duration_s=3)
    manager = TimerManager(redis_client, session_factory=db_session_factory, tick_interval=FAST_TICK)
    try:
        await manager.reload()

        events_task = asyncio.create_task(
            _collect_events(
                redis_client,
                "qecomp:events",
                lambda e: e["type"] == "timer_finished",
                timeout=5.0,
            )
        )
        await asyncio.sleep(0.05)  # let the subscriber attach before publishing
        await manager.start_countdown(entity_id)

        events = await events_task

        types = [e["type"] for e in events]
        assert types[0] == "timer_started"
        assert "timer_milestone" in types
        assert types[-1] == "timer_finished"

        started = events[0]
        assert started["entity_id"] == entity_id
        assert started["payload"]["duration_s"] == 3
        assert started["payload"]["field_id"] == 1

        milestones = [e for e in events if e["type"] == "timer_milestone"]
        remainings = [m["payload"]["remaining"] for m in milestones]
        # Remaining should be non-increasing across successive milestone ticks.
        assert remainings == sorted(remainings, reverse=True)
        assert all(0 <= r <= 3 for r in remainings)

        # EventBusMessage-shaped: validate against the frozen schema.
        for e in events:
            EventBusMessage.model_validate(e)
    finally:
        await manager.stop()
        await _cleanup_timers(db_session_factory, [entity_id])


async def test_multi_instance_isolation(db_session_factory, redis_client):
    """Two timers with different durations must tick independently without
    interfering with each other's state."""
    entity_a = "timer.test_isolation_a"
    entity_b = "timer.test_isolation_b"
    await _make_timer(db_session_factory, entity_a, field_id=1, duration_s=10)
    await _make_timer(db_session_factory, entity_b, field_id=2, duration_s=2)
    manager = TimerManager(redis_client, session_factory=db_session_factory, tick_interval=FAST_TICK)
    try:
        await manager.reload()
        await manager.start_countdown(entity_a)
        await manager.start_countdown(entity_b)

        # Let B run to completion (short duration) while A is still counting down.
        await asyncio.sleep(3)

        state_a = manager.get_state(entity_a)
        state_b = manager.get_state(entity_b)

        assert state_a["phase"] == PHASE_COUNTDOWN
        assert state_a["duration_s"] == 10
        # B should have finished its countdown and moved to match_running.
        assert state_b["phase"] == PHASE_MATCH_RUNNING
        assert state_b["duration_s"] == 2

        # Confirm they are tracked as fully separate Redis hashes.
        raw_a = await redis_client.hgetall("qecomp:timer:timer.test_isolation_a:state")
        raw_b = await redis_client.hgetall("qecomp:timer:timer.test_isolation_b:state")
        assert raw_a["duration_s"] == "10"
        assert raw_b["duration_s"] == "2"
    finally:
        await manager.stop()
        await _cleanup_timers(db_session_factory, [entity_a, entity_b])


async def test_match_running_transition_at_zero(db_session_factory, redis_client):
    entity_id = "timer.test_match_running"
    await _make_timer(db_session_factory, entity_id, field_id=5, duration_s=1)
    manager = TimerManager(redis_client, session_factory=db_session_factory, tick_interval=FAST_TICK)
    try:
        await manager.reload()
        await manager.start_countdown(entity_id)

        # Wait past T-0.
        for _ in range(100):
            state = manager.get_state(entity_id)
            if state["phase"] == PHASE_MATCH_RUNNING:
                break
            await asyncio.sleep(0.05)
        else:
            pytest.fail("Timer never transitioned to match_running")

        state = manager.get_state(entity_id)
        assert state["phase"] == PHASE_MATCH_RUNNING
        assert state["running"] is True

        # Elapsed should now be counting up from ~0, not still tied to the
        # countdown's remaining time.
        await asyncio.sleep(0.3)
        state2 = manager.get_state(entity_id)
        assert state2["elapsed"] >= state["elapsed"]
    finally:
        await manager.stop()
        await _cleanup_timers(db_session_factory, [entity_id])


async def test_match_complete_on_match_stopped_event(db_session_factory, redis_client):
    entity_id = "timer.test_match_complete"
    await _make_timer(db_session_factory, entity_id, field_id=7, duration_s=1)
    manager = TimerManager(redis_client, session_factory=db_session_factory, tick_interval=FAST_TICK)
    try:
        await manager.start()  # exercises start()'s pub/sub listeners too
        await manager.start_countdown(entity_id)

        for _ in range(100):
            if manager.get_state(entity_id)["phase"] == PHASE_MATCH_RUNNING:
                break
            await asyncio.sleep(0.05)
        else:
            pytest.fail("Timer never reached match_running")

        # Simulate the bound TM field emitting matchStopped.
        stopped_event = EventBusMessage(
            entity_id="vex_tm.division_1",
            entity_tags=[],
            type="matchStopped",
            timestamp=time.time(),
            payload={"fieldID": 7, "matchNum": 12, "round": "QUAL"},
        )
        await redis_client.publish("qecomp:events", stopped_event.model_dump_json())

        for _ in range(100):
            if manager.get_state(entity_id)["phase"] == PHASE_MATCH_COMPLETE:
                break
            await asyncio.sleep(0.05)
        else:
            pytest.fail("Timer never transitioned to match_complete after matchStopped")

        state = manager.get_state(entity_id)
        assert state["phase"] == PHASE_MATCH_COMPLETE
        assert state["running"] is False
    finally:
        await manager.stop()
        await _cleanup_timers(db_session_factory, [entity_id])


async def test_stop_timer_manual(db_session_factory, redis_client):
    entity_id = "timer.test_manual_stop"
    await _make_timer(db_session_factory, entity_id, field_id=9, duration_s=10)
    manager = TimerManager(redis_client, session_factory=db_session_factory, tick_interval=FAST_TICK)
    try:
        await manager.reload()

        events_task = asyncio.create_task(
            _collect_events(
                redis_client,
                "qecomp:events",
                lambda e: e["type"] == "timer_stopped",
                timeout=5.0,
            )
        )
        await asyncio.sleep(0.05)
        await manager.start_countdown(entity_id)
        await asyncio.sleep(0.3)
        await manager.stop_timer(entity_id)

        events = await events_task
        stopped = [e for e in events if e["type"] == "timer_stopped"][0]
        assert stopped["payload"]["field_id"] == 9
        assert stopped["payload"]["elapsed"] >= 0

        state = manager.get_state(entity_id)
        assert state["phase"] == "idle"
        assert state["running"] is False
    finally:
        await manager.stop()
        await _cleanup_timers(db_session_factory, [entity_id])


async def test_reset_timer(db_session_factory, redis_client):
    entity_id = "timer.test_reset"
    await _make_timer(db_session_factory, entity_id, field_id=11, duration_s=1)
    manager = TimerManager(redis_client, session_factory=db_session_factory, tick_interval=FAST_TICK)
    try:
        await manager.reload()
        await manager.start_countdown(entity_id)

        for _ in range(100):
            if manager.get_state(entity_id)["phase"] == PHASE_MATCH_RUNNING:
                break
            await asyncio.sleep(0.05)

        await manager.reset_timer(entity_id)
        state = manager.get_state(entity_id)
        assert state["phase"] == "idle"
        assert state["running"] is False
        assert state["elapsed"] == 0
    finally:
        await manager.stop()
        await _cleanup_timers(db_session_factory, [entity_id])


async def test_reload_removes_deleted_instance(db_session_factory, redis_client):
    entity_id = "timer.test_reload_removed"
    await _make_timer(db_session_factory, entity_id, field_id=13, duration_s=5)
    manager = TimerManager(redis_client, session_factory=db_session_factory, tick_interval=FAST_TICK)
    try:
        await manager.reload()
        await manager.start_countdown(entity_id)
        assert entity_id in manager._configs

        await _cleanup_timers(db_session_factory, [entity_id])
        await manager.reload()

        assert entity_id not in manager._configs
        with pytest.raises(ValueError):
            await manager.start_countdown(entity_id)
    finally:
        await manager.stop()


async def test_get_state_unknown_entity_returns_empty_dict(db_session_factory, redis_client):
    manager = TimerManager(redis_client, session_factory=db_session_factory, tick_interval=FAST_TICK)
    assert manager.get_state("timer.does_not_exist") == {}


async def test_reset_then_stop_does_not_report_stale_elapsed(db_session_factory, redis_client):
    """Regression test: reset_timer() must clear `frozen_elapsed` in Redis,
    not just in the in-memory state cache, so a later stop_timer() call on
    the same (now-idle) instance doesn't report a stale non-zero elapsed
    value left over from before the reset."""
    entity_id = "timer.test_reset_then_stop"
    await _make_timer(db_session_factory, entity_id, field_id=17, duration_s=1)
    manager = TimerManager(redis_client, session_factory=db_session_factory, tick_interval=FAST_TICK)
    try:
        await manager.reload()
        await manager.start_countdown(entity_id)
        await asyncio.sleep(0.3)
        await manager.stop_timer(entity_id)  # writes a non-zero frozen_elapsed

        await manager.start_countdown(entity_id)
        await asyncio.sleep(0.05)
        await manager.reset_timer(entity_id)  # must clear frozen_elapsed too

        raw = await redis_client.hgetall(f"qecomp:timer:{entity_id}:state")
        assert raw.get("frozen_elapsed") == "0"

        await manager.stop_timer(entity_id)
        state = manager.get_state(entity_id)
        assert state["elapsed"] == 0
    finally:
        await manager.stop()
        await _cleanup_timers(db_session_factory, [entity_id])


async def test_start_countdown_rejects_disabled_instance(db_session_factory, redis_client):
    entity_id = "timer.test_disabled"
    async with db_session_factory() as session:
        row = TimerInstance(
            entity_id=entity_id,
            display_name=entity_id,
            field_set_id=1,
            field_id=1,
            duration_s=30,
            enabled=False,
        )
        session.add(row)
        await session.commit()

    manager = TimerManager(redis_client, session_factory=db_session_factory, tick_interval=FAST_TICK)
    try:
        await manager.reload()
        with pytest.raises(ValueError, match="disabled"):
            await manager.start_countdown(entity_id)
    finally:
        await manager.stop()
        await _cleanup_timers(db_session_factory, [entity_id])
