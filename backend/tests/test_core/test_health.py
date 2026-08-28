"""Tests for /healthz and /readyz using httpx.AsyncClient against the app."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app

pytestmark = pytest.mark.asyncio


async def test_healthz_always_ok():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_readyz_reports_db_and_redis_status():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/readyz")
    body = resp.json()
    assert "db" in body and "redis" in body and "status" in body
    # With the compose stack up, both should be reachable.
    assert resp.status_code in (200, 503)
