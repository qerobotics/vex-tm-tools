"""Server-side session storage + signed session cookie helpers (plan
Appendix B.1 / B.9).

Per Appendix B.1: "Session middleware: `itsdangerous` for signed cookies +
Redis for session store. Cookie contains a signed session ID; session data
(user info, groups, permissions) stored in Redis hash at
`qecomp:session:<id>` with 24h TTL."

Per Appendix B.9: groups/permissions are evaluated once, at login time, and
cached in the session; they are only re-evaluated on the next login. Force
logout is just deleting the session key from Redis.

This lives in `backend/core/` (not `routers/auth.py`) so that
`backend/core/dependencies.py`'s `require_permission()` — used by every
router — can read the current session without importing `routers/auth.py`
(routers must not import other routers, per Appendix C.2, and dependency
helpers shared across routers live in `backend/core/`).
"""
from __future__ import annotations

import json
import secrets
import time
from typing import Any

from itsdangerous import BadSignature, URLSafeSerializer

from backend.core.settings import settings

SESSION_COOKIE_NAME = "qecomp_session"
SESSION_KEY_TMPL = "qecomp:session:{session_id}"
SESSION_TTL_SECONDS = 24 * 60 * 60  # 24h, per Appendix B.1/B.9

_ADMIN_LOCAL_USER_ID = "admin_local"


def _serializer() -> URLSafeSerializer:
    return URLSafeSerializer(settings.SECRET_KEY, salt="qecomp-session-cookie")


def sign_session_id(session_id: str) -> str:
    """Sign a session id for use as the cookie value."""
    return _serializer().dumps(session_id)


def unsign_session_id(cookie_value: str) -> str | None:
    """Recover a session id from a signed cookie value. Returns `None` if the
    signature is invalid/tampered rather than raising, since this is called
    on every request with an untrusted cookie."""
    try:
        return _serializer().loads(cookie_value)
    except BadSignature:
        return None


def _session_key(session_id: str) -> str:
    return SESSION_KEY_TMPL.format(session_id=session_id)


async def create_session(
    redis_client: Any,
    *,
    user_id: str,
    display_name: str,
    groups: list[str],
    permissions: list[str],
    is_admin_local: bool = False,
) -> tuple[str, str]:
    """Create a new server-side session in Redis and return
    `(session_id, signed_cookie_value)`.

    Per Appendix B.9, `permissions` must already be the fully-resolved set
    for `groups` at login time — this function does not itself compute
    group -> permission mappings (see
    `backend.core.dependencies.resolve_permissions_for_groups`).
    """
    session_id = secrets.token_urlsafe(32)
    data = {
        "user_id": user_id,
        "display_name": display_name,
        "groups": json.dumps(groups),
        "permissions": json.dumps(permissions),
        "is_admin_local": "1" if is_admin_local else "0",
        "created_at": str(time.time()),
    }
    await redis_client.hset(_session_key(session_id), mapping=data)
    await redis_client.expire(_session_key(session_id), SESSION_TTL_SECONDS)
    return session_id, sign_session_id(session_id)


async def get_session(redis_client: Any, session_id: str) -> dict[str, Any] | None:
    """Fetch session data for `session_id`. Returns `None` if the session
    doesn't exist (expired, never existed, or force-logged-out)."""
    raw = await redis_client.hgetall(_session_key(session_id))
    if not raw:
        return None
    try:
        groups = json.loads(raw.get("groups", "[]"))
        permissions = json.loads(raw.get("permissions", "[]"))
    except (TypeError, ValueError):
        groups, permissions = [], []
    return {
        "session_id": session_id,
        "user_id": raw.get("user_id", ""),
        "display_name": raw.get("display_name", raw.get("user_id", "")),
        "groups": groups,
        "permissions": permissions,
        "is_admin_local": raw.get("is_admin_local") == "1",
    }


async def delete_session(redis_client: Any, session_id: str) -> None:
    """Delete a session immediately (logout, or admin-triggered force
    logout per Appendix B.9)."""
    await redis_client.delete(_session_key(session_id))


async def delete_sessions_for_user(redis_client: Any, user_id: str) -> int:
    """Force-logout every session belonging to `user_id` (Users page "force
    logout", plan Appendix B.9). Scans the `qecomp:session:*` keyspace since
    sessions aren't indexed by user_id — acceptable for the expected session
    volume of a single-event control app."""
    deleted = 0
    async for key in redis_client.scan_iter(match=SESSION_KEY_TMPL.format(session_id="*")):
        owner = await redis_client.hget(key, "user_id")
        if owner == user_id:
            await redis_client.delete(key)
            deleted += 1
    return deleted
