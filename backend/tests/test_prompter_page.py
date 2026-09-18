"""Tests for `GET /prompter/{entity_id}` in `backend/main.py` (plan Appendix
B.3/B.4/B.8): serves the standalone teleprompter page with the HMAC token
validated server-side, and safely injects `entity_id`/`token` into the
page's `<script>` block.
"""
from __future__ import annotations

import uuid
from urllib.parse import quote

from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import pytest

from backend.core.security import generate_prompter_token
from backend.core.settings import settings
from backend.models.timer import TimerInstance

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def test_session_factory():
    engine = create_async_engine(settings.POSTGRES_DSN, future=True)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
async def client_and_db(test_session_factory):
    from backend.core.db import get_db
    from backend.main import create_app

    app = create_app()

    async def _override_get_db():
        async with test_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, test_session_factory


async def _make_timer(session_factory, entity_id: str) -> TimerInstance:
    async with session_factory() as session:
        row = TimerInstance(
            entity_id=entity_id, display_name=entity_id, field_set_id=1, field_id=1
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row


async def _cleanup(session_factory, entity_id: str) -> None:
    async with session_factory() as session:
        await session.execute(delete(TimerInstance).where(TimerInstance.entity_id == entity_id))
        await session.commit()


def _unique_entity_id() -> str:
    return f"timer.test_prompter_{uuid.uuid4().hex[:8]}"


async def test_prompter_page_requires_valid_token(client_and_db):
    client, session_factory = client_and_db
    entity_id = _unique_entity_id()
    row = await _make_timer(session_factory, entity_id)
    try:
        # No token -> 403.
        resp = await client.get(f"/prompter/{entity_id}")
        assert resp.status_code == 403

        # Wrong token -> 403.
        resp = await client.get(f"/prompter/{entity_id}", params={"token": "wrong"})
        assert resp.status_code == 403

        # Correct token -> 200, with entity_id safely embedded.
        token = generate_prompter_token(row.entity_id, row.token_nonce)
        resp = await client.get(f"/prompter/{entity_id}", params={"token": token})
        assert resp.status_code == 200
        assert entity_id in resp.text
        # The quoted JS-literal placeholders must have been substituted
        # (unquoted mentions of the placeholder name remain in the file's
        # explanatory HTML comment, which is expected and fine).
        assert '"__ENTITY_ID__"' not in resp.text
        assert '"__TOKEN__"' not in resp.text
    finally:
        await _cleanup(session_factory, entity_id)


async def test_prompter_page_404_for_unknown_entity(client_and_db):
    client, _ = client_and_db
    resp = await client.get("/prompter/timer.does_not_exist", params={"token": "x"})
    assert resp.status_code == 404


async def test_prompter_page_escapes_entity_id_for_script_injection(client_and_db):
    """An entity_id containing a double quote must not be able to break out
    of the `entityId: "..."` JS string literal (regression test for the
    code-review finding that a plain str.replace() without JSON escaping
    would allow script injection). Deliberately avoids a literal '/' in the
    payload — a slash in a path parameter is a separate, generic Starlette
    routing limitation (a `{entity_id}` path segment can't contain one even
    URL-encoded) unrelated to the JSON-escaping fix under test here, and
    entity_ids never contain '/' per plan §3.3's `<domain>.<name>` format."""
    client, session_factory = client_and_db
    malicious_id = 'timer.x"};alert(1);'
    async with session_factory() as session:
        row = TimerInstance(
            entity_id=malicious_id, display_name="x", field_set_id=1, field_id=1
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
    try:
        token = generate_prompter_token(row.entity_id, row.token_nonce)
        resp = await client.get(
            f"/prompter/{quote(malicious_id, safe='')}", params={"token": token}
        )
        assert resp.status_code == 200
        # The raw quote must not appear unescaped inside the script block —
        # json.dumps() escapes it to \" so it can't close the JS string.
        assert 'entityId: "timer.x"};' not in resp.text
        assert "alert(1)" in resp.text  # content is present, just safely quoted
    finally:
        await _cleanup(session_factory, malicious_id)
