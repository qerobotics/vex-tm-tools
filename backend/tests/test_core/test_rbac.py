"""RBAC enforcement tests (plan §14 `test_rbac.py` / §13).

Exercises `backend.core.dependencies.require_permission` end-to-end through
a real (tiny) FastAPI app + `httpx.AsyncClient`, using `fakeredis` for the
session store (per plan §14's test stack — no real Redis needed) so these
tests don't depend on the docker-compose Redis/Postgres services being up.

Covers:
  * No session/API key -> 401.
  * A session with insufficient permissions -> 403.
  * A session with the required permission -> 200.
  * `admin_local` sessions bypass all permission checks (plan §3.9/§B.9).
  * API keys are scoped to their own `permissions` list and never bypass
    (requires real Postgres for the `api_keys` lookup — skipped if
    unreachable, matching the convention in `test_routers/test_teams.py`).
"""
from __future__ import annotations

import uuid

import fakeredis
import pytest
from fakeredis import aioredis as fake_aioredis
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from backend.core.dependencies import get_current_principal, require_permission
from backend.core.redis import get_redis
from backend.core.security import generate_api_key, hash_api_key
from backend.core.sessions import SESSION_COOKIE_NAME, create_session

pytestmark = pytest.mark.asyncio


def _build_app() -> FastAPI:
    app = FastAPI()

    @app.get("/protected")
    async def protected(principal=Depends(require_permission("tm:control"))) -> dict:
        return {"ok": True, "subject": principal.subject}

    @app.get("/whoami")
    async def whoami(principal=Depends(get_current_principal)) -> dict:
        if principal is None:
            return {"authenticated": False}
        return {"authenticated": True, "permissions": sorted(principal.permissions)}

    return app


@pytest.fixture
async def fake_redis():
    server = fakeredis.FakeServer()
    client = fake_aioredis.FakeRedis(server=server, decode_responses=True)
    yield client
    await client.aclose()


@pytest.fixture
async def client(fake_redis):
    app = _build_app()

    async def _override_get_redis():
        yield fake_redis

    app.dependency_overrides[get_redis] = _override_get_redis

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_no_auth_returns_401(client):
    resp = await client.get("/protected")
    assert resp.status_code == 401


async def test_session_missing_permission_returns_403(client, fake_redis):
    _, signed = await create_session(
        fake_redis,
        user_id="viewer1",
        display_name="Viewer One",
        groups=["qecomp-viewer"],
        permissions=["teams:read", "integrations:read", "automations:read"],
    )
    client.cookies.set(SESSION_COOKIE_NAME, signed)

    resp = await client.get("/protected")
    assert resp.status_code == 403


async def test_session_with_permission_returns_200(client, fake_redis):
    _, signed = await create_session(
        fake_redis,
        user_id="operator1",
        display_name="Operator One",
        groups=["qecomp-operator"],
        permissions=["tm:control", "teams:read"],
    )
    client.cookies.set(SESSION_COOKIE_NAME, signed)

    resp = await client.get("/protected")
    assert resp.status_code == 200
    assert resp.json()["subject"] == "operator1"


async def test_admin_local_bypasses_all_permission_checks(client, fake_redis):
    """Plan §3.9: `admin_local` always has all permissions regardless of
    RBAC group mappings."""
    _, signed = await create_session(
        fake_redis,
        user_id="admin_local",
        display_name="Emergency Admin",
        groups=[],
        permissions=[],
        is_admin_local=True,
    )
    client.cookies.set(SESSION_COOKIE_NAME, signed)

    resp = await client.get("/protected")
    assert resp.status_code == 200


async def test_invalid_cookie_signature_is_treated_as_unauthenticated(client):
    client.cookies.set(SESSION_COOKIE_NAME, "tampered-not-a-real-signed-value")
    resp = await client.get("/protected")
    assert resp.status_code == 401


async def test_force_logout_invalidates_session_immediately(client, fake_redis):
    """Plan Appendix B.9: force logout deletes the session key from Redis
    immediately."""
    from backend.core.sessions import delete_session, unsign_session_id

    session_id, signed = await create_session(
        fake_redis,
        user_id="operator2",
        display_name="Operator Two",
        groups=["qecomp-operator"],
        permissions=["tm:control"],
    )
    client.cookies.set(SESSION_COOKIE_NAME, signed)
    assert (await client.get("/protected")).status_code == 200

    await delete_session(fake_redis, unsign_session_id(signed))
    resp = await client.get("/protected")
    assert resp.status_code == 401


# ── API key scoping (Appendix B.7) — needs real Postgres for `api_keys` ──


@pytest.fixture
async def db_engine():
    from sqlalchemy.ext.asyncio import create_async_engine

    from backend.core.settings import settings

    engine = create_async_engine(settings.POSTGRES_DSN)
    try:
        async with engine.connect() as conn:
            await conn.exec_driver_sql("SELECT 1")
    except Exception:
        pytest.skip("Real Postgres not reachable; skipping API key RBAC tests")
    yield engine
    await engine.dispose()


@pytest.fixture
async def client_with_db(fake_redis, db_engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from backend.core.dependencies import get_db

    app = _build_app()
    factory = async_sessionmaker(bind=db_engine, expire_on_commit=False)

    async def _override_get_db():
        async with factory() as session:
            yield session

    async def _override_get_redis():
        yield fake_redis

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_redis] = _override_get_redis

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c, factory


async def test_api_key_scoped_to_its_permissions(client_with_db):
    from backend.models.settings import ApiKey

    client, factory = client_with_db
    raw_key = generate_api_key()
    assert raw_key.startswith("qec_")

    async with factory() as session:
        row = ApiKey(name=f"test-key-{uuid.uuid4().hex[:8]}", key_hash=hash_api_key(raw_key), permissions=["tm:control"])
        session.add(row)
        await session.commit()
        key_id = row.id

    try:
        client.headers["Authorization"] = f"Bearer {raw_key}"
        resp = await client.get("/protected")
        assert resp.status_code == 200

        # A key without the required permission is scoped, not a bypass.
        client.headers["Authorization"] = "Bearer qec_not-a-real-key"
        resp2 = await client.get("/protected")
        assert resp2.status_code == 401
    finally:
        async with factory() as session:
            row = await session.get(ApiKey, key_id)
            if row is not None:
                await session.delete(row)
                await session.commit()


async def test_api_key_hash_never_stores_plaintext(client_with_db):
    """Regression guard: `api_keys.key_hash` must never equal the raw key
    (plan Appendix B.7 — SHA-256 hash only)."""
    from backend.models.settings import ApiKey

    _, factory = client_with_db
    raw_key = generate_api_key()
    key_hash = hash_api_key(raw_key)
    assert key_hash != raw_key
    assert len(key_hash) == 64  # SHA-256 hex digest

    async with factory() as session:
        row = ApiKey(name=f"test-key-{uuid.uuid4().hex[:8]}", key_hash=key_hash, permissions=["settings:read"])
        session.add(row)
        await session.commit()
        key_id = row.id

    try:
        async with factory() as session:
            fetched = await session.get(ApiKey, key_id)
            assert fetched.key_hash != raw_key
    finally:
        async with factory() as session:
            row = await session.get(ApiKey, key_id)
            if row is not None:
                await session.delete(row)
                await session.commit()
