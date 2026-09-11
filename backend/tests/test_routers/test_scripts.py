"""Router tests for `backend/routers/scripts.py` (plan §14) against a real
test Postgres — same pattern as `backend/tests/test_routers/test_automations.py`.
"""
from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.core.settings import settings
from backend.models.automation import Script

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def test_session_factory():
    engine = create_async_engine(settings.POSTGRES_DSN, future=True)
    try:
        async with engine.connect() as conn:
            await conn.exec_driver_sql("SELECT 1")
    except Exception:
        await engine.dispose()
        pytest.skip("Real Postgres not reachable; skipping scripts router tests")
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
async def app_and_client(test_session_factory):
    from backend.core.db import get_db
    from backend.main import create_app

    app = create_app()

    async def _override_get_db():
        async with test_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
async def cleanup(test_session_factory):
    script_ids: list[uuid.UUID] = []
    yield script_ids
    if script_ids:
        async with test_session_factory() as session:
            await session.execute(delete(Script).where(Script.id.in_(script_ids)))
            await session.commit()


async def test_script_crud(app_and_client, cleanup):
    client = app_and_client
    name = f"router_test_script_{uuid.uuid4().hex[:8]}"

    resp = await client.post(
        "/api/v1/scripts",
        json={"name": name, "description": "test", "action_yaml": "- service: a.b\n  target: a.c\n  data: {}\n"},
    )
    assert resp.status_code == 201
    created = resp.json()
    cleanup.append(created["id"])
    assert created["name"] == name

    resp = await client.get("/api/v1/scripts")
    assert resp.status_code == 200
    assert any(s["id"] == created["id"] for s in resp.json())

    resp = await client.put(f"/api/v1/scripts/{created['id']}", json={"description": "updated"})
    assert resp.status_code == 200
    assert resp.json()["description"] == "updated"

    resp = await client.delete(f"/api/v1/scripts/{created['id']}")
    assert resp.status_code == 204
    cleanup.remove(created["id"])

    resp = await client.put(f"/api/v1/scripts/{created['id']}", json={"description": "gone"})
    assert resp.status_code == 404


async def test_create_script_duplicate_name_conflicts(app_and_client, cleanup):
    client = app_and_client
    name = f"dup_test_{uuid.uuid4().hex[:8]}"
    body = {"name": name, "action_yaml": "- service: a.b\n  target: a.c\n  data: {}\n"}

    resp = await client.post("/api/v1/scripts", json=body)
    assert resp.status_code == 201
    cleanup.append(resp.json()["id"])

    resp = await client.post("/api/v1/scripts", json=body)
    assert resp.status_code == 409
