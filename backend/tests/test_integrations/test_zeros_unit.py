"""Unit tests for the zeros integration client.

No real ZerOS lighting console exists. `SimpleUDPClient` is exercised for
real (it's just a local UDP socket, so it is safe/fast to construct and use
directly against a real `AsyncioOSCUDPServer` listening on localhost — this
gives a genuine wire-level check of the OSC address/message format).
Database access for preset-name resolution is mocked via a fake async
session factory (no real Postgres needed for these tests).
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import fakeredis.aioredis
import pytest
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import AsyncIOOSCUDPServer

from backend.core.exceptions import IntegrationError
from backend.modules.integrations.zeros.integration import ZerosIntegration

pytestmark = pytest.mark.asyncio


def _make_config(**overrides):
    config = {"ip": "127.0.0.1", "port": 18730, "tags": ["lighting_board"]}
    config.update(overrides)
    return config


@pytest.fixture
async def redis_client():
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


class _FakeResult:
    def __init__(self, row: tuple[Any, ...] | None) -> None:
        self._row = row

    def first(self):
        return self._row


class _FakeSession:
    def __init__(self, integration_id: str | None, presets: dict[str, int]) -> None:
        self._integration_id = integration_id
        self._presets = presets

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def execute(self, statement, params=None):
        sql = str(statement)
        if "FROM integration_instances" in sql:
            if self._integration_id is None:
                return _FakeResult(None)
            return _FakeResult((self._integration_id,))
        if "FROM zeros_presets" in sql:
            preset_name = params["preset_name"]
            number = self._presets.get(preset_name)
            return _FakeResult((number,) if number is not None else None)
        raise AssertionError(f"unexpected SQL: {sql}")


def _make_db_pool(integration_id: str | None = "int-uuid-1", presets: dict[str, int] | None = None):
    presets = presets or {"field_1_active": 14}

    def factory():
        return _FakeSession(integration_id, presets)

    return factory


async def test_setup_missing_ip_raises(redis_client):
    integration = ZerosIntegration("zeros.test", _make_config(ip=None), redis_client, None)
    with pytest.raises(IntegrationError):
        await integration.setup()


async def test_set_preset_by_id_sends_real_osc_message(redis_client):
    received: list[tuple[str, list]] = []
    dispatcher = Dispatcher()

    def handler(address, *args):
        received.append((address, list(args)))

    dispatcher.map("/zeros/playback/go/*", handler)

    loop = asyncio.get_running_loop()
    server = AsyncIOOSCUDPServer(("127.0.0.1", 18731), dispatcher, loop)
    transport, protocol = await server.create_serve_endpoint()
    try:
        integration = ZerosIntegration("zeros.test", _make_config(port=18731), redis_client, None)
        await integration.setup()
        try:
            result = await integration.call_service("set_preset", {"preset_id": 42})
            assert result == {"ok": True, "preset_number": 42, "address": "/zeros/playback/go/42"}
            await asyncio.sleep(0.2)  # let the UDP datagram actually arrive
        finally:
            await integration.teardown()
    finally:
        transport.close()

    assert received == [("/zeros/playback/go/42", [])]


async def test_set_preset_by_name_resolves_via_db(redis_client):
    integration = ZerosIntegration(
        "zeros.test", _make_config(), redis_client, _make_db_pool(presets={"field_1_active": 14})
    )
    await integration.setup()
    try:
        result = await integration.call_service("set_preset", {"preset_name": "field_1_active"})
        assert result["preset_number"] == 14
    finally:
        await integration.teardown()


async def test_set_preset_unknown_name_raises_value_error(redis_client):
    integration = ZerosIntegration(
        "zeros.test", _make_config(), redis_client, _make_db_pool(presets={"other": 1})
    )
    await integration.setup()
    try:
        with pytest.raises(ValueError):
            await integration.call_service("set_preset", {"preset_name": "does_not_exist"})
    finally:
        await integration.teardown()


async def test_set_preset_requires_id_or_name(redis_client):
    integration = ZerosIntegration("zeros.test", _make_config(), redis_client, None)
    await integration.setup()
    try:
        with pytest.raises(ValueError):
            await integration.call_service("set_preset", {})
    finally:
        await integration.teardown()


async def test_set_preset_by_name_without_db_pool_raises_integration_error(redis_client):
    integration = ZerosIntegration("zeros.test", _make_config(), redis_client, None)
    await integration.setup()
    try:
        with pytest.raises(IntegrationError):
            await integration.call_service("set_preset", {"preset_name": "anything"})
    finally:
        await integration.teardown()


async def test_unknown_service_raises_value_error(redis_client):
    integration = ZerosIntegration("zeros.test", _make_config(), redis_client, None)
    await integration.setup()
    try:
        with pytest.raises(ValueError):
            await integration.call_service("blackout", {})
    finally:
        await integration.teardown()


async def test_call_service_without_setup_raises_integration_error(redis_client):
    integration = ZerosIntegration("zeros.test", _make_config(), redis_client, None)
    with pytest.raises(IntegrationError):
        await integration.call_service("set_preset", {"preset_id": 1})


async def test_get_state_reports_last_preset(redis_client):
    integration = ZerosIntegration("zeros.test", _make_config(), redis_client, None)
    await integration.setup()
    try:
        integration._client.send_message = MagicMock()
        await integration.call_service("set_preset", {"preset_id": 9})
        state = await integration.get_state()
        assert state["connected"] is True
        assert state["last_preset"] == 9
    finally:
        await integration.teardown()


async def test_teardown_never_raises(redis_client):
    integration = ZerosIntegration("zeros.test", _make_config(), redis_client, None)
    await integration.setup()
    await integration.teardown()
    assert integration._client is None
