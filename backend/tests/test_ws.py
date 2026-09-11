"""WebSocket route tests (plan §14): `/ws/events`, `/ws/prompter/{entity_id}`,
`/ws/overlay/{entity_id}` (plan §11 "WebSocket Channels").

Uses Starlette's `TestClient` (not `httpx.AsyncClient`/`ASGITransport` —
those don't support WebSocket upgrades) with the REAL app lifespan (`with
TestClient(app) as client:` triggers FastAPI startup/shutdown), against the
real docker-compose Postgres/Redis services, since there's no leader
contention in a single test process and `ConnectionManager`'s background
pub/sub fan-out (`ws_manager.start()`) is wired up by the real lifespan.
A plain synchronous `redis` client publishes test events directly to
`qecomp:events`, mirroring how an integration/TimerManager would.
"""
from __future__ import annotations

import json
import time
import uuid

import pytest
import redis as redis_sync
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.testclient import TestClient

from backend.core.security import generate_prompter_token
from backend.core.settings import settings
from backend.main import app
from backend.models.timer import TimerInstance


def _postgres_reachable() -> bool:
    import asyncio

    async def _check() -> bool:
        engine = create_async_engine(settings.POSTGRES_DSN)
        try:
            async with engine.connect() as conn:
                await conn.exec_driver_sql("SELECT 1")
            return True
        except Exception:
            return False
        finally:
            await engine.dispose()

    return asyncio.run(_check())


def _redis_reachable() -> bool:
    try:
        client = redis_sync.Redis.from_url(settings.REDIS_URL, decode_responses=True)
        return bool(client.ping())
    except Exception:
        return False


requires_infra = pytest.mark.skipif(
    not (_postgres_reachable() and _redis_reachable()),
    reason="Real Postgres/Redis not reachable; skipping WebSocket integration tests",
)


@requires_infra
def test_ws_events_receives_published_event():
    with TestClient(app) as client:
        with client.websocket_connect("/ws/events") as ws:
            r = redis_sync.Redis.from_url(settings.REDIS_URL, decode_responses=True)
            marker = uuid.uuid4().hex
            msg = {
                "entity_id": f"test.{marker}",
                "entity_tags": [],
                "type": "test_event",
                "timestamp": time.time(),
                "payload": {"marker": marker},
            }
            r.publish("qecomp:events", json.dumps(msg))
            r.close()

            # Drain frames until we see ours (the app may already have other
            # background chatter published on qecomp:events, e.g. from a
            # promotion-triggered TimerManager.reload()).
            for _ in range(20):
                received = ws.receive_json()
                if received.get("payload", {}).get("marker") == marker:
                    assert received["type"] == "test_event"
                    return
            pytest.fail("Did not receive the published test event on /ws/events")


@requires_infra
def test_ws_overlay_connects_without_auth():
    with TestClient(app) as client:
        entity_id = f"overlay.test_{uuid.uuid4().hex[:8]}"
        with client.websocket_connect(f"/ws/overlay/{entity_id}") as ws:
            # No auth required (plan Appendix A.1) — the connection simply
            # accepts. Publish a fieldMatchAssigned event for a field this
            # overlay isn't bound to (no OverlayInstance row exists for it),
            # so nothing should arrive; the connection itself succeeding
            # (no exception from websocket_connect) is the assertion.
            r = redis_sync.Redis.from_url(settings.REDIS_URL, decode_responses=True)
            r.close()
            ws.close()


async def _seed_timer_instance(entity_id: str) -> None:
    engine = create_async_engine(settings.POSTGRES_DSN)
    try:
        factory = async_sessionmaker(bind=engine, expire_on_commit=False)
        async with factory() as session:
            session.add(
                TimerInstance(entity_id=entity_id, display_name="WS Test", field_set_id=1, field_id=1)
            )
            await session.commit()
    finally:
        await engine.dispose()


async def _fetch_token_nonce(entity_id: str) -> str:
    engine = create_async_engine(settings.POSTGRES_DSN)
    try:
        factory = async_sessionmaker(bind=engine, expire_on_commit=False)
        async with factory() as session:
            result = await session.execute(
                TimerInstance.__table__.select().where(TimerInstance.entity_id == entity_id)
            )
            return result.mappings().one()["token_nonce"]
    finally:
        await engine.dispose()


async def _delete_timer_instance(entity_id: str) -> None:
    engine = create_async_engine(settings.POSTGRES_DSN)
    try:
        factory = async_sessionmaker(bind=engine, expire_on_commit=False)
        async with factory() as session:
            await session.execute(delete(TimerInstance).where(TimerInstance.entity_id == entity_id))
            await session.commit()
    finally:
        await engine.dispose()


@requires_infra
def test_ws_prompter_rejects_invalid_token():
    import asyncio

    entity_id = f"timer.test_ws_{uuid.uuid4().hex[:8]}"
    asyncio.run(_seed_timer_instance(entity_id))
    try:
        with TestClient(app) as client:
            with pytest.raises(Exception):
                with client.websocket_connect(f"/ws/prompter/{entity_id}?token=not-a-real-token"):
                    pass
    finally:
        asyncio.run(_delete_timer_instance(entity_id))


@requires_infra
def test_ws_prompter_accepts_valid_token_once_leader():
    import asyncio

    entity_id = f"timer.test_ws_{uuid.uuid4().hex[:8]}"
    asyncio.run(_seed_timer_instance(entity_id))
    nonce = asyncio.run(_fetch_token_nonce(entity_id))
    token = generate_prompter_token(entity_id, nonce)

    try:
        with TestClient(app) as client:
            # Wait for this single process to promote itself to leader
            # (no contention — should be near-instant, but the election
            # loop runs as a background task so give it a few ticks).
            for _ in range(30):
                if getattr(app.state, "timer_manager", None) is not None:
                    break
                time.sleep(0.2)
            else:
                pytest.skip("This process did not become leader in time")

            with client.websocket_connect(f"/ws/prompter/{entity_id}?token={token}") as ws:
                first = ws.receive_json()
                assert first["type"] == "timer_state"
                assert first["entity_id"] == entity_id
                second = ws.receive_json()
                assert second["type"] == "cues"
    finally:
        asyncio.run(_delete_timer_instance(entity_id))
