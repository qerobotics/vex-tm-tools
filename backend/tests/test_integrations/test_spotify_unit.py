"""Unit tests for the spotify integration client (fakeredis + mocked httpx).

No real Spotify hardware/account exists, so every Web API call is mocked.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import fakeredis.aioredis
import pytest

from backend.modules.integrations.spotify.integration import SpotifyIntegration

pytestmark = pytest.mark.asyncio


def _make_config(**overrides):
    config = {
        "client_id": "spotify-client-id",
        "client_secret": "spotify-client-secret",
        "device_name": "Field Speaker",
        "tags": ["fs1"],
    }
    config.update(overrides)
    return config


@pytest.fixture
async def redis_client():
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


@pytest.fixture
async def integration(redis_client):
    inst = SpotifyIntegration("spotify.test", _make_config(), redis_client, None)
    inst._http = AsyncMock()
    inst._access_token = "initial-access-token"
    inst._device_id = "device-123"
    yield inst
    inst._tasks = []  # avoid real teardown() task-cancellation churn in unit tests


def _mock_response(status_code=200, json_data=None, headers=None, content=b"{}"):
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = headers or {}
    resp.content = content
    resp.json.return_value = json_data if json_data is not None else {}
    if status_code >= 400:
        import httpx

        def _raise():
            raise httpx.HTTPStatusError("error", request=MagicMock(), response=resp)

        resp.raise_for_status.side_effect = _raise
    else:
        resp.raise_for_status = MagicMock()
    return resp


async def test_set_oauth_tokens_encrypts_refresh_token(redis_client):
    inst = SpotifyIntegration("spotify.test", _make_config(), redis_client, None)
    inst._http = AsyncMock()
    inst._tasks = []
    await inst.set_oauth_tokens("access-tok", "refresh-tok", 3600)

    assert inst._access_token == "access-tok"
    stored_access = await redis_client.get("qecomp:integration:spotify.test:spotify_access_token")
    assert stored_access == "access-tok"
    stored_refresh = await redis_client.get("qecomp:integration:spotify.test:spotify_refresh_token")
    assert stored_refresh is not None
    assert stored_refresh != "refresh-tok"  # must be encrypted, not plaintext

    for task in inst._tasks:
        task.cancel()
    await asyncio.gather(*inst._tasks, return_exceptions=True)


async def test_play_sends_correct_request(integration):
    integration._http.request = AsyncMock(return_value=_mock_response(200))
    await integration.call_service("play", {"context_uri": "spotify:playlist:abc"})

    integration._http.request.assert_awaited_once()
    call = integration._http.request.call_args
    assert call.args[0] == "PUT"
    assert call.args[1] == "/me/player/play"
    assert call.kwargs["params"] == {"device_id": "device-123"}
    assert call.kwargs["json"] == {"context_uri": "spotify:playlist:abc"}


async def test_pause_next_previous(integration):
    integration._http.request = AsyncMock(return_value=_mock_response(200))
    await integration.call_service("pause", {})
    await integration.call_service("next", {})
    await integration.call_service("previous", {})
    methods_paths = [(c.args[0], c.args[1]) for c in integration._http.request.call_args_list]
    assert methods_paths == [
        ("PUT", "/me/player/pause"),
        ("POST", "/me/player/next"),
        ("POST", "/me/player/previous"),
    ]


async def test_set_volume_passes_volume_percent(integration):
    integration._http.request = AsyncMock(return_value=_mock_response(200))
    await integration.call_service("set_volume", {"volume": 42})
    call = integration._http.request.call_args
    assert call.kwargs["params"] == {"volume_percent": 42, "device_id": "device-123"}


async def test_play_playlist_track_with_explicit_track_number(integration):
    integration._http.request = AsyncMock(return_value=_mock_response(200))
    await integration.call_service(
        "play_playlist_track", {"playlist_uri": "spotify:playlist:xyz", "track_number": 3}
    )
    call = integration._http.request.call_args
    assert call.kwargs["json"] == {"context_uri": "spotify:playlist:xyz", "offset": {"position": 2}}


async def test_play_playlist_track_random_when_omitted(integration, monkeypatch):
    responses = [
        _mock_response(200, json_data={"total": 5}),  # playlist total lookup
        _mock_response(200),  # play call
    ]
    integration._http.request = AsyncMock(side_effect=responses)
    monkeypatch.setattr("random.randint", lambda a, b: 3)

    result = await integration.call_service("play_playlist_track", {"playlist_uri": "spotify:playlist:xyz"})
    assert result == {"ok": True, "track_number": 3}
    play_call = integration._http.request.call_args_list[1]
    assert play_call.kwargs["json"]["offset"] == {"position": 2}


async def test_unknown_service_raises_value_error(integration):
    with pytest.raises(ValueError):
        await integration.call_service("not_a_service", {})


async def test_rate_limit_retries_once_then_succeeds(integration):
    responses = [
        _mock_response(429, headers={"Retry-After": "0"}),
        _mock_response(200),
    ]
    integration._http.request = AsyncMock(side_effect=responses)
    result = await integration.call_service("pause", {})
    assert result == {"ok": True}
    assert integration._http.request.call_count == 2


async def test_rate_limit_only_retries_once_not_busy_loop(integration):
    responses = [
        _mock_response(429, headers={"Retry-After": "0"}),
        _mock_response(429, headers={"Retry-After": "0"}),
    ]
    integration._http.request = AsyncMock(side_effect=responses)
    with pytest.raises(Exception):
        await integration.call_service("pause", {})
    # Only two calls total: original + exactly one retry.
    assert integration._http.request.call_count == 2


async def test_401_triggers_single_token_refresh_then_retries(integration):
    integration._refresh_token = "refresh-tok"
    integration._refresh_access_token = AsyncMock(return_value=3600)
    responses = [
        _mock_response(401),
        _mock_response(200),
    ]
    integration._http.request = AsyncMock(side_effect=responses)
    result = await integration.call_service("pause", {})
    assert result == {"ok": True}
    integration._refresh_access_token.assert_awaited_once()


async def test_get_state_returns_cached_now_playing_without_polling(integration):
    integration._cached_state["now_playing"] = {"track": "Song", "is_playing": True}
    integration._http.request = AsyncMock(side_effect=AssertionError("must not poll inside get_state"))
    state = await integration.get_state()
    assert state["now_playing"] == {"track": "Song", "is_playing": True}


async def test_device_resolution_matches_by_name(redis_client):
    inst = SpotifyIntegration("spotify.test", _make_config(device_name="Field Speaker"), redis_client, None)
    inst._http = AsyncMock()
    inst._http.request = AsyncMock(
        return_value=_mock_response(
            200,
            json_data={
                "devices": [
                    {"id": "d1", "name": "Other Speaker"},
                    {"id": "d2", "name": "field speaker"},
                ]
            },
        )
    )
    inst._access_token = "tok"
    device_id = await inst._resolve_device_id()
    assert device_id == "d2"


async def test_teardown_never_raises(redis_client):
    inst = SpotifyIntegration("spotify.test", _make_config(), redis_client, None)
    inst._http = AsyncMock()
    inst._http.aclose = AsyncMock(side_effect=RuntimeError("boom"))
    inst._tasks = []
    await inst.teardown()  # must not raise
