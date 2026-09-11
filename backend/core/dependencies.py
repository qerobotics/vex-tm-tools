"""Shared FastAPI `Depends()` utilities used across routers.

Per Appendix C.2, inter-router dependencies (auth/permission checks, common
query params, etc.) live here rather than being imported router-to-router.

Wave 3b implements the real RBAC dependency (plan §13 / Appendix B.7 / B.9):
`require_permission(permission)` accepts either a signed session cookie
(OIDC login or `admin_local`, see `routers/auth.py`) or a `Bearer qec_...`
API key (Appendix B.7). `admin_local` and any session/key holding the
special `"*"` permission bypass all checks.

Note on `backend/models/` import (deliberate, narrow exception to §C.2's
"`backend/core/` may import nothing in the backend" rule): RBAC enforcement
fundamentally requires reading `role_permissions` and `api_keys`, and §C.2
also says "inter-router dependencies go via shared `Depends()` utilities in
`backend/core/dependencies.py`" — the only place all routers can share this
logic without importing one another. Rather than duplicate DB queries in
every router (or introduce a router-to-router import, which §C.2 forbids
outright), this module imports the two specific ORM models it needs. No
other `backend/core/` module does this.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.db import check_db_connection, get_db  # noqa: F401
from backend.core.redis import check_redis_connection, get_redis  # noqa: F401
from backend.core.security import hash_api_key
from backend.core.sessions import SESSION_COOKIE_NAME, get_session, unsign_session_id
from backend.models.settings import ApiKey, RolePermission

logger = logging.getLogger(__name__)

#: Sentinel permission string meaning "all permissions" — used by
#: `admin_local` and by `qecomp-admin`'s seeded role_permissions rows so a
#: single DB row (rather than one row per permission) grants everything.
ALL_PERMISSIONS = "*"


class CurrentPrincipal:
    """The authenticated caller for the current request: either a human
    session (OIDC or `admin_local`) or an API key."""

    def __init__(
        self,
        *,
        subject: str,
        permissions: set[str],
        is_admin_local: bool = False,
        via_api_key: bool = False,
    ) -> None:
        self.subject = subject
        self.permissions = permissions
        self.is_admin_local = is_admin_local
        self.via_api_key = via_api_key

    def has_permission(self, permission: str) -> bool:
        if self.is_admin_local or ALL_PERMISSIONS in self.permissions:
            return True
        return permission in self.permissions


async def resolve_permissions_for_groups(
    session: AsyncSession, groups: list[str]
) -> list[str]:
    """Resolve a list of Authentik group names to the union of permissions
    mapped to them via `role_permissions` (plan §13). Used at OIDC login
    time (Appendix B.9: evaluated once, cached in the session, only
    re-evaluated on next login)."""
    if not groups:
        return []
    result = await session.execute(
        select(RolePermission.permission).where(RolePermission.authentik_group.in_(groups))
    )
    return sorted({row[0] for row in result.all()})


async def get_current_principal(
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis_client: Any = Depends(get_redis),
) -> CurrentPrincipal | None:
    """Best-effort resolution of the caller's identity from either a
    `Bearer qec_...` API key or the signed session cookie. Returns `None`
    if neither is present/valid — callers (e.g. `require_permission`) turn
    that into a 401/403 as appropriate."""
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        raw_key = auth_header[7:].strip()
        return await _principal_from_api_key(db, raw_key)

    cookie_value = request.cookies.get(SESSION_COOKIE_NAME)
    if cookie_value:
        session_id = unsign_session_id(cookie_value)
        if session_id is not None:
            data = await get_session(redis_client, session_id)
            if data is not None:
                permissions = set(data["permissions"])
                if data.get("is_admin_local"):
                    permissions.add(ALL_PERMISSIONS)
                return CurrentPrincipal(
                    subject=data["user_id"],
                    permissions=permissions,
                    is_admin_local=bool(data.get("is_admin_local")),
                )
    return None


#: Minimum interval between `api_keys.last_used_at` writes for the same
#: key. `get_current_principal` runs on nearly every REST route via
#: `require_permission()`, so writing+committing on literally every request
#: from a busy API-key client (e.g. an automation polling a service
#: endpoint) would turn a read-mostly auth check into DB write pressure
#: that scales with request volume rather than with how often "last used"
#: actually needs to be accurate for the Settings page's API Keys list.
_LAST_USED_UPDATE_INTERVAL_SECONDS = 60


async def _principal_from_api_key(db: AsyncSession, raw_key: str) -> CurrentPrincipal | None:
    if not raw_key:
        return None
    key_hash = hash_api_key(raw_key)
    result = await db.execute(select(ApiKey).where(ApiKey.key_hash == key_hash))
    row = result.scalar_one_or_none()
    if row is None or row.revoked:
        return None

    from datetime import datetime, timedelta, timezone

    # `api_keys.last_used_at` is a naive `TIMESTAMP` column (see
    # `backend.models.settings.ApiKey`) — asyncpg rejects a tz-aware value
    # against it ("can't subtract offset-naive and offset-aware
    # datetimes"), so strip tzinfo after computing the UTC instant.
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    stale = row.last_used_at is None or (now - row.last_used_at) >= timedelta(
        seconds=_LAST_USED_UPDATE_INTERVAL_SECONDS
    )
    if stale:
        try:
            row.last_used_at = now
            await db.commit()
        except Exception:
            logger.exception("Failed to update api_keys.last_used_at for key id=%s", row.id)
            await db.rollback()
    return CurrentPrincipal(
        subject=f"api_key:{row.name}",
        permissions=set(row.permissions or []),
        via_api_key=True,
    )


def require_permission(permission: str):
    """RBAC dependency factory (plan §13). Every route declares the exact
    permission string it needs; this returns a `Depends()`-compatible check
    that 401s if there's no valid session/API key and 403s if the caller
    lacks `permission`.

    `admin_local` (Appendix §3.9/§B.9) and any principal holding the `"*"`
    sentinel always pass, regardless of the specific permission requested.
    """

    async def _dependency(
        principal: CurrentPrincipal | None = Depends(get_current_principal),
    ) -> CurrentPrincipal:
        if principal is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )
        if not principal.has_permission(permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required permission: {permission!r}",
            )
        return principal

    return _dependency
