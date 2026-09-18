"""ntfy.sh-compatible push notification client (Appendix A.8).

Reads `server_url`/`topic`/`enabled` from the `notifications` row of the
`system_settings` table (Settings page -> Notifications section) and, when
enabled and configured, POSTs to the ntfy server's simple HTTP API
(`POST {server_url}/{topic}`, body = message, `Title`/`Priority` headers).

Per Appendix C.2, `backend/core/` may only depend on stdlib + third-party
packages — it must not import from `backend/models/`. Rather than import
`backend.models.settings.SystemSetting` (the narrow exception
`backend/core/dependencies.py` documents for RBAC), this reads the
`system_settings` row via a raw SQL `SELECT` against the shared session
factory, keeping this module inside the stdlib+third-party-only boundary.

`send_ntfy_notification()` never raises — a notification failure (ntfy
unreachable, DB unreachable, bad config, etc.) must never crash whatever
event triggered it (leader failover, integration DEGRADED, automation
retry-exhaustion, video processing failure).
"""
from __future__ import annotations

import logging
from typing import Any

import httpx
from sqlalchemy import text

from backend.core.db import async_session_factory

logger = logging.getLogger(__name__)

_SETTINGS_KEY = "notifications"
_REQUEST_TIMEOUT_SECONDS = 5.0


async def _read_notification_settings() -> dict[str, Any]:
    try:
        async with async_session_factory() as session:
            result = await session.execute(
                text("SELECT value FROM system_settings WHERE key = :key"),
                {"key": _SETTINGS_KEY},
            )
            row = result.first()
    except Exception:
        logger.exception("Failed to read '%s' system_settings row", _SETTINGS_KEY)
        return {}
    if row is None or not isinstance(row[0], dict):
        return {}
    return row[0]


async def send_ntfy_notification(title: str, message: str, priority: str = "default") -> None:
    """Best-effort push notification via a self-hosted ntfy server.

    No-ops silently if notifications are disabled, or `server_url`/`topic`
    are unset. Never raises.
    """
    try:
        config = await _read_notification_settings()
        if not config.get("enabled"):
            return
        server_url = str(config.get("server_url") or "").rstrip("/")
        topic = str(config.get("topic") or "")
        if not server_url or not topic:
            return

        url = f"{server_url}/{topic}"
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS) as client:
            await client.post(
                url,
                content=message.encode("utf-8"),
                headers={"Title": title, "Priority": priority},
            )
    except Exception:
        logger.exception("Failed to send ntfy notification (title=%r)", title)
