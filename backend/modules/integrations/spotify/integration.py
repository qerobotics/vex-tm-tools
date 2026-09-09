"""Async Spotify integration client (plan §3.5 / §5.4 / §C.7.3).

Auth is the browser-side PKCE flow (plan §3.5): the frontend obtains
`access_token`/`refresh_token` and POSTs them to
`POST /api/v1/integrations/<entity_id>/oauth_token`. That router endpoint
(a later wave) calls `set_oauth_tokens()` below, which is this integration's
half of the contract — persisting the tokens (refresh token encrypted) in
Redis and kicking off the background auto-refresh task.

Per §C.7.3:
- A single persistent `httpx.AsyncClient` for all Spotify Web API calls.
- Token refresh runs as a background `asyncio.Task` that wakes via
  `asyncio.sleep(expires_in - 60)` *before* expiry — never inside
  `call_service()`.
- HTTP 429 is handled by reading `Retry-After`, sleeping once, and retrying
  once — never busy-looping.
- "Now playing" telemetry is polled at most every 5s by a background task;
  `get_state()` only ever returns the last cached snapshot.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import random
import time
from typing import Any

import httpx

from backend.core.exceptions import IntegrationError
from backend.core.security import decrypt, encrypt
from backend.modules.integrations.base import Integration

logger = logging.getLogger(__name__)

TOKEN_URL = "https://accounts.spotify.com/api/token"
API_BASE_URL = "https://api.spotify.com/v1"
PLAYBACK_POLL_INTERVAL_SECONDS = 5

ACCESS_TOKEN_KEY_TMPL = "qecomp:integration:{entity_id}:spotify_access_token"
REFRESH_TOKEN_KEY_TMPL = "qecomp:integration:{entity_id}:spotify_refresh_token"


class SpotifyIntegration(Integration):
    def __init__(self, entity_id: str, config: dict[str, Any], redis: Any, db_pool: Any) -> None:
        super().__init__(entity_id, config, redis, db_pool)
        self._http: httpx.AsyncClient | None = None
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._device_id: str | None = None
        self._tasks: list[asyncio.Task] = []
        self._shutdown = asyncio.Event()
        self._cached_state: dict[str, Any] = {"now_playing": None, "authenticated": False}

    # ── lifecycle ────────────────────────────────────────────────────
    async def setup(self) -> None:
        self._shutdown = asyncio.Event()
        self._http = httpx.AsyncClient(base_url=API_BASE_URL, timeout=10.0)

        refresh_token = await self._redis.get(REFRESH_TOKEN_KEY_TMPL.format(entity_id=self.entity_id))
        if refresh_token:
            try:
                self._refresh_token = decrypt(refresh_token)
            except Exception:
                logger.exception("spotify[%s]: failed to decrypt stored refresh token", self.entity_id)
                self._refresh_token = None

        access_token = await self._redis.get(ACCESS_TOKEN_KEY_TMPL.format(entity_id=self.entity_id))
        if access_token:
            self._access_token = access_token
            self._cached_state["authenticated"] = True
        elif self._refresh_token:
            try:
                await self._refresh_access_token()
                self._cached_state["authenticated"] = True
            except Exception:
                logger.warning("spotify[%s]: initial token refresh failed; awaiting re-auth", self.entity_id)

        self._tasks = [asyncio.create_task(self._playback_poll_loop())]
        if self._refresh_token:
            self._tasks.append(asyncio.create_task(self._refresh_loop()))

    async def teardown(self) -> None:
        try:
            self._shutdown.set()
            for task in self._tasks:
                task.cancel()
            if self._tasks:
                await asyncio.gather(*self._tasks, return_exceptions=True)
            self._tasks = []
            if self._http is not None:
                with contextlib.suppress(Exception):
                    await self._http.aclose()
                self._http = None
        except Exception:
            logger.exception("Error during spotify teardown for %s", self.entity_id)

    # ── PKCE token intake (called by the oauth_token router endpoint) ─
    async def set_oauth_tokens(self, access_token: str, refresh_token: str | None, expires_in: int) -> None:
        """Persist tokens obtained via the frontend's PKCE flow (plan §3.5).

        The refresh token is encrypted at rest (Fernet) before being cached
        in Redis. Restarts an in-flight refresh task with the new token.
        """
        self._access_token = access_token
        await self._redis.set(
            ACCESS_TOKEN_KEY_TMPL.format(entity_id=self.entity_id),
            access_token,
            ex=max(int(expires_in) - 60, 30),
        )
        if refresh_token:
            self._refresh_token = refresh_token
            await self._redis.set(
                REFRESH_TOKEN_KEY_TMPL.format(entity_id=self.entity_id),
                encrypt(refresh_token),
            )
        self._cached_state["authenticated"] = True

        for task in self._tasks:
            if getattr(task, "_qecomp_kind", None) == "refresh":
                task.cancel()
        refresh_task = asyncio.create_task(self._refresh_loop(initial_expires_in=expires_in))
        refresh_task._qecomp_kind = "refresh"  # type: ignore[attr-defined]
        self._tasks.append(refresh_task)

    # ── background refresh ───────────────────────────────────────────
    async def _refresh_loop(self, initial_expires_in: int | None = None) -> None:
        expires_in = initial_expires_in or 3600
        while not self._shutdown.is_set():
            await asyncio.sleep(max(expires_in - 60, 30))
            if self._shutdown.is_set():
                return
            try:
                expires_in = await self._refresh_access_token()
            except Exception:
                logger.exception("spotify[%s]: background token refresh failed", self.entity_id)
                expires_in = 60  # retry sooner after a failure

    async def _refresh_access_token(self) -> int:
        if not self._refresh_token:
            raise IntegrationError(f"spotify[{self.entity_id}]: no refresh token available")
        assert self._http is not None
        async with httpx.AsyncClient(timeout=10.0) as auth_client:
            resp = await auth_client.post(
                TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self._refresh_token,
                    "client_id": self.config.get("client_id", ""),
                },
                auth=(self.config.get("client_id", ""), self.config.get("client_secret", "")),
            )
        resp.raise_for_status()
        data = resp.json()
        self._access_token = data["access_token"]
        expires_in = int(data.get("expires_in", 3600))
        await self._redis.set(
            ACCESS_TOKEN_KEY_TMPL.format(entity_id=self.entity_id),
            self._access_token,
            ex=max(expires_in - 60, 30),
        )
        # Spotify does not always return a new refresh token; keep the old one.
        new_refresh = data.get("refresh_token")
        if new_refresh:
            self._refresh_token = new_refresh
            await self._redis.set(REFRESH_TOKEN_KEY_TMPL.format(entity_id=self.entity_id), encrypt(new_refresh))
        return expires_in

    # ── device resolution ────────────────────────────────────────────
    async def _resolve_device_id(self) -> str | None:
        if self._device_id:
            return self._device_id
        data = await self._request("GET", "/me/player/devices")
        devices = (data or {}).get("devices", [])
        if not devices:
            return None
        device_name = self.config.get("device_name")
        if device_name:
            for device in devices:
                if device.get("name", "").lower() == device_name.lower():
                    self._device_id = device["id"]
                    return self._device_id
        self._device_id = devices[0]["id"]
        return self._device_id

    # ── services ─────────────────────────────────────────────────────
    async def call_service(self, service: str, data: dict[str, Any]) -> dict[str, Any]:
        data = data or {}
        handler = getattr(self, f"_svc_{service}", None)
        if handler is None:
            raise ValueError(f"Unknown service '{service}' for spotify integration")
        return await handler(data)

    async def _svc_play(self, data: dict[str, Any]) -> dict[str, Any]:
        device_id = await self._resolve_device_id()
        body = {}
        if data.get("context_uri"):
            body["context_uri"] = data["context_uri"]
        await self._request("PUT", "/me/player/play", params={"device_id": device_id}, json_body=body or None)
        return {"ok": True}

    async def _svc_play_playlist_track(self, data: dict[str, Any]) -> dict[str, Any]:
        playlist_uri = data.get("playlist_uri")
        if not playlist_uri:
            raise ValueError("play_playlist_track requires 'playlist_uri'")
        device_id = await self._resolve_device_id()
        track_number = data.get("track_number")
        if track_number is None:
            playlist_id = playlist_uri.rsplit(":", 1)[-1]
            items = await self._request("GET", f"/playlists/{playlist_id}/tracks", params={"fields": "total"})
            total = (items or {}).get("total", 0)
            if not total:
                return {"ok": False, "reason": "playlist empty"}
            track_number = random.randint(1, total)
        offset = {"position": track_number - 1}
        await self._request(
            "PUT",
            "/me/player/play",
            params={"device_id": device_id},
            json_body={"context_uri": playlist_uri, "offset": offset},
        )
        return {"ok": True, "track_number": track_number}

    async def _svc_play_track(self, data: dict[str, Any]) -> dict[str, Any]:
        track_uri = data.get("track_uri")
        if not track_uri:
            raise ValueError("play_track requires 'track_uri'")
        if not track_uri.startswith("spotify:track:"):
            track_uri = f"spotify:track:{track_uri}"
        device_id = await self._resolve_device_id()
        start_time_ms = int(data.get("start_time_s", 0)) * 1000
        await self._request(
            "PUT",
            "/me/player/play",
            params={"device_id": device_id},
            json_body={"uris": [track_uri], "position_ms": start_time_ms},
        )
        return {"ok": True}

    async def _svc_pause(self, data: dict[str, Any]) -> dict[str, Any]:
        device_id = await self._resolve_device_id()
        await self._request("PUT", "/me/player/pause", params={"device_id": device_id})
        return {"ok": True}

    async def _svc_next(self, data: dict[str, Any]) -> dict[str, Any]:
        device_id = await self._resolve_device_id()
        await self._request("POST", "/me/player/next", params={"device_id": device_id})
        return {"ok": True}

    async def _svc_previous(self, data: dict[str, Any]) -> dict[str, Any]:
        device_id = await self._resolve_device_id()
        await self._request("POST", "/me/player/previous", params={"device_id": device_id})
        return {"ok": True}

    async def _svc_set_volume(self, data: dict[str, Any]) -> dict[str, Any]:
        volume = int(data.get("volume", 50))
        device_id = await self._resolve_device_id()
        await self._request(
            "PUT", "/me/player/volume", params={"volume_percent": volume, "device_id": device_id}
        )
        return {"ok": True}

    # ── HTTP helper (429 handling per §C.7.3) ────────────────────────
    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        _retried_401: bool = False,
        _retried_429: bool = False,
    ) -> dict[str, Any] | None:
        assert self._http is not None
        if not self._access_token:
            raise IntegrationError(f"spotify[{self.entity_id}]: not authenticated")
        headers = {"Authorization": f"Bearer {self._access_token}"}
        resp = await self._http.request(method, path, params=params, json=json_body, headers=headers)

        if resp.status_code == 401 and not _retried_401 and self._refresh_token:
            await self._refresh_access_token()
            return await self._request(method, path, params, json_body, _retried_401=True, _retried_429=_retried_429)

        if resp.status_code == 429 and not _retried_429:
            retry_after = int(resp.headers.get("Retry-After", 1))
            await asyncio.sleep(retry_after)
            return await self._request(method, path, params, json_body, _retried_401=_retried_401, _retried_429=True)

        resp.raise_for_status()
        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()

    # ── telemetry ─────────────────────────────────────────────────────
    async def _playback_poll_loop(self) -> None:
        while not self._shutdown.is_set():
            try:
                if self._access_token:
                    data = await self._request("GET", "/me/player")
                    if data:
                        item = data.get("item") or {}
                        self._cached_state["now_playing"] = {
                            "track": item.get("name"),
                            "artist": ", ".join(a.get("name", "") for a in item.get("artists", [])),
                            "progress_ms": data.get("progress_ms"),
                            "duration_ms": item.get("duration_ms"),
                            "is_playing": data.get("is_playing"),
                        }
                    else:
                        self._cached_state["now_playing"] = None
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.debug("spotify[%s]: playback poll failed", self.entity_id, exc_info=True)
            await asyncio.sleep(PLAYBACK_POLL_INTERVAL_SECONDS)

    async def get_state(self) -> dict[str, Any]:
        try:
            status = await self._redis.get(f"qecomp:integration:{self.entity_id}:status") or "DISCONNECTED"
        except Exception:
            status = "UNKNOWN"
        return {
            "entity_id": self.entity_id,
            "status": status,
            "authenticated": self._cached_state.get("authenticated", False),
            "now_playing": self._cached_state.get("now_playing"),
            "timestamp": time.time(),
        }


IntegrationClass = SpotifyIntegration
