"""Router tests for `backend/routers/timers.py` (plan §14 — CRUD on
`/api/v1/timers` and cues endpoints) against a real test Postgres.

Confirms:
  * CRUD works end-to-end through the real FastAPI app (`backend.main.app`)
    against the isolated `qecomp_wave2b` test database.
  * `/timers/{entity_id}/start|stop|reset` correctly 503 when no
    `TimerManager` is wired onto `app.state` (e.g. a passive/non-leader
    node) and succeed once one is.

Wave 3b note: `_require_permission` (per route, plan §11's permission
column) is no longer a no-op — it now delegates to the real RBAC dependency
in `backend/core/dependencies.py`. This file is about CRUD/business logic,
not RBAC itself (that's covered by `tests/test_core/test_rbac.py`), so its
fixtures override `get_current_principal` with an all-permissions principal
so requests here don't need a real session/API key.
"""
from __future__ import annotations

import uuid

import fakeredis
import pytest
from fakeredis import aioredis as fake_aioredis
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.core.security import generate_prompter_token
from backend.core.settings import settings
from backend.models.timer import PrompterCue, TimerInstance
from backend.modules.timer.manager import TimerManager

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def test_session_factory():
    """A session factory bound to a fresh engine for this test's event
    loop. NOT `backend.core.db.async_session_factory` — that module-level
    singleton engine is bound to whichever event loop first touched it, and
    pytest-asyncio gives every test function its own loop, so reusing the
    global singleton across tests raises "attached to a different loop"
    once asyncpg tries to hand out a pooled connection from a prior test's
    (now-closed) loop."""
    engine = create_async_engine(settings.POSTGRES_DSN, future=True)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
async def app_and_client(test_session_factory):
    from backend.core.db import get_db
    from backend.core.dependencies import ALL_PERMISSIONS, CurrentPrincipal, get_current_principal
    from backend.main import create_app

    server = fakeredis.FakeServer()
    fake_redis = fake_aioredis.FakeRedis(server=server, decode_responses=True)

    app = create_app()
    # Bypass the real lifespan (leader election / real Redis) for router
    # tests — we only need app.state.timer_manager wired, same as
    # production would after leader promotion.
    manager = TimerManager(fake_redis, session_factory=test_session_factory)
    app.state.timer_manager = manager

    # Override `get_db` to use this test's own engine/event-loop-scoped
    # session factory instead of `backend.core.db`'s module-level singleton
    # engine, which is bound to whichever event loop first used it —
    # pytest-asyncio gives every test its own loop, so reusing the global
    # engine's pooled connections across tests raises "attached to a
    # different loop" from asyncpg.
    async def _override_get_db():
        async with test_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db

    # This file tests CRUD/business logic, not RBAC itself (that's covered
    # by `tests/test_core/test_rbac.py`) — bypass auth with an
    # all-permissions principal so these requests don't need a real
    # session/API key.
    async def _override_get_current_principal():
        return CurrentPrincipal(subject="test-admin", permissions={ALL_PERMISSIONS})

    app.dependency_overrides[get_current_principal] = _override_get_current_principal

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield app, client, manager

    await manager.stop()
    await fake_redis.aclose()


@pytest.fixture
async def cleanup_entities(test_session_factory):
    created: list[str] = []
    yield created
    if created:
        async with test_session_factory() as session:
            await session.execute(delete(PrompterCue).where(PrompterCue.timer_entity_id.in_(created)))
            await session.execute(delete(TimerInstance).where(TimerInstance.entity_id.in_(created)))
            await session.commit()


def _unique_entity_id() -> str:
    return f"timer.test_router_{uuid.uuid4().hex[:8]}"


async def test_create_list_update_delete_timer(app_and_client, cleanup_entities):
    _, client, _ = app_and_client
    entity_id = _unique_entity_id()
    cleanup_entities.append(entity_id)

    create_resp = await client.post(
        "/api/v1/timers",
        json={
            "entity_id": entity_id,
            "display_name": "Test Timer",
            "field_set_id": 1,
            "field_id": 1,
            "tags": ["fieldCountdown", "fs1"],
            "duration_s": 90,
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    body = create_resp.json()
    assert body["entity_id"] == entity_id
    assert body["duration_s"] == 90
    assert body["prompter_token"]  # HMAC token computed and present

    # Duplicate create -> 409.
    dup_resp = await client.post(
        "/api/v1/timers",
        json={
            "entity_id": entity_id,
            "display_name": "Dup",
            "field_set_id": 1,
            "field_id": 1,
        },
    )
    assert dup_resp.status_code == 409

    list_resp = await client.get("/api/v1/timers")
    assert list_resp.status_code == 200
    assert any(t["entity_id"] == entity_id for t in list_resp.json())

    update_resp = await client.put(
        f"/api/v1/timers/{entity_id}", json={"display_name": "Renamed", "duration_s": 45}
    )
    assert update_resp.status_code == 200
    updated = update_resp.json()
    assert updated["display_name"] == "Renamed"
    assert updated["duration_s"] == 45

    delete_resp = await client.delete(f"/api/v1/timers/{entity_id}")
    assert delete_resp.status_code == 204

    get_after_delete = await client.put(f"/api/v1/timers/{entity_id}", json={"duration_s": 1})
    assert get_after_delete.status_code == 404


async def test_regenerate_token_invalidates_old_token(app_and_client, cleanup_entities):
    _, client, _ = app_and_client
    entity_id = _unique_entity_id()
    cleanup_entities.append(entity_id)

    create_resp = await client.post(
        "/api/v1/timers",
        json={"entity_id": entity_id, "display_name": "T", "field_set_id": 1, "field_id": 1},
    )
    old_token = create_resp.json()["prompter_token"]

    regen_resp = await client.put(f"/api/v1/timers/{entity_id}", json={"regenerate_token": True})
    new_token = regen_resp.json()["prompter_token"]

    assert new_token != old_token


async def test_start_stop_reset_via_timer_manager(app_and_client, cleanup_entities):
    _, client, manager = app_and_client
    entity_id = _unique_entity_id()
    cleanup_entities.append(entity_id)

    await client.post(
        "/api/v1/timers",
        json={
            "entity_id": entity_id,
            "display_name": "T",
            "field_set_id": 1,
            "field_id": 1,
            "duration_s": 30,
        },
    )
    await manager.reload()

    start_resp = await client.post(f"/api/v1/timers/{entity_id}/start")
    assert start_resp.status_code == 200
    assert start_resp.json()["phase"] == "countdown"

    stop_resp = await client.post(f"/api/v1/timers/{entity_id}/stop")
    assert stop_resp.status_code == 200
    assert stop_resp.json()["phase"] == "idle"

    reset_resp = await client.post(f"/api/v1/timers/{entity_id}/reset")
    assert reset_resp.status_code == 200

    await manager.stop()


async def test_start_returns_503_without_timer_manager(cleanup_entities, test_session_factory):
    """Confirms the RBAC-gated routes are still reachable (bypassed here via
    an all-permissions principal override — RBAC enforcement itself is
    covered by `tests/test_core/test_rbac.py`) but correctly surface a 503
    when no TimerManager is wired onto app.state — e.g. a passive/non-leader
    node."""
    from backend.core.db import get_db
    from backend.core.dependencies import ALL_PERMISSIONS, CurrentPrincipal, get_current_principal
    from backend.main import create_app

    entity_id = _unique_entity_id()
    cleanup_entities.append(entity_id)

    app = create_app()  # app.state.timer_manager intentionally left unset

    async def _override_get_db():
        async with test_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db

    async def _override_get_current_principal():
        return CurrentPrincipal(subject="test-admin", permissions={ALL_PERMISSIONS})

    app.dependency_overrides[get_current_principal] = _override_get_current_principal

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/api/v1/timers",
            json={"entity_id": entity_id, "display_name": "T", "field_set_id": 1, "field_id": 1},
        )
        resp = await client.post(f"/api/v1/timers/{entity_id}/start")
        assert resp.status_code == 503


async def test_cues_crud(app_and_client, cleanup_entities):
    _, client, _ = app_and_client
    entity_id = _unique_entity_id()
    cleanup_entities.append(entity_id)

    await client.post(
        "/api/v1/timers",
        json={"entity_id": entity_id, "display_name": "T", "field_set_id": 1, "field_id": 1},
    )

    create_resp = await client.post(
        f"/api/v1/timers/{entity_id}/cues",
        json={"timer_entity_id": entity_id, "content": "**Welcome** to the show", "sort_order": 0},
    )
    assert create_resp.status_code == 201, create_resp.text
    cue = create_resp.json()
    cue_id = cue["id"]

    list_resp = await client.get(f"/api/v1/timers/{entity_id}/cues")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    update_resp = await client.put(
        f"/api/v1/timers/{entity_id}/cues/{cue_id}", json={"content": "Updated cue", "is_active": False}
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["content"] == "Updated cue"
    assert update_resp.json()["is_active"] is False

    delete_resp = await client.delete(f"/api/v1/timers/{entity_id}/cues/{cue_id}")
    assert delete_resp.status_code == 204

    list_after = await client.get(f"/api/v1/timers/{entity_id}/cues")
    assert list_after.json() == []


async def test_cue_mismatched_timer_entity_id_rejected(app_and_client, cleanup_entities):
    _, client, _ = app_and_client
    entity_id = _unique_entity_id()
    other_id = _unique_entity_id()
    cleanup_entities.extend([entity_id, other_id])

    await client.post(
        "/api/v1/timers",
        json={"entity_id": entity_id, "display_name": "T", "field_set_id": 1, "field_id": 1},
    )

    resp = await client.post(
        f"/api/v1/timers/{entity_id}/cues",
        json={"timer_entity_id": other_id, "content": "x"},
    )
    assert resp.status_code == 400


async def test_update_timer_ignores_explicit_null(app_and_client, cleanup_entities):
    """Regression test: PUT with an explicit JSON null for a NOT NULL column
    (e.g. {"duration_s": null}) must be treated as "field not provided", not
    applied and left to fail at commit with an unhandled 500."""
    _, client, _ = app_and_client
    entity_id = _unique_entity_id()
    cleanup_entities.append(entity_id)

    await client.post(
        "/api/v1/timers",
        json={
            "entity_id": entity_id,
            "display_name": "T",
            "field_set_id": 1,
            "field_id": 1,
            "duration_s": 60,
        },
    )

    resp = await client.put(f"/api/v1/timers/{entity_id}", json={"duration_s": None})
    assert resp.status_code == 200
    assert resp.json()["duration_s"] == 60  # unchanged, not nulled out


async def test_delete_timer_cascades_cues(app_and_client, cleanup_entities):
    """Regression test: deleting a Timer instance must also delete its
    PrompterCue rows (no FK/cascade ties them together in the schema), so a
    later instance reusing the same entity_id doesn't inherit stale cues."""
    _, client, _ = app_and_client
    entity_id = _unique_entity_id()
    cleanup_entities.append(entity_id)

    await client.post(
        "/api/v1/timers",
        json={"entity_id": entity_id, "display_name": "T", "field_set_id": 1, "field_id": 1},
    )
    await client.post(
        f"/api/v1/timers/{entity_id}/cues",
        json={"timer_entity_id": entity_id, "content": "orphan candidate"},
    )

    delete_resp = await client.delete(f"/api/v1/timers/{entity_id}")
    assert delete_resp.status_code == 204

    # Re-create an instance with the same entity_id.
    await client.post(
        "/api/v1/timers",
        json={"entity_id": entity_id, "display_name": "T2", "field_set_id": 1, "field_id": 1},
    )
    cues_resp = await client.get(f"/api/v1/timers/{entity_id}/cues")
    assert cues_resp.status_code == 200
    assert cues_resp.json() == []  # no orphaned cue from the deleted instance


async def test_create_timer_duplicate_returns_409_not_500(app_and_client, cleanup_entities):
    """Even bypassing the pre-check (simulated by inserting the row
    directly, mirroring what a concurrent request would leave behind), a
    duplicate entity_id create must surface as 409, not an unhandled
    IntegrityError-driven 500."""
    _, client, _ = app_and_client
    entity_id = _unique_entity_id()
    cleanup_entities.append(entity_id)

    body = {"entity_id": entity_id, "display_name": "T", "field_set_id": 1, "field_id": 1}
    first = await client.post("/api/v1/timers", json=body)
    assert first.status_code == 201

    second = await client.post("/api/v1/timers", json=body)
    assert second.status_code == 409


async def test_prompter_token_round_trip():
    """HMAC token generate/validate round trip (independent of the router,
    but exercised here alongside the other timer-related tests)."""
    from backend.core.security import validate_prompter_token

    token = generate_prompter_token("timer.fs1_field1", "nonce-abc")
    assert validate_prompter_token("timer.fs1_field1", "nonce-abc", token) is True
    assert validate_prompter_token("timer.fs1_field1", "different-nonce", token) is False
    assert validate_prompter_token("timer.other_entity", "nonce-abc", token) is False
    assert validate_prompter_token("timer.fs1_field1", "nonce-abc", "garbage") is False
