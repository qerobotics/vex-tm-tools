"""Audit Log API (plan §12 "Audit Log" page / §8 `audit_log` table).

Thin, read-only router over `audit_log` — writes happen via
`backend.core.audit.log_action`, called from every mutating endpoint across
the other routers. This module only exposes the paginated/filterable list
view the Audit Log page (§12) needs: filters by user, action type, resource
type, and a created_at date range, ordered newest-first.

Gated on `settings:read` — same permission the Settings page's read-only
views use (`backend/routers/settings.py`'s `list_settings`/`list_api_keys`),
since the audit log is equivalent admin-only visibility into system state
rather than its own permission domain.
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.dependencies import get_db, require_permission
from backend.models.audit import AuditLog
from backend.schemas.audit import AuditLogRead

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


@router.get(
    "",
    response_model=list[AuditLogRead],
    dependencies=[Depends(require_permission("settings:read"))],
)
async def list_audit_log(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: str | None = Query(default=None, description="Filter by user_id (exact match)"),
    action: str | None = Query(default=None, description="Filter by action (exact match)"),
    resource_type: str | None = Query(default=None, description="Filter by resource_type (exact match)"),
    start_date: datetime | None = Query(default=None, description="Only rows with created_at >= this"),
    end_date: datetime | None = Query(default=None, description="Only rows with created_at <= this"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[AuditLog]:
    stmt = select(AuditLog)
    if user is not None:
        stmt = stmt.where(AuditLog.user_id == user)
    if action is not None:
        stmt = stmt.where(AuditLog.action == action)
    if resource_type is not None:
        stmt = stmt.where(AuditLog.resource_type == resource_type)
    if start_date is not None:
        stmt = stmt.where(AuditLog.created_at >= start_date)
    if end_date is not None:
        stmt = stmt.where(AuditLog.created_at <= end_date)

    stmt = stmt.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(stmt)
    return list(result.scalars().all())
