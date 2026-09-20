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

import logging
import time
from typing import Any
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.audit import log_action
from backend.core.dependencies import CurrentPrincipal, get_db, require_permission
from backend.core.redis import get_redis
from backend.models.automation import Automation, AutomationFolder, AutomationRun
from backend.modules.automation.engine import AutomationEngine, validate_automation_yaml
from backend.schemas.automation import (
    AutomationCreate,
    AutomationFolderCreate,
    AutomationFolderRead,
    AutomationFolderUpdate,
    AutomationRead,
    AutomationRunRead,
    AutomationUpdate,
    TriggerResponse,
    ValidateRequest,
    ValidateResponse,
)
from backend.schemas.events import EventBusMessage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/automations", tags=["automations"])


# ── Helpers ───────────────────────────────────────────────────────────────


async def _get_automation_or_404(session: AsyncSession, automation_id: UUID) -> Automation:
    result = await session.execute(select(Automation).where(Automation.id == automation_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Automation not found")
    return row


async def _get_folder_or_404(session: AsyncSession, folder_id: UUID) -> AutomationFolder:
    result = await session.execute(select(AutomationFolder).where(AutomationFolder.id == folder_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Automation folder not found")
    return row


def _json_safe(value: object) -> object:
    """`log_action`'s `changes=` column is JSONB — a raw `UUID` (e.g. from
    `folder_id`/`parent_id`) isn't JSON-serializable and would fail the
    audit insert's own commit, which then leaves the request's session in
    an unusable state for response serialization. Coerce to `str` before
    logging; `setattr()` onto the row still uses the original typed value."""
    return str(value) if isinstance(value, UUID) else value


async def _publish_config_change(redis_client: Any, resource_type: str, entity_id: str, action: str) -> None:
    """Publishes `config_change` (plan §5.8 point 6) so `AutomationEngine`'s
    `_config_change_listener` hot-reloads — mirrors `routers/integrations.py`
    and `routers/timers.py`'s identical helper. Without this, a
    create/update/delete here is invisible to the real trigger-matching path
    until the process restarts (`AutomationEngine.trigger()` re-reads fresh
    from Postgres and is unaffected, which is why "Test Run" masks this)."""
    msg = EventBusMessage(
        entity_id=entity_id,
        entity_tags=[],
        type="config_change",
        timestamp=time.time(),
        payload={"resource_type": resource_type, "entity_id": entity_id, "action": action},
    )
    try:
        await redis_client.publish("qecomp:config_change", msg.model_dump_json())
    except Exception:
        pass


def _get_engine(request: Request) -> AutomationEngine | None:
    """Best-effort accessor for the `AutomationEngine` singleton `main.py`
    wires onto `app.state` during the leader lifecycle. Returns `None` on a
    passive node / before startup instead of raising, so read-only CRUD
    routes still work everywhere (only `/trigger` actually needs it)."""
    return getattr(request.app.state, "automation_engine", None)


async def _proxy_trigger_to_leader(request: Request, leader: Any, automation_id: UUID) -> Response | None:
    """Passive-node request forwarding for `/trigger`, mirroring
    `routers/integrations.py`'s `_proxy_to_leader` (plan §3.1). The
    `AutomationEngine` only runs on the current leader pod; a passive pod
    that can't service this locally reads the leader's address from Redis
    and HTTP-proxies this exact request there, forwarding the caller's
    `Authorization`/`Cookie` headers so the leader's own permission check
    sees the same principal. Returns `None` if no leader address can
    currently be resolved, so the caller falls back to a plain 503."""
    leader_address = await leader.get_leader_address_async()
    if not leader_address:
        return None

    forward_headers: dict[str, str] = {"content-type": "application/json"}
    auth = request.headers.get("authorization")
    if auth:
        forward_headers["authorization"] = auth
    cookie = request.headers.get("cookie")
    if cookie:
        forward_headers["cookie"] = cookie

    url = f"http://{leader_address}/api/v1/automations/{automation_id}/trigger"
    body = await request.body()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, content=body, headers=forward_headers)
    except httpx.HTTPError:
        logger.exception("Failed to proxy automation trigger for %s to leader at %s", automation_id, leader_address)
        return None

    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers={"content-type": resp.headers.get("content-type", "application/json")},
    )


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
    redis_client: Any = Depends(get_redis),
    principal: CurrentPrincipal = Depends(require_permission("automations:edit")),
) -> AutomationFolderRead:
    row = AutomationFolder(**body.model_dump())
    session.add(row)
    await session.commit()
    await session.refresh(row)
    await log_action(
        session,
        principal.subject,
        "create",
        "automation_folder",
        str(row.id),
        changes=body.model_dump(mode="json"),
    )
    await _publish_config_change(redis_client, "automation_folder", str(row.id), "created")
    return row


@router.put(
    "/folders/{folder_id}",
    response_model=AutomationFolderRead,
)
async def update_folder(
    folder_id: UUID,
    body: AutomationFolderUpdate,
    session: AsyncSession = Depends(get_db),
    redis_client: Any = Depends(get_redis),
    principal: CurrentPrincipal = Depends(require_permission("automations:edit")),
) -> AutomationFolderRead:
    row = await _get_folder_or_404(session, folder_id)

    # `name` is NOT NULL — an explicit JSON `null` for it is treated the
    # same as "not provided" rather than failing at commit (matches
    # update_automation's rationale for the same pattern above).
    changed_fields: dict[str, object] = {}
    for field_name, value in body.model_dump(exclude_unset=True).items():
        if value is None and field_name == "name":
            continue
        setattr(row, field_name, value)
        changed_fields[field_name] = _json_safe(value)

    await session.commit()
    await session.refresh(row)
    await log_action(
        session, principal.subject, "update", "automation_folder", str(folder_id), changes=changed_fields
    )
    await _publish_config_change(redis_client, "automation_folder", str(folder_id), "updated")
    return row


@router.delete(
    "/folders/{folder_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_folder(
    folder_id: UUID,
    session: AsyncSession = Depends(get_db),
    redis_client: Any = Depends(get_redis),
    principal: CurrentPrincipal = Depends(require_permission("automations:edit")),
) -> None:
    row = await _get_folder_or_404(session, folder_id)
    deleted = {"name": row.name, "parent_id": str(row.parent_id) if row.parent_id else None}
    await session.delete(row)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete a folder that still contains automations or subfolders",
        ) from None
    await log_action(session, principal.subject, "delete", "automation_folder", str(folder_id), changes=deleted)
    await _publish_config_change(redis_client, "automation_folder", str(folder_id), "deleted")


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
    redis_client: Any = Depends(get_redis),
    principal: CurrentPrincipal = Depends(require_permission("automations:edit")),
) -> AutomationRead:
    valid, errors = validate_automation_yaml(body.trigger_yaml, body.condition_yaml, body.action_yaml)
    if not valid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"errors": errors})
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
    await _publish_config_change(redis_client, "automation", str(row.id), "created")
    return row


@router.put(
    "/{automation_id}",
    response_model=AutomationRead,
)
async def update_automation(
    automation_id: UUID,
    body: AutomationUpdate,
    session: AsyncSession = Depends(get_db),
    redis_client: Any = Depends(get_redis),
    principal: CurrentPrincipal = Depends(require_permission("automations:edit")),
) -> AutomationRead:
    row = await _get_automation_or_404(session, automation_id)

    # Every column AutomationUpdate can touch is nullable except `enabled`,
    # `alias`, `trigger_yaml`, `action_yaml` — an explicit JSON `null` for
    # one of those NOT-NULL fields would otherwise pass exclude_unset and
    # fail unhandled at commit, so treat it the same as "not provided"
    # (matches the same rationale in routers/timers.py's update_timer).
    updates = {
        field_name: value
        for field_name, value in body.model_dump(exclude_unset=True).items()
        if not (value is None and field_name in {"alias", "enabled", "trigger_yaml", "action_yaml"})
    }

    # Validate the *resulting* YAML (existing value for any field not
    # touched by this PUT) so a broken edit can't bypass the "Validate"
    # button and save silently — it would otherwise only surface later, at
    # execution time, as a confusing unrelated error.
    valid, errors = validate_automation_yaml(
        updates.get("trigger_yaml", row.trigger_yaml),
        updates.get("condition_yaml", row.condition_yaml),
        updates.get("action_yaml", row.action_yaml),
    )
    if not valid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"errors": errors})

    changed_fields: dict[str, object] = {}
    for field_name, value in updates.items():
        setattr(row, field_name, value)
        changed_fields[field_name] = _json_safe(value)

    await session.commit()
    await session.refresh(row)
    await log_action(
        session, principal.subject, "update", "automation", str(automation_id), changes=changed_fields
    )
    await _publish_config_change(redis_client, "automation", str(automation_id), "updated")
    return row


@router.delete(
    "/{automation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_automation(
    automation_id: UUID,
    session: AsyncSession = Depends(get_db),
    redis_client: Any = Depends(get_redis),
    principal: CurrentPrincipal = Depends(require_permission("automations:edit")),
) -> None:
    row = await _get_automation_or_404(session, automation_id)
    deleted = {"alias": row.alias, "folder_id": str(row.folder_id) if row.folder_id else None}
    await session.delete(row)
    await session.commit()
    await log_action(session, principal.subject, "delete", "automation", str(automation_id), changes=deleted)
    await _publish_config_change(redis_client, "automation", str(automation_id), "deleted")


# ── Test Run / execution history / validation ────────────────────────────


@router.post(
    "/{automation_id}/trigger",
    response_model=None,
)
async def trigger_automation(
    request: Request,
    automation_id: UUID,
    session: AsyncSession = Depends(get_db),
    principal: CurrentPrincipal = Depends(require_permission("automations:trigger")),
) -> TriggerResponse | Response:
    """The "Test Run" button (plan §12): fires the automation's action
    chain immediately, regardless of its trigger/condition.

    The `AutomationEngine` only runs on the current leader pod. A passive
    pod forwards this request to the leader instead of a bare 503 (mirrors
    `routers/integrations.py`'s `call_integration_service`) so a Stream
    Deck-style trigger behind a load balancer doesn't fail ~50% of the time
    (plan §3.1)."""
    row = await _get_automation_or_404(session, automation_id)  # 404 before touching the engine

    engine = _get_engine(request)
    if engine is None:
        leader = getattr(request.app.state, "leader", None)
        if leader is not None and not leader.is_leader():
            proxied = await _proxy_trigger_to_leader(request, leader, automation_id)
            if proxied is not None:
                return proxied
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AutomationEngine is not running on this node (not the current leader?)",
        )

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
    dependencies=[Depends(require_permission("settings:edit"))],
)
async def list_automation_runs(
    automation_id: UUID, session: AsyncSession = Depends(get_db)
) -> list[AutomationRunRead]:
    """Appendix A.7's per-automation execution history (also surfaced as one
    of the three debug views in Appendix A.11, which gates all three debug
    views — this one, Integration Debug Log, Live Event Bus — on
    `settings:edit`, not `automations:read`)."""
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
