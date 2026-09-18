"""Reusable scripts FastAPI router (plan §11 "Scripts" / §5.9).

Thin CRUD on the `scripts` table — same conventions as
`backend/routers/automations.py` (RBAC placeholder via
`backend.core.dependencies.require_permission`, no business logic here).
Scripts are called from automations via `script: <name>` action entries,
resolved by `AutomationEngine` at execution time (see
`backend/modules/automation/engine.py`) — this router never touches the
engine directly since script CRUD has no execution semantics of its own.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.audit import log_action
from backend.core.dependencies import CurrentPrincipal, get_db, require_permission
from backend.models.automation import Script
from backend.schemas.automation import ScriptCreate, ScriptRead, ScriptUpdate

router = APIRouter(prefix="/api/v1/scripts", tags=["scripts"])


async def _get_script_or_404(session: AsyncSession, script_id: UUID) -> Script:
    result = await session.execute(select(Script).where(Script.id == script_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Script not found")
    return row


@router.get("", response_model=list[ScriptRead], dependencies=[Depends(require_permission("automations:read"))])
async def list_scripts(session: AsyncSession = Depends(get_db)) -> list[ScriptRead]:
    result = await session.execute(select(Script).order_by(Script.name))
    return list(result.scalars().all())


@router.post(
    "",
    response_model=ScriptRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_script(
    body: ScriptCreate,
    session: AsyncSession = Depends(get_db),
    principal: CurrentPrincipal = Depends(require_permission("automations:edit")),
) -> ScriptRead:
    row = Script(**body.model_dump())
    session.add(row)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=f"Script {body.name!r} already exists"
        ) from None
    await session.refresh(row)
    await log_action(session, principal.subject, "create", "script", str(row.id), changes=body.model_dump())
    return row


@router.put(
    "/{script_id}",
    response_model=ScriptRead,
)
async def update_script(
    script_id: UUID,
    body: ScriptUpdate,
    session: AsyncSession = Depends(get_db),
    principal: CurrentPrincipal = Depends(require_permission("automations:edit")),
) -> ScriptRead:
    row = await _get_script_or_404(session, script_id)
    changed_fields: dict[str, object] = {}
    for field_name, value in body.model_dump(exclude_unset=True).items():
        if value is None and field_name in {"name", "action_yaml"}:
            continue
        setattr(row, field_name, value)
        changed_fields[field_name] = value
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=f"Script name {row.name!r} already in use"
        ) from None
    await session.refresh(row)
    await log_action(session, principal.subject, "update", "script", str(script_id), changes=changed_fields)
    return row


@router.delete(
    "/{script_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_script(
    script_id: UUID,
    session: AsyncSession = Depends(get_db),
    principal: CurrentPrincipal = Depends(require_permission("automations:edit")),
) -> None:
    row = await _get_script_or_404(session, script_id)
    deleted = {"name": row.name}
    await session.delete(row)
    await session.commit()
    await log_action(session, principal.subject, "delete", "script", str(script_id), changes=deleted)
