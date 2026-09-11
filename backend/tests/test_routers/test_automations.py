"""Router tests for `backend/routers/automations.py` (plan §14) against a
real test Postgres, following the exact fixture pattern established in
`backend/tests/test_timers_router.py`: bypass the real lifespan, wire
`app.state.automation_engine` manually (as production would after leader
promotion), override `get_db` to a test-scoped session factory, and use
`httpx.AsyncClient` + `ASGITransport` against the real FastAPI app.

Confirms: folder + automation CRUD, the "Validate" endpoint (Appendix A.7),
`/trigger` correctly 503s with no `AutomationEngine` wired and succeeds once
one is (calling into a mocked integration via a monkeypatched loader), and
the execution-history `/runs` endpoint.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import fakeredis
import pytest
from fakeredis import aioredis as fake_aioredis
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import backend.loader as loader_module
from backend.core.settings import settings
from backend.models.automation import Automation, AutomationFolder, AutomationRun
from backend.modules.automation.engine import AutomationEngine

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
async def test_session_factory():
    engine = create_async_engine(settings.POSTGRES_DSN, future=True)
    try:
        async with engine.connect() as conn:
            await conn.exec_driver_sql("SELECT 1")
    except Exception:
        await engine.dispose()
        pytest.skip("Real Postgres not reachable; skipping automations router tests")
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
    engine = AutomationEngine(redis=fake_redis, session_factory=test_session_factory)
    app.state.automation_engine = engine

    async def _override_get_db():
        async with test_session_factory() as session:
            yield session

    # This file tests CRUD/business logic, not RBAC itself (that's covered
    # by `tests/test_core/test_rbac.py`) — bypass auth with an
    # all-permissions principal, matching the pattern in
    # `tests/test_routers/test_teams.py`.
    async def _override_get_current_principal():
        return CurrentPrincipal(subject="test-admin", permissions={ALL_PERMISSIONS})

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_principal] = _override_get_current_principal

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield app, client, engine

    await fake_redis.aclose()


@pytest.fixture
def patch_loader(monkeypatch):
    registry: dict[str, FakeIntegration] = {}
    monkeypatch.setattr(loader_module, "get_instance", lambda eid: registry.get(eid))
    monkeypatch.setattr(
        loader_module, "get_instances_by_tag", lambda tag: [i for i in registry.values() if tag in i.tags]
    )
    monkeypatch.setattr(loader_module, "get_all_instances", lambda: list(registry.values()))
    return registry


@pytest.fixture
async def cleanup(test_session_factory):
    automation_ids: list[uuid.UUID] = []
    folder_ids: list[uuid.UUID] = []
    yield automation_ids, folder_ids
    async with test_session_factory() as session:
        if automation_ids:
            await session.execute(delete(AutomationRun).where(AutomationRun.automation_id.in_(automation_ids)))
            await session.execute(delete(Automation).where(Automation.id.in_(automation_ids)))
        if folder_ids:
            await session.execute(delete(AutomationFolder).where(AutomationFolder.id.in_(folder_ids)))
        await session.commit()


async def test_folder_crud(app_and_client, cleanup):
    _, client, _ = app_and_client
    automation_ids, folder_ids = cleanup

    resp = await client.post("/api/v1/automations/folders", json={"name": "Match Day"})
    assert resp.status_code == 201
    folder = resp.json()
    folder_ids.append(folder["id"])

    resp = await client.get("/api/v1/automations/folders")
    assert resp.status_code == 200
    assert any(f["id"] == folder["id"] for f in resp.json())


async def test_automation_crud(app_and_client, cleanup):
    _, client, _ = app_and_client
    automation_ids, _ = cleanup

    body = {
        "alias": "Router CRUD test",
        "enabled": True,
        "trigger_yaml": "- platform: state\n  entity_id: x\n  event_type: y\n",
        "action_yaml": "- service: atem.switch_input\n  target: atem.a\n  data: {}\n",
    }
    resp = await client.post("/api/v1/automations", json=body)
    assert resp.status_code == 201
    created = resp.json()
    automation_ids.append(created["id"])
    assert created["alias"] == "Router CRUD test"

    resp = await client.get("/api/v1/automations")
    assert resp.status_code == 200
    assert any(a["id"] == created["id"] for a in resp.json())

    resp = await client.put(f"/api/v1/automations/{created['id']}", json={"alias": "Renamed"})
    assert resp.status_code == 200
    assert resp.json()["alias"] == "Renamed"

    resp = await client.delete(f"/api/v1/automations/{created['id']}")
    assert resp.status_code == 204
    automation_ids.remove(created["id"])

    resp = await client.get(f"/api/v1/automations/{created['id']}/runs")
    assert resp.status_code == 404


async def test_validate_endpoint_valid_and_invalid(app_and_client):
    _, client, _ = app_and_client

    resp = await client.post(
        "/api/v1/automations/validate",
        json={
            "trigger_yaml": "- platform: state\n  entity_id: x\n  event_type: y\n",
            "action_yaml": "- service: a.b\n  target: a.c\n  data: {}\n",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["valid"] is True

    resp = await client.post(
        "/api/v1/automations/validate",
        json={"trigger_yaml": "- platform: state\n", "action_yaml": "- service: a.b\n  data:\n    x: \"{{ (( }}\"\n"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is False
    assert body["errors"]


async def test_trigger_returns_503_without_automation_engine(test_session_factory):
    from backend.core.db import get_db
    from backend.core.dependencies import ALL_PERMISSIONS, CurrentPrincipal, get_current_principal
    from backend.main import create_app

    app = create_app()  # app.state.automation_engine intentionally left unset

    async def _override_get_db():
        async with test_session_factory() as session:
            yield session

    async def _override_get_current_principal():
        return CurrentPrincipal(subject="test-admin", permissions={ALL_PERMISSIONS})

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_principal] = _override_get_current_principal

    async with test_session_factory() as session:
        row = Automation(
            alias="No engine test",
            trigger_yaml="- platform: state\n  entity_id: x\n  event_type: y\n",
            action_yaml="- service: a.b\n  target: a.c\n  data: {}\n",
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        automation_id = row.id

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(f"/api/v1/automations/{automation_id}/trigger")
        assert resp.status_code == 503
    finally:
        async with test_session_factory() as session:
            await session.execute(delete(Automation).where(Automation.id == automation_id))
            await session.commit()


async def test_trigger_via_router_calls_service_and_logs_run(app_and_client, cleanup, patch_loader):
    _, client, _ = app_and_client
    automation_ids, _ = cleanup

    fake = FakeIntegration(entity_id="atem.router_test")
    patch_loader["atem.router_test"] = fake

    body = {
        "alias": "Router trigger test",
        "trigger_yaml": "- platform: state\n  entity_id: never\n  event_type: never\n",
        "action_yaml": "- service: atem.switch_input\n  target: atem.router_test\n  data:\n    input_index: 1\n",
    }
    resp = await client.post("/api/v1/automations", json=body)
    created = resp.json()
    automation_ids.append(created["id"])

    resp = await client.post(f"/api/v1/automations/{created['id']}/trigger")
    assert resp.status_code == 200
    result = resp.json()
    assert result["status"] == "success"
    assert fake.calls == [("switch_input", {"input_index": 1})]

    resp = await client.get(f"/api/v1/automations/{created['id']}/runs")
    assert resp.status_code == 200
    runs = resp.json()
    assert len(runs) == 1
    assert runs[0]["status"] == "success"


async def test_trigger_unknown_automation_returns_404(app_and_client):
    _, client, _ = app_and_client
    resp = await client.post(f"/api/v1/automations/{uuid.uuid4()}/trigger")
    assert resp.status_code == 404
