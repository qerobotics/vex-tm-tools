"""Async ATEM integration client (plan §5.5 / §C.7.3).

`PyATEMMax` is a **synchronous** library. Per §C.7.3:
- Every `PyATEMMax` call is wrapped in `asyncio.to_thread()` — never called
  directly from a coroutine.
- The connection heartbeat/receive loop (which `PyATEMMax.connect()` already
  spins up internally as its own `threading.Thread`s) is started in
  `setup()` and joined (via `disconnect()`, itself wrapped in
  `asyncio.to_thread()`) in `teardown()`.
- Cross-thread signalling uses `asyncio.Event`, set from the ATEM library's
  callback thread via `loop.call_soon_threadsafe(event.set)` — never
  `threading.Event.wait()`.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

import PyATEMMax

from backend.core.exceptions import IntegrationError
from backend.modules.integrations.base import Integration

logger = logging.getLogger(__name__)

PROGRAM_ME = 0  # Mix Effect 1
CONNECT_TIMEOUT_SECONDS = 5.0


class AtemIntegration(Integration):
    def __init__(self, entity_id: str, config: dict[str, Any], redis: Any, db_pool: Any) -> None:
        super().__init__(entity_id, config, redis, db_pool)
        self._atem: PyATEMMax.ATEMMax | None = None
        self._connected_event: asyncio.Event = asyncio.Event()
        self._loop: asyncio.AbstractEventLoop | None = None

    async def setup(self) -> None:
        ip = self.config.get("ip")
        if not ip:
            raise IntegrationError(f"atem[{self.entity_id}]: 'ip' is required")

        self._loop = asyncio.get_running_loop()
        self._connected_event = asyncio.Event()
        self._atem = PyATEMMax.ATEMMax()
        self._atem.registerEvent(self._atem.atem.events.connect, self._on_connect)
        self._atem.registerEvent(self._atem.atem.events.disconnect, self._on_disconnect)

        await asyncio.to_thread(self._atem.connect, ip)
        connected = await asyncio.to_thread(
            self._atem.waitForConnection, False, CONNECT_TIMEOUT_SECONDS, True
        )
        if not connected:
            with contextlib.suppress(Exception):
                await asyncio.to_thread(self._atem.disconnect)
            self._atem = None
            raise IntegrationError(f"atem[{self.entity_id}]: could not connect to switcher at {ip}")

    async def teardown(self) -> None:
        try:
            if self._atem is not None:
                await asyncio.to_thread(self._atem.disconnect)
                self._atem = None
        except Exception:
            logger.exception("Error during atem teardown for %s", self.entity_id)

    # ── thread -> event loop signalling ──────────────────────────────
    def _on_connect(self, _params: dict[str, Any]) -> None:
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._connected_event.set)

    def _on_disconnect(self, _params: dict[str, Any]) -> None:
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._connected_event.clear)

    # ── services ─────────────────────────────────────────────────────
    async def call_service(self, service: str, data: dict[str, Any]) -> dict[str, Any]:
        data = data or {}
        if service not in ("switch_input", "set_preview"):
            raise ValueError(f"Unknown service '{service}' for atem integration")
        if self._atem is None:
            raise IntegrationError(f"atem[{self.entity_id}]: not connected")
        try:
            input_index = int(data["input_index"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("'input_index' is required and must be an integer") from exc

        if service == "switch_input":
            await asyncio.to_thread(self._atem.setProgramInputVideoSource, PROGRAM_ME, input_index)
        else:
            await asyncio.to_thread(self._atem.setPreviewInputVideoSource, PROGRAM_ME, input_index)
        return {"ok": True, "input_index": input_index}

    async def get_state(self) -> dict[str, Any]:
        try:
            connected = bool(self._atem.connected) if self._atem is not None else False
        except Exception:
            connected = False
        program_input = None
        preview_input = None
        try:
            if self._atem is not None:
                program_input = self._atem.programInput[PROGRAM_ME].videoSource
                preview_input = self._atem.previewInput[PROGRAM_ME].videoSource
        except Exception:
            pass
        return {
            "entity_id": self.entity_id,
            "connected": connected,
            "program_input": program_input,
            "preview_input": preview_input,
        }


IntegrationClass = AtemIntegration
