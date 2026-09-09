"""Async ZerOS lighting integration client (plan §5.6 / §C.7.3).

OSC over UDP via `python-osc`. `SimpleUDPClient.send_message` is a
synchronous, fire-and-forget UDP send — wrapped in `asyncio.to_thread()`
per §C.7.3 so it never risks blocking the event loop.

Preset name -> number resolution reads the `zeros_presets` table via raw
SQL (no ORM import — per §C.2, integration clients must not import
`backend/models/`). `db_pool` is expected to be an async session factory
(the same shape as `backend.core.db.async_session_factory`).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from pythonosc.udp_client import SimpleUDPClient
from sqlalchemy import text

from backend.core.exceptions import IntegrationError
from backend.modules.integrations.base import Integration

logger = logging.getLogger(__name__)

DEFAULT_PORT = 8000


class ZerosIntegration(Integration):
    def __init__(self, entity_id: str, config: dict[str, Any], redis: Any, db_pool: Any) -> None:
        super().__init__(entity_id, config, redis, db_pool)
        self._client: SimpleUDPClient | None = None
        self._last_preset: int | None = None

    async def setup(self) -> None:
        ip = self.config.get("ip")
        if not ip:
            raise IntegrationError(f"zeros[{self.entity_id}]: 'ip' is required")
        port = int(self.config.get("port") or DEFAULT_PORT)
        # SimpleUDPClient's constructor just opens a socket (cheap, but
        # wrapped for consistency with the async-discipline rule that no
        # PyATEMMax/python-osc/obs-websocket-py call happens directly on
        # the event loop thread).
        self._client = await asyncio.to_thread(SimpleUDPClient, ip, port)

    async def teardown(self) -> None:
        try:
            # SimpleUDPClient has no explicit close()/disconnect() — the
            # underlying socket is garbage-collected once we drop the
            # reference. Nothing here can block or raise meaningfully, but
            # keep the try/except per §C.7.4's "never raise" rule anyway.
            self._client = None
        except Exception:
            logger.exception("Error during zeros teardown for %s", self.entity_id)

    async def call_service(self, service: str, data: dict[str, Any]) -> dict[str, Any]:
        data = data or {}
        if service != "set_preset":
            raise ValueError(f"Unknown service '{service}' for zeros integration")
        if self._client is None:
            raise IntegrationError(f"zeros[{self.entity_id}]: not connected")

        preset_number = data.get("preset_id")
        if preset_number is None:
            preset_name = data.get("preset_name")
            if not preset_name:
                raise ValueError("set_preset requires 'preset_id' or 'preset_name'")
            preset_number = await self._resolve_preset_name(preset_name)
            if preset_number is None:
                raise ValueError(f"Unknown ZerOS preset name '{preset_name}'")

        preset_number = int(preset_number)
        address = f"/zeros/playback/go/{preset_number}"
        await asyncio.to_thread(self._client.send_message, address, None)
        self._last_preset = preset_number
        return {"ok": True, "preset_number": preset_number, "address": address}

    async def _resolve_preset_name(self, preset_name: str) -> int | None:
        if self._db_pool is None:
            raise IntegrationError(f"zeros[{self.entity_id}]: no database access configured")
        async with self._db_pool() as session:
            row = (
                await session.execute(
                    text("SELECT id FROM integration_instances WHERE entity_id = :entity_id"),
                    {"entity_id": self.entity_id},
                )
            ).first()
            if row is None:
                return None
            integration_id = row[0]
            preset_row = (
                await session.execute(
                    text(
                        "SELECT preset_number FROM zeros_presets "
                        "WHERE integration_id = :integration_id AND preset_name = :preset_name"
                    ),
                    {"integration_id": integration_id, "preset_name": preset_name},
                )
            ).first()
            return preset_row[0] if preset_row else None

    async def get_state(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "connected": self._client is not None,
            "last_preset": self._last_preset,
        }


IntegrationClass = ZerosIntegration
