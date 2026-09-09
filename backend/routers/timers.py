"""Timer-Teleprompter FastAPI router (plan §11 "Timers" + "Cues").

Per Appendix C.5 rule 6, routers are stateless: every handler completes
within one request/response cycle and never spawns background asyncio
tasks — the long-running `TimerManager` (tick loops, pub/sub listeners) is
started once by `main.py`'s lifespan and reached here via
`request.app.state.timer_manager`. This module is thin per plan §C.2: it
validates input, calls `TimerManager` / does simple CRUD via the DB session,
and returns a response — no business logic is embedded here.

RBAC (plan §13) is NOT implemented by this wave. Wave 3 owns the real
`require_permission` dependency (see `backend/core/dependencies.py`'s
documented extension point). `_require_permission()` below is a clearly
structured placeholder `Depends()` factory: every route already calls it
with the exact permission string from plan §11's table, so Wave 3 can swap
its body for a real session/JWT/API-key check without touching any route
signature.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.db import get_db
from backend.core.redis import get_redis
from backend.core.security import generate_prompter_token
from backend.models.timer import PrompterCue, TimerInstance
from backend.modules.timer.manager import TimerManager
from backend.schemas.events import EventBusMessage
from backend.schemas.timer import (
    PrompterCueCreate,
    PrompterCueRead,
    PrompterCueUpdate,
    TimerInstanceCreate,
    TimerInstanceRead,
    TimerInstanceUpdate,
)

import secrets
import time

router = APIRouter(prefix="/api/v1/timers", tags=["timers"])


# ── Placeholder RBAC extension point (Wave 3 replaces this) ─────────────


def _require_permission(permission: str):
    """Returns a `Depends()`-compatible no-op check for `permission`.

    TODO(Wave 3 / RBAC, plan §13): replace the body of `_check` with a real
    session/JWT/API-key permission check (see
    `backend/core/dependencies.py`'s documented extension point). Every
    route below already passes the exact permission string required by plan
    §11's API table, so swapping this implementation is the only change
    needed here.
    """

    async def _check() -> None:
        return None

    return Depends(_check)


# ── Helpers ───────────────────────────────────────────────────────────────


async def get_timer_or_404(session: AsyncSession, entity_id: str) -> TimerInstance:
    result = await session.execute(
        select(TimerInstance).where(TimerInstance.entity_id == entity_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Timer instance not found")
    return row


def _to_read_schema(row: TimerInstance) -> TimerInstanceRead:
    read = TimerInstanceRead.model_validate(row)
    read.prompter_token = generate_prompter_token(row.entity_id, row.token_nonce)
    return read


async def _publish_config_change(
    redis_client: Any, entity_id: str, action: str, tags: list[str]
) -> None:
    """Publishes a `config_change` event (plan §C.4) so the leader's
    `TimerManager.reload()` (via its `qecomp:config_change` subscription)
    and any other interested module pick up the change without a restart."""
    msg = EventBusMessage(
        entity_id=entity_id,
        entity_tags=tags,
        type="config_change",
        timestamp=time.time(),
        payload={"resource_type": "timer_instance", "entity_id": entity_id, "action": action},
    )
    try:
        await redis_client.publish("qecomp:config_change", msg.model_dump_json())
    except Exception:
        # Config-change notification is best-effort; the DB write already
        # succeeded and a future reload()/restart will pick it up.
        pass


def _get_timer_manager(request: Request) -> TimerManager | None:
    """Best-effort accessor for the `TimerManager` singleton main.py wires
    onto `app.state` during the leader lifecycle (see plan §C.2's extension
    point in `backend/main.py`). Returns `None` on a passive node / before
    startup instead of raising, so read-only routes still work everywhere."""
    return getattr(request.app.state, "timer_manager", None)


def _require_timer_manager(request: Request) -> TimerManager:
    manager = _get_timer_manager(request)
    if manager is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="TimerManager is not running on this node (not the current leader?)",
        )
    return manager


# ── Timer instance CRUD (plan §11 "Timers") ──────────────────────────────


@router.get("", response_model=list[TimerInstanceRead], dependencies=[_require_permission("timers:read")])
async def list_timers(session: AsyncSession = Depends(get_db)) -> list[TimerInstanceRead]:
    result = await session.execute(select(TimerInstance).order_by(TimerInstance.display_name))
    return [_to_read_schema(row) for row in result.scalars().all()]


@router.post(
    "",
    response_model=TimerInstanceRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[_require_permission("timers:edit")],
)
async def create_timer(
    body: TimerInstanceCreate,
    session: AsyncSession = Depends(get_db),
    redis_client: Any = Depends(get_redis),
) -> TimerInstanceRead:
    existing = await session.execute(
        select(TimerInstance).where(TimerInstance.entity_id == body.entity_id)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Timer instance {body.entity_id!r} already exists",
        )

    row = TimerInstance(**body.model_dump())
    session.add(row)
    try:
        await session.commit()
    except IntegrityError:
        # The pre-check above and this insert aren't atomic, so two
        # concurrent creates with the same entity_id can both pass the
        # check; the DB's unique constraint is the real guard, and a
        # violation here means the same race the pre-check was meant to
        # catch — surface it as the same 409 rather than an unhandled 500.
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Timer instance {body.entity_id!r} already exists",
        ) from None
    await session.refresh(row)

    await _publish_config_change(redis_client, row.entity_id, "created", row.tags)
    return _to_read_schema(row)


@router.put(
    "/{entity_id}",
    response_model=TimerInstanceRead,
    dependencies=[_require_permission("timers:edit")],
)
async def update_timer(
    entity_id: str,
    body: TimerInstanceUpdate,
    session: AsyncSession = Depends(get_db),
    redis_client: Any = Depends(get_redis),
) -> TimerInstanceRead:
    row = await get_timer_or_404(session, entity_id)

    updates = body.model_dump(exclude={"regenerate_token"}, exclude_unset=True)
    # Every column TimerInstanceUpdate can touch is NOT NULL. Pydantic's
    # `exclude_unset=True` only drops fields absent from the request body —
    # a field explicitly sent as JSON `null` (e.g. {"duration_s": null})
    # still comes through as `None` here, and `setattr(row, ..., None)`
    # would pass SQLAlchemy's flush only to fail at commit with an
    # unhandled IntegrityError. Treat an explicit null the same as "not
    # provided" instead.
    for field_name, value in updates.items():
        if value is None:
            continue
        setattr(row, field_name, value)

    if body.regenerate_token:
        # Appendix B.8: rotating the nonce invalidates every previously
        # issued teleprompter link for this instance.
        row.token_nonce = secrets.token_urlsafe(16)

    await session.commit()
    await session.refresh(row)

    await _publish_config_change(redis_client, row.entity_id, "updated", row.tags)
    return _to_read_schema(row)


@router.delete(
    "/{entity_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    dependencies=[_require_permission("timers:edit")],
)
async def delete_timer(
    entity_id: str,
    session: AsyncSession = Depends(get_db),
    redis_client: Any = Depends(get_redis),
) -> None:
    row = await get_timer_or_404(session, entity_id)
    tags = list(row.tags or [])

    # PrompterCue.timer_entity_id is a plain string column (no FK/cascade —
    # per plan §8's schema, cues are only ever looked up by that string, not
    # joined), so deleting a TimerInstance without also deleting its cues
    # would orphan them; a later instance created with the same entity_id
    # (nothing prevents reusing one) would then inherit stale cues.
    await session.execute(delete(PrompterCue).where(PrompterCue.timer_entity_id == entity_id))
    await session.delete(row)
    await session.commit()

    await _publish_config_change(redis_client, entity_id, "deleted", tags)


# ── Countdown control (plan §11 "Timers" — prompter:control) ────────────


@router.post(
    "/{entity_id}/start",
    dependencies=[_require_permission("prompter:control")],
)
async def start_timer(
    entity_id: str,
    session: AsyncSession = Depends(get_db),
    manager: TimerManager = Depends(_require_timer_manager),
) -> dict:
    await get_timer_or_404(session, entity_id)  # 404 before touching the manager
    try:
        await manager.start_countdown(entity_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return manager.get_state(entity_id)


@router.post(
    "/{entity_id}/stop",
    dependencies=[_require_permission("prompter:control")],
)
async def stop_timer_route(
    entity_id: str,
    session: AsyncSession = Depends(get_db),
    manager: TimerManager = Depends(_require_timer_manager),
) -> dict:
    await get_timer_or_404(session, entity_id)
    try:
        await manager.stop_timer(entity_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return manager.get_state(entity_id)


@router.post(
    "/{entity_id}/reset",
    dependencies=[_require_permission("prompter:control")],
)
async def reset_timer_route(
    entity_id: str,
    session: AsyncSession = Depends(get_db),
    manager: TimerManager = Depends(_require_timer_manager),
) -> dict:
    await get_timer_or_404(session, entity_id)
    try:
        await manager.reset_timer(entity_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return manager.get_state(entity_id)


# ── Prompter cues CRUD (plan §11 "Timers" cues + §5.10 "Runsheet") ───────


@router.get(
    "/{entity_id}/cues",
    response_model=list[PrompterCueRead],
    dependencies=[_require_permission("prompter:view")],
)
async def list_cues(
    entity_id: str, session: AsyncSession = Depends(get_db)
) -> list[PrompterCueRead]:
    await get_timer_or_404(session, entity_id)
    result = await session.execute(
        select(PrompterCue)
        .where(PrompterCue.timer_entity_id == entity_id)
        .order_by(PrompterCue.sort_order, PrompterCue.created_at)
    )
    return list(result.scalars().all())


@router.post(
    "/{entity_id}/cues",
    response_model=PrompterCueRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[_require_permission("prompter:edit")],
)
async def create_cue(
    entity_id: str, body: PrompterCueCreate, session: AsyncSession = Depends(get_db)
) -> PrompterCueRead:
    await get_timer_or_404(session, entity_id)
    if body.timer_entity_id != entity_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="body.timer_entity_id must match the URL's entity_id",
        )
    row = PrompterCue(**body.model_dump())
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


@router.put(
    "/{entity_id}/cues/{cue_id}",
    response_model=PrompterCueRead,
    dependencies=[_require_permission("prompter:edit")],
)
async def update_cue(
    entity_id: str,
    cue_id: UUID,
    body: PrompterCueUpdate,
    session: AsyncSession = Depends(get_db),
) -> PrompterCueRead:
    result = await session.execute(
        select(PrompterCue).where(
            PrompterCue.id == cue_id, PrompterCue.timer_entity_id == entity_id
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cue not found")

    # Same rationale as update_timer: every column PrompterCueUpdate can
    # touch (content, type, sort_order, is_active) is NOT NULL, so an
    # explicit JSON `null` must be treated as "not provided" rather than
    # applied and left to fail at commit.
    for field_name, value in body.model_dump(exclude_unset=True).items():
        if value is None:
            continue
        setattr(row, field_name, value)

    await session.commit()
    await session.refresh(row)
    return row


@router.delete(
    "/{entity_id}/cues/{cue_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    dependencies=[_require_permission("prompter:edit")],
)
async def delete_cue(
    entity_id: str, cue_id: UUID, session: AsyncSession = Depends(get_db)
) -> None:
    result = await session.execute(
        select(PrompterCue).where(
            PrompterCue.id == cue_id, PrompterCue.timer_entity_id == entity_id
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cue not found")
    await session.delete(row)
    await session.commit()
