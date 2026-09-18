"""Automations + automation-folders FastAPI router (plan §11 "Automations").

Per Appendix C.5 rule 6, routers are stateless: every handler completes
within one request/response cycle and never spawns background asyncio
tasks — the long-running `AutomationEngine` (event-bus subscription, hot
reload) is started once by `main.py`'s lifespan and reached here via
`request.app.state.automation_engine`, mirroring the exact pattern
`backend/routers/timers.py` uses for `TimerManager`. This module is thin
per plan §C.2: it validates input, does simple CRUD via the DB session, and
delegates to `AutomationEngine` for anything execution-related (trigger /
validate) — no business logic lives here.

RBAC (plan §13) uses the shared `require_permission` placeholder from
`backend/core/dependencies.py` (same pattern as `backend/routers/teams.py`)
— every route below already passes the exact permission string from plan
§11's table, so Wave 3b (Routers/WS/Auth) can swap that function's body for
a real session/JWT/API-key check without touching any route signature here.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.audit import log_action
from backend.core.dependencies import CurrentPrincipal, get_db, require_permission
from backend.models.automation import Automation, AutomationFolder, AutomationRun
from backend.modules.automation.engine import AutomationEngine, validate_automation_yaml
from backend.schemas.automation import (
    AutomationCreate,
    AutomationFolderCreate,
    AutomationFolderRead,
    AutomationRead,
    AutomationRunRead,
    AutomationUpdate,
    TriggerResponse,
    ValidateRequest,
    ValidateResponse,
)

router = APIRouter(prefix="/api/v1/automations", tags=["automations"])


# ── Helpers ───────────────────────────────────────────────────────────────


async def _get_automation_or_404(session: AsyncSession, automation_id: UUID) -> Automation:
    result = await session.execute(select(Automation).where(Automation.id == automation_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Automation not found")
    return row


def _get_engine(request: Request) -> AutomationEngine | None:
    """Best-effort accessor for the `AutomationEngine` singleton `main.py`
    wires onto `app.state` during the leader lifecycle. Returns `None` on a
    passive node / before startup instead of raising, so read-only CRUD
    routes still work everywhere (only `/trigger` actually needs it)."""
    return getattr(request.app.state, "automation_engine", None)


def _require_engine(request: Request) -> AutomationEngine:
    engine = _get_engine(request)
    if engine is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AutomationEngine is not running on this node (not the current leader?)",
        )
    return engine


# ── Folders (plan §11 "Automations" — automations:read/edit) ────────────


@router.get(
    "/folders",
    response_model=list[AutomationFolderRead],
    dependencies=[Depends(require_permission("automations:read"))],
)
async def list_folders(session: AsyncSession = Depends(get_db)) -> list[AutomationFolderRead]:
    result = await session.execute(select(AutomationFolder).order_by(AutomationFolder.name))
    return list(result.scalars().all())


@router.post(
    "/folders",
    response_model=AutomationFolderRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_folder(
    body: AutomationFolderCreate,
    session: AsyncSession = Depends(get_db),
    principal: CurrentPrincipal = Depends(require_permission("automations:edit")),
) -> AutomationFolderRead:
    row = AutomationFolder(**body.model_dump())
    session.add(row)
    await session.commit()
    await session.refresh(row)
    await log_action(
        session, principal.subject, "create", "automation_folder", str(row.id), changes=body.model_dump()
    )
    return row


# ── Automations CRUD (plan §11 "Automations") ────────────────────────────


@router.get(
    "",
    response_model=list[AutomationRead],
    dependencies=[Depends(require_permission("automations:read"))],
)
async def list_automations(session: AsyncSession = Depends(get_db)) -> list[AutomationRead]:
    result = await session.execute(select(Automation).order_by(Automation.alias))
    return list(result.scalars().all())


@router.post(
    "",
    response_model=AutomationRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_automation(
    body: AutomationCreate,
    session: AsyncSession = Depends(get_db),
    principal: CurrentPrincipal = Depends(require_permission("automations:edit")),
) -> AutomationRead:
    row = Automation(**body.model_dump())
    session.add(row)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not create automation (check folder_id references an existing folder)",
        ) from None
    await session.refresh(row)
    await log_action(
        session, principal.subject, "create", "automation", str(row.id), changes=body.model_dump(mode="json")
    )
    return row


@router.put(
    "/{automation_id}",
    response_model=AutomationRead,
)
async def update_automation(
    automation_id: UUID,
    body: AutomationUpdate,
    session: AsyncSession = Depends(get_db),
    principal: CurrentPrincipal = Depends(require_permission("automations:edit")),
) -> AutomationRead:
    row = await _get_automation_or_404(session, automation_id)

    # Every column AutomationUpdate can touch is nullable except `enabled`,
    # `alias`, `trigger_yaml`, `action_yaml` — an explicit JSON `null` for
    # one of those NOT-NULL fields would otherwise pass exclude_unset and
    # fail unhandled at commit, so treat it the same as "not provided"
    # (matches the same rationale in routers/timers.py's update_timer).
    changed_fields: dict[str, object] = {}
    for field_name, value in body.model_dump(exclude_unset=True).items():
        if value is None and field_name in {"alias", "enabled", "trigger_yaml", "action_yaml"}:
            continue
        setattr(row, field_name, value)
        changed_fields[field_name] = value

    await session.commit()
    await session.refresh(row)
    await log_action(
        session, principal.subject, "update", "automation", str(automation_id), changes=changed_fields
    )
    return row


@router.delete(
    "/{automation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_automation(
    automation_id: UUID,
    session: AsyncSession = Depends(get_db),
    principal: CurrentPrincipal = Depends(require_permission("automations:edit")),
) -> None:
    row = await _get_automation_or_404(session, automation_id)
    deleted = {"alias": row.alias, "folder_id": str(row.folder_id) if row.folder_id else None}
    await session.delete(row)
    await session.commit()
    await log_action(session, principal.subject, "delete", "automation", str(automation_id), changes=deleted)


# ── Test Run / execution history / validation ────────────────────────────


@router.post(
    "/{automation_id}/trigger",
    response_model=TriggerResponse,
)
async def trigger_automation(
    automation_id: UUID,
    session: AsyncSession = Depends(get_db),
    engine: AutomationEngine = Depends(_require_engine),
    principal: CurrentPrincipal = Depends(require_permission("automations:trigger")),
) -> TriggerResponse:
    """The "Test Run" button (plan §12): fires the automation's action
    chain immediately, regardless of its trigger/condition."""
    row = await _get_automation_or_404(session, automation_id)  # 404 before touching the engine
    try:
        result = await engine.trigger(automation_id, {})
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    await log_action(
        session, principal.subject, "trigger", "automation", str(automation_id), changes={"alias": row.alias}
    )
    return TriggerResponse(**result)


@router.get(
    "/{automation_id}/runs",
    response_model=list[AutomationRunRead],
    dependencies=[Depends(require_permission("automations:read"))],
)
async def list_automation_runs(
    automation_id: UUID, session: AsyncSession = Depends(get_db)
) -> list[AutomationRunRead]:
    """Appendix A.7's per-automation execution history (also surfaced as one
    of the three debug views in Appendix A.11)."""
    await _get_automation_or_404(session, automation_id)
    result = await session.execute(
        select(AutomationRun)
        .where(AutomationRun.automation_id == automation_id)
        .order_by(AutomationRun.triggered_at.desc())
        .limit(100)
    )
    return list(result.scalars().all())


@router.post(
    "/validate",
    response_model=ValidateResponse,
    dependencies=[Depends(require_permission("automations:edit"))],
)
async def validate_automation(body: ValidateRequest) -> ValidateResponse:
    """Appendix A.7's "Validate" button: YAML + Jinja2 syntax check only —
    never executes any service call."""
    valid, errors = validate_automation_yaml(body.trigger_yaml, body.condition_yaml, body.action_yaml)
    return ValidateResponse(valid=valid, errors=errors)
