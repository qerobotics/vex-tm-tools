"""Async OBS integration client (plan §5.7 / §C.7.3).

**Deviation from plan §C.7.3's text, applied deliberately:** the plan
describes `obs-websocket-py` v1.x as "async-native... wraps `websockets`
internally". The actual installed library (`obs-websocket-py==1.0`) is, on
inspection of its source, a fully **synchronous** client: it uses the
`websocket-client` package (`websocket.WebSocket()`, blocking `.recv()`/
`.send()`) plus a background `threading.Thread` for receives, and
`obsws.call()` blocks the calling thread on a `threading.Event.wait()`
until a reply arrives or it times out.

Per plan §C.7.1 (non-negotiable: no blocking call may ever run directly on
the event loop thread), this integration therefore treats `obsws` exactly
like the synchronous `PyATEMMax` client in the `atem` integration: every
`obsws.connect()` / `.disconnect()` / `.call()` invocation is wrapped in
`asyncio.to_thread()`. The library's own `RecvThread` already satisfies the
"heartbeat/receive loop runs off the event loop" requirement.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

from obswebsocket import exceptions as obs_exceptions
from obswebsocket import obsws
from obswebsocket import requests as obs_requests

from backend.core.exceptions import IntegrationError
from backend.modules.integrations.base import Integration

logger = logging.getLogger(__name__)

DEFAULT_PORT = 4455  # obs-websocket protocol v5 default (OBS 28+); 4444 is legacy v4.
STATUS_KEY_TMPL = "qecomp:integration:{entity_id}:status"
SCENES_KEY_TMPL = "qecomp:integration:{entity_id}:scenes"


class ObsIntegration(Integration):
    def __init__(self, entity_id: str, config: dict[str, Any], redis: Any, db_pool: Any) -> None:
        super().__init__(entity_id, config, redis, db_pool)
        self._obs: obsws | None = None
        self._scene_list: list[str] = []
        self._current_scene: str | None = None

    async def setup(self) -> None:
        host = self.config.get("host")
        if not host:
            raise IntegrationError(f"obs[{self.entity_id}]: 'host' is required")
        port = int(self.config.get("port") or DEFAULT_PORT)
        password = self.config.get("password") or ""

        obs = obsws(host, port, password, legacy=False, timeout=10)
        try:
            await asyncio.to_thread(obs.connect)
        except Exception as exc:
            raise IntegrationError(f"obs[{self.entity_id}]: could not connect: {exc}") from exc
        self._obs = obs

        await self.refresh_scenes()

    async def teardown(self) -> None:
        try:
            if self._obs is not None:
                await asyncio.to_thread(self._obs.disconnect)
                self._obs = None
        except Exception:
            logger.exception("Error during obs teardown for %s", self.entity_id)

    # ── scene list (fetched live on setup(), cached in Redis; on-demand
    #    refresh supported for the router/UI to call) ────────────────
    async def refresh_scenes(self) -> list[str]:
        if self._obs is None:
            return []
        try:
            resp = await asyncio.to_thread(self._obs.call, obs_requests.GetSceneList())
            scenes = resp.datain.get("scenes", [])
            self._scene_list = [s.get("sceneName") for s in scenes if s.get("sceneName")]
            self._current_scene = resp.datain.get("currentProgramSceneName")
            with contextlib.suppress(Exception):
                await self._redis.set(SCENES_KEY_TMPL.format(entity_id=self.entity_id), ",".join(self._scene_list))
        except Exception:
            logger.exception("obs[%s]: failed to refresh scene list", self.entity_id)
        return list(self._scene_list)

    # ── services ─────────────────────────────────────────────────────
    async def call_service(self, service: str, data: dict[str, Any]) -> dict[str, Any]:
        data = data or {}
        if service == "switch_scene":
            return await self._svc_switch_scene(data)
        if service == "trigger_hotkey":
            return await self._svc_trigger_hotkey(data)
        raise ValueError(f"Unknown service '{service}' for obs integration")

    async def _svc_switch_scene(self, data: dict[str, Any]) -> dict[str, Any]:
        scene_name = data.get("scene_name")
        if not scene_name:
            raise ValueError("switch_scene requires 'scene_name'")
        if self._obs is None:
            raise IntegrationError(f"obs[{self.entity_id}]: not connected")
        try:
            await asyncio.to_thread(self._obs.call, obs_requests.SetCurrentProgramScene(sceneName=scene_name))
        except (obs_exceptions.MessageTimeout, obs_exceptions.ConnectionFailure) as exc:
            await self._on_connection_error()
            raise IntegrationError(f"obs[{self.entity_id}]: switch_scene failed: {exc}") from exc
        self._current_scene = scene_name
        return {"ok": True, "scene_name": scene_name}

    async def _svc_trigger_hotkey(self, data: dict[str, Any]) -> dict[str, Any]:
        hotkey_name = data.get("hotkey_name")
        if not hotkey_name:
            raise ValueError("trigger_hotkey requires 'hotkey_name'")
        if self._obs is None:
            raise IntegrationError(f"obs[{self.entity_id}]: not connected")
        try:
            await asyncio.to_thread(self._obs.call, obs_requests.TriggerHotkeyByName(hotkeyName=hotkey_name))
        except (obs_exceptions.MessageTimeout, obs_exceptions.ConnectionFailure) as exc:
            await self._on_connection_error()
            raise IntegrationError(f"obs[{self.entity_id}]: trigger_hotkey failed: {exc}") from exc
        return {"ok": True, "hotkey_name": hotkey_name}

    async def _on_connection_error(self) -> None:
        # obs-websocket-py raises websocket-client's ConnectionClosedException
        # (wrapped here as MessageTimeout/ConnectionFailure) when the server
        # disconnects — mark DEGRADED and best-effort reconnect in the
        # background; the loader's own retry loop covers the case where this
        # never recovers.
        with contextlib.suppress(Exception):
            await self._redis.set(STATUS_KEY_TMPL.format(entity_id=self.entity_id), "DEGRADED")
        if self._obs is not None:
            try:
                await asyncio.to_thread(self._obs.reconnect)
                await self.refresh_scenes()
            except Exception:
                logger.warning("obs[%s]: reconnect after connection error failed", self.entity_id)
                return
            # Reconnect succeeded — clear the DEGRADED status so the loader's
            # CONNECTED status (set when setup() first ran) isn't left stuck.
            with contextlib.suppress(Exception):
                await self._redis.set(STATUS_KEY_TMPL.format(entity_id=self.entity_id), "CONNECTED")

    async def get_state(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "connected": self._obs is not None,
            "current_scene": self._current_scene,
            "scenes": list(self._scene_list),
        }


IntegrationClass = ObsIntegration
