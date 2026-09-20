"""Shared audit-logging helper (plan §8 `audit_log` table / §17 verification
checklist: "All create/update/delete operations appear in audit log with
user, timestamp, before/after.").

Every router that mutates state calls `log_action(...)` right after a
successful `commit()` so the audit trail reflects only changes that actually
persisted. This module deliberately contains no FastAPI/router-specific
imports (per §C.2, `backend/core/` is the shared-utility layer every router
may depend on) — just the one helper and the DB session it's given.
"""
from __future__ import annotations

from contextvars import ContextVar
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.audit import AuditLog

#: Set by `backend.core.request_context`'s ASGI middleware at the top of
#: every request so `log_action()` can fill in `ip_address` without every
#: one of its ~26 call sites across `backend/routers/*.py` needing to accept
#: a `Request` and thread it through — several (folder/script/team CRUD
#: handlers) don't currently take one at all. Previously `ip_address` was a
#: real column that no call site ever populated, including ones that already
#: had a `Request` in scope, leaving it permanently NULL.
current_request_ip: ContextVar[str | None] = ContextVar("current_request_ip", default=None)


async def log_action(
    session: AsyncSession,
    principal_id: str | None,
    action: str,
    resource_type: str,
    resource_id: str,
    changes: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> None:
    """Inserts one `audit_log` row and commits it.

    Uses the caller's passed-in session (same request-scoped session the
    mutation itself just committed on, matching this codebase's convention
    of one session per request via `Depends(get_db)`). A failure to write
    the audit row is logged but never raised — an audit-logging bug must
    never roll back or fail the mutation it's describing, which has already
    committed by the time this is called.

    `ip_address` defaults to the current request's client address (set by
    the ASGI middleware in `backend.core.request_context`) when the caller
    doesn't pass one explicitly.
    """
    import logging

    row = AuditLog(
        user_id=principal_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        changes=changes,
        ip_address=ip_address if ip_address is not None else current_request_ip.get(),
    )
    session.add(row)
    try:
        await session.commit()
    except Exception:
        logging.getLogger(__name__).exception(
            "Failed to write audit_log row (action=%s resource_type=%s resource_id=%s)",
            action,
            resource_type,
            resource_id,
        )
        await session.rollback()
