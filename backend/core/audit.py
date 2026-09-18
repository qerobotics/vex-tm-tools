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

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.audit import AuditLog


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
    """
    import logging

    row = AuditLog(
        user_id=principal_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        changes=changes,
        ip_address=ip_address,
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
