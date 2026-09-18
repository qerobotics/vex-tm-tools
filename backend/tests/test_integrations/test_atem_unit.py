"""Unit tests for the atem integration client.

No real ATEM switcher hardware exists, so `PyATEMMax.ATEMMax` is replaced
with a fake that mimics its synchronous, thread-based API shape (connect(),
waitForConnection(), setProgramInputVideoSource(), disconnect(), the
`connected` attribute, and `registerEvent`/event callbacks) closely enough
to exercise the integration's `asyncio.to_thread()` wrapping and its
asyncio.Event cross-thread signalling.
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

import fakeredis.aioredis
import pytest

import backend.modules.integrations.atem.integration as atem_module
from backend.core.exceptions import IntegrationError
from backend.modules.integrations.atem.integration import AtemIntegration

pytestmark = pytest.mark.asyncio


class _FakeEvents:
    connect = "connect"
    disconnect = "disconnect"


class _FakeAtemProtocol:
    events = _FakeEvents()


class _FakeInputSource:
    def __init__(self, video_source: int = 1) -> None:
        self.videoSource = video_source


class FakeATEMMax:
    """Mimics enough of PyATEMMax.ATEMMax's synchronous surface for tests."""

    fail_to_connect = False

    def __init__(self) -> None:
        self.atem = _FakeAtemProtocol()
        self.connected = False
        self._callbacks: dict[str, list[Any]] = {}
        self.programInput = {0: _FakeInputSource(1)}
        self.previewInput = {0: _FakeInputSource(2)}
        self.set_program_calls: list[tuple[int, int]] = []
        self.set_preview_calls: list[tuple[int, int]] = []

    def registerEvent(self, event: str, callback) -> None:
        self._callbacks.setdefault(event, []).append(callback)

    def connect(self, ip: str) -> None:
        self.ip = ip
        if not FakeATEMMax.fail_to_connect:
            self.connected = True
            for cb in self._callbacks.get("connect", []):
                cb({})

    def waitForConnection(self, infinite: bool, timeout: float, waitForFullHandshake: bool) -> bool:
        return self.connected

    def disconnect(self) -> None:
        self.connected = False
        for cb in self._callbacks.get("disconnect", []):
            cb({})

    def setProgramInputVideoSource(self, mE: int, videoSource: int) -> None:
        self.set_program_calls.append((mE, videoSource))
        self.programInput[mE].videoSource = videoSource

    def setPreviewInputVideoSource(self, mE: int, videoSource: int) -> None:
        self.set_preview_calls.append((mE, videoSource))
        self.previewInput[mE].videoSource = videoSource


@pytest.fixture(autouse=True)
def patch_atemmax(monkeypatch):
    FakeATEMMax.fail_to_connect = False
    monkeypatch.setattr(atem_module.PyATEMMax, "ATEMMax", FakeATEMMax)
    yield


@pytest.fixture
async def redis_client():
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


def _make_config(**overrides):
    config = {"ip": "10.0.0.50", "field_to_input": {"1": 1, "2": 2}, "tags": ["main_switcher"]}
    config.update(overrides)
    return config


async def test_setup_missing_ip_raises(redis_client):
    integration = AtemIntegration("atem.test", _make_config(ip=None), redis_client, None)
    with pytest.raises(IntegrationError):
        await integration.setup()


async def test_setup_connects_via_to_thread(redis_client):
    integration = AtemIntegration("atem.test", _make_config(), redis_client, None)
    await integration.setup()
    try:
        assert integration._atem is not None
        assert integration._atem.connected is True
        assert integration._connected_event.is_set()
    finally:
        await integration.teardown()


async def test_setup_raises_when_connection_fails(redis_client):
    FakeATEMMax.fail_to_connect = True
    integration = AtemIntegration("atem.test", _make_config(), redis_client, None)
    with pytest.raises(IntegrationError):
        await integration.setup()
    assert integration._atem is None


async def test_switch_input_calls_set_program_input(redis_client):
    integration = AtemIntegration("atem.test", _make_config(), redis_client, None)
    await integration.setup()
    try:
        result = await integration.call_service("switch_input", {"input_index": 3})
        assert result == {"ok": True, "input_index": 3}
        assert integration._atem.set_program_calls == [(0, 3)]
    finally:
        await integration.teardown()


async def test_set_preview_calls_set_preview_input(redis_client):
    integration = AtemIntegration("atem.test", _make_config(), redis_client, None)
    await integration.setup()
    try:
        await integration.call_service("set_preview", {"input_index": 5})
        assert integration._atem.set_preview_calls == [(0, 5)]
    finally:
        await integration.teardown()


async def test_unknown_service_raises_value_error(redis_client):
    integration = AtemIntegration("atem.test", _make_config(), redis_client, None)
    await integration.setup()
    try:
        with pytest.raises(ValueError):
            await integration.call_service("fade_to_black", {})
    finally:
        await integration.teardown()


async def test_missing_input_index_raises_value_error(redis_client):
    integration = AtemIntegration("atem.test", _make_config(), redis_client, None)
    await integration.setup()
    try:
        with pytest.raises(ValueError):
            await integration.call_service("switch_input", {})
    finally:
        await integration.teardown()


async def test_call_service_without_connection_raises_integration_error(redis_client):
    integration = AtemIntegration("atem.test", _make_config(), redis_client, None)
    integration._atem = None
    with pytest.raises(IntegrationError):
        await integration.call_service("switch_input", {"input_index": 1})


async def test_disconnect_callback_clears_connected_event(redis_client):
    integration = AtemIntegration("atem.test", _make_config(), redis_client, None)
    await integration.setup()
    try:
        assert integration._connected_event.is_set()
        integration._atem.disconnect()
        await asyncio.sleep(0)  # let call_soon_threadsafe callback run
        assert not integration._connected_event.is_set()
        integration._atem.connected = True  # simulate teardown() not re-disconnecting twice
    finally:
        await integration.teardown()


async def test_get_state_reports_connection_and_inputs(redis_client):
    integration = AtemIntegration("atem.test", _make_config(), redis_client, None)
    await integration.setup()
    try:
        state = await integration.get_state()
        assert state["connected"] is True
        assert state["program_input"] == 1
        assert state["preview_input"] == 2
    finally:
        await integration.teardown()


async def test_get_state_never_raises_without_atem(redis_client):
    integration = AtemIntegration("atem.test", _make_config(), redis_client, None)
    state = await integration.get_state()
    assert state["connected"] is False


async def test_teardown_never_raises(redis_client):
    integration = AtemIntegration("atem.test", _make_config(), redis_client, None)
    await integration.setup()
    bad = MagicMock()
    bad.disconnect.side_effect = RuntimeError("boom")
    integration._atem = bad
    await integration.teardown()  # must not raise
