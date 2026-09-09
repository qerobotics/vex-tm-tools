"""Unit tests for the obs integration client.

No real OBS Studio instance exists, so `obswebsocket.obsws` is replaced
with a fake that mimics its actual (synchronous, thread-based) call shape:
`.connect()`, `.disconnect()`, `.call(request_obj) -> request_obj populated
with .datain`, and `.reconnect()`.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import fakeredis.aioredis
import pytest
from obswebsocket import exceptions as obs_exceptions

import backend.modules.integrations.obs.integration as obs_module
from backend.core.exceptions import IntegrationError
from backend.modules.integrations.obs.integration import ObsIntegration

pytestmark = pytest.mark.asyncio


class FakeRequest:
    """Mimics obswebsocket.requests' dynamically-generated request objects."""

    fail_with: Exception | None = None

    def __init__(self, **kwargs: Any) -> None:
        self.name = type(self).__name__
        self.dataout = kwargs
        self.datain: dict[str, Any] = {}


class GetSceneList(FakeRequest):
    pass


class SetCurrentProgramScene(FakeRequest):
    pass


class TriggerHotkeyByName(FakeRequest):
    pass


class FakeObsRequestsModule:
    GetSceneList = GetSceneList
    SetCurrentProgramScene = SetCurrentProgramScene
    TriggerHotkeyByName = TriggerHotkeyByName


class FakeObsWs:
    def __init__(self, host: str, port: int, password: str, legacy: bool = False, timeout: int = 10) -> None:
        self.host = host
        self.port = port
        self.password = password
        self.connected = False
        self.reconnect_calls = 0
        self.reconnect_should_fail = False
        self.scenes = [{"sceneName": "Main"}, {"sceneName": "BRB"}]
        self.current_scene = "Main"

    def connect(self) -> None:
        self.connected = True

    def disconnect(self) -> None:
        self.connected = False

    def reconnect(self) -> None:
        self.reconnect_calls += 1
        if self.reconnect_should_fail:
            self.connected = False
            raise obs_exceptions.ConnectionFailure("reconnect failed")
        self.connected = True

    def call(self, request: FakeRequest) -> FakeRequest:
        if request.fail_with is not None:
            raise request.fail_with
        if isinstance(request, GetSceneList):
            request.datain = {"scenes": self.scenes, "currentProgramSceneName": self.current_scene}
        elif isinstance(request, SetCurrentProgramScene):
            self.current_scene = request.dataout["sceneName"]
            request.datain = {}
        elif isinstance(request, TriggerHotkeyByName):
            request.datain = {}
        return request


@pytest.fixture(autouse=True)
def patch_obsws(monkeypatch):
    GetSceneList.fail_with = None
    SetCurrentProgramScene.fail_with = None
    TriggerHotkeyByName.fail_with = None
    monkeypatch.setattr(obs_module, "obsws", FakeObsWs)
    monkeypatch.setattr(obs_module, "obs_requests", FakeObsRequestsModule)
    yield


@pytest.fixture
async def redis_client():
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


def _make_config(**overrides):
    config = {"host": "127.0.0.1", "port": 4455, "password": "secret", "tags": ["main_stream"]}
    config.update(overrides)
    return config


async def test_setup_missing_host_raises(redis_client):
    integration = ObsIntegration("obs.test", _make_config(host=None), redis_client, None)
    with pytest.raises(IntegrationError):
        await integration.setup()


async def test_setup_connects_and_fetches_scene_list(redis_client):
    integration = ObsIntegration("obs.test", _make_config(), redis_client, None)
    await integration.setup()
    try:
        assert integration._obs.connected is True
        assert integration._scene_list == ["Main", "BRB"]
        assert integration._current_scene == "Main"
        cached = await redis_client.get("qecomp:integration:obs.test:scenes")
        assert cached == "Main,BRB"
    finally:
        await integration.teardown()


async def test_switch_scene_calls_set_current_program_scene(redis_client):
    integration = ObsIntegration("obs.test", _make_config(), redis_client, None)
    await integration.setup()
    try:
        result = await integration.call_service("switch_scene", {"scene_name": "BRB"})
        assert result == {"ok": True, "scene_name": "BRB"}
        assert integration._obs.current_scene == "BRB"
    finally:
        await integration.teardown()


async def test_switch_scene_requires_scene_name(redis_client):
    integration = ObsIntegration("obs.test", _make_config(), redis_client, None)
    await integration.setup()
    try:
        with pytest.raises(ValueError):
            await integration.call_service("switch_scene", {})
    finally:
        await integration.teardown()


async def test_trigger_hotkey_calls_correct_request(redis_client):
    integration = ObsIntegration("obs.test", _make_config(), redis_client, None)
    await integration.setup()
    try:
        result = await integration.call_service("trigger_hotkey", {"hotkey_name": "StartRecording"})
        assert result == {"ok": True, "hotkey_name": "StartRecording"}
    finally:
        await integration.teardown()


async def test_unknown_service_raises_value_error(redis_client):
    integration = ObsIntegration("obs.test", _make_config(), redis_client, None)
    await integration.setup()
    try:
        with pytest.raises(ValueError):
            await integration.call_service("cut_to_black", {})
    finally:
        await integration.teardown()


async def test_call_service_without_connection_raises_integration_error(redis_client):
    integration = ObsIntegration("obs.test", _make_config(), redis_client, None)
    integration._obs = None
    with pytest.raises(IntegrationError):
        await integration.call_service("switch_scene", {"scene_name": "Main"})


async def test_connection_closed_reconnects_and_recovers_to_connected(redis_client):
    """A transient disconnect should not leave the instance stuck reporting
    DEGRADED forever once the background reconnect actually succeeds."""
    integration = ObsIntegration("obs.test", _make_config(), redis_client, None)
    await integration.setup()
    try:
        SetCurrentProgramScene.fail_with = obs_exceptions.MessageTimeout("no reply")
        with pytest.raises(IntegrationError):
            await integration.call_service("switch_scene", {"scene_name": "BRB"})

        assert integration._obs.reconnect_calls == 1
        # The reconnect (and subsequent scene-list refresh) succeeded, so the
        # status must be reported as recovered, not stuck at DEGRADED.
        status = await redis_client.get("qecomp:integration:obs.test:status")
        assert status == "CONNECTED"
    finally:
        SetCurrentProgramScene.fail_with = None
        await integration.teardown()


async def test_connection_closed_stays_degraded_when_reconnect_fails(redis_client):
    integration = ObsIntegration("obs.test", _make_config(), redis_client, None)
    await integration.setup()
    try:
        integration._obs.reconnect_should_fail = True
        SetCurrentProgramScene.fail_with = obs_exceptions.MessageTimeout("no reply")
        with pytest.raises(IntegrationError):
            await integration.call_service("switch_scene", {"scene_name": "BRB"})

        status = await redis_client.get("qecomp:integration:obs.test:status")
        assert status == "DEGRADED"
    finally:
        SetCurrentProgramScene.fail_with = None
        integration._obs.reconnect_should_fail = False
        await integration.teardown()


async def test_get_state_reports_current_scene(redis_client):
    integration = ObsIntegration("obs.test", _make_config(), redis_client, None)
    await integration.setup()
    try:
        state = await integration.get_state()
        assert state["connected"] is True
        assert state["current_scene"] == "Main"
        assert state["scenes"] == ["Main", "BRB"]
    finally:
        await integration.teardown()


async def test_get_state_never_raises_without_connection(redis_client):
    integration = ObsIntegration("obs.test", _make_config(), redis_client, None)
    state = await integration.get_state()
    assert state["connected"] is False


async def test_teardown_never_raises(redis_client):
    integration = ObsIntegration("obs.test", _make_config(), redis_client, None)
    await integration.setup()
    bad = MagicMock()
    bad.disconnect.side_effect = RuntimeError("boom")
    integration._obs = bad
    await integration.teardown()  # must not raise
