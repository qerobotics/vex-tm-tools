"""Overlays API (plan §11 "Overlays" / §5.14).

Thin CRUD router over `overlay_instances`, plus a preview endpoint. Per
§C.2, no business logic lives here.
"""
from __future__ import annotations

import logging
import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.dependencies import get_db, require_permission
from backend.core.redis import get_redis
from backend.models.overlay import OverlayInstance
from backend.schemas.events import EventBusMessage
from backend.schemas.overlay import (
    OverlayInstanceCreate,
    OverlayInstanceRead,
    OverlayInstanceUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/overlays", tags=["overlays"])


async def _get_or_404(db: AsyncSession, entity_id: str) -> OverlayInstance:
    result = await db.execute(select(OverlayInstance).where(OverlayInstance.entity_id == entity_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Overlay {entity_id!r} not found")
    return row


async def _publish_config_change(redis_client: Any, entity_id: str, action: str, tags: list[str]) -> None:
    msg = EventBusMessage(
        entity_id=entity_id,
        entity_tags=tags,
        type="config_change",
        timestamp=time.time(),
        payload={"resource_type": "overlay_instance", "entity_id": entity_id, "action": action},
    )
    try:
        await redis_client.publish("qecomp:config_change", msg.model_dump_json())
    except Exception:
        logger.exception("Failed to publish config_change for %s", entity_id)


@router.get(
    "",
    response_model=list[OverlayInstanceRead],
    dependencies=[Depends(require_permission("overlays:read"))],
)
async def list_overlays(db: Annotated[AsyncSession, Depends(get_db)]) -> list[OverlayInstance]:
    result = await db.execute(select(OverlayInstance).order_by(OverlayInstance.display_name))
    return list(result.scalars().all())


@router.post(
    "",
    response_model=OverlayInstanceRead,
    status_code=201,
    dependencies=[Depends(require_permission("overlays:edit"))],
)
async def create_overlay(
    body: OverlayInstanceCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    redis_client: Any = Depends(get_redis),
) -> OverlayInstance:
    existing = await db.execute(select(OverlayInstance).where(OverlayInstance.entity_id == body.entity_id))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail=f"Overlay {body.entity_id!r} already exists")

    row = OverlayInstance(**body.model_dump())
    db.add(row)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail=f"Overlay {body.entity_id!r} already exists") from None
    await db.refresh(row)

    await _publish_config_change(redis_client, row.entity_id, "created", row.tags)
    return row


@router.put(
    "/{entity_id}",
    response_model=OverlayInstanceRead,
    dependencies=[Depends(require_permission("overlays:edit"))],
)
async def update_overlay(
    entity_id: str,
    body: OverlayInstanceUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    redis_client: Any = Depends(get_redis),
) -> OverlayInstance:
    row = await _get_or_404(db, entity_id)
    for field_name, value in body.model_dump(exclude_unset=True).items():
        if value is None:
            continue
        setattr(row, field_name, value)
    await db.commit()
    await db.refresh(row)
    await _publish_config_change(redis_client, row.entity_id, "updated", row.tags)
    return row


@router.delete(
    "/{entity_id}",
    status_code=204,
    response_model=None,
    dependencies=[Depends(require_permission("overlays:edit"))],
)
async def delete_overlay(
    entity_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    redis_client: Any = Depends(get_redis),
) -> None:
    row = await _get_or_404(db, entity_id)
    tags = list(row.tags or [])
    await db.delete(row)
    await db.commit()
    await _publish_config_change(redis_client, entity_id, "deleted", tags)


@router.get(
    "/{entity_id}/preview",
    dependencies=[Depends(require_permission("overlays:read"))],
)
async def preview_overlay(entity_id: str, db: Annotated[AsyncSession, Depends(get_db)]) -> dict[str, Any]:
    """Returns the queued-match data shape the overlay would currently
    render (plan §5.14), for the Overlays page's preview panel.

    GAP (flagged for the coordinator): the full team-video pipeline
    (resolving the next queued match for this overlay's `field_set_id` via
    `backend.loader`, then joining team numbers to
    `TeamProfile.video_360_s3_key` presigned URLs the way
    `routers/teams.py`'s `/batch/videos` already does) isn't wired up by
    this wave. This stub returns an empty "no match queued" shape
    (matching what `overlay.html`/the OBS overlay page is expected to
    render per Appendix A.6 — "no match queued -> transparent/empty") so
    the frontend Preview panel has a well-formed response to build against
    now, rather than a 404/501.
    """
    await _get_or_404(db, entity_id)
    return {"entity_id": entity_id, "match": None, "teams": []}
