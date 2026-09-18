"""Developer/Debug Views API (plan Appendix A.11).

Of the three debug views Appendix A.11 calls for (Automation Execution
History, Integration Debug Log, Live Event Bus), this router implements
the second: `GET /api/v1/debug/integrations/{entity_id}/log`, reading the
per-instance last-100-raw-events ring buffer that `backend/loader.py`'s
`_events_debug_log_listener()` maintains at
`qecomp:integration:{entity_id}:debug_log` (LPUSH + LTRIM to 100 + a 7-day
EXPIRE on every event mirrored off the `qecomp:events` pub/sub channel).

Per Appendix A.11, all three debug views require `settings:edit`.
"""
from __future__ import annotations

import json
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from redis.asyncio import Redis as AsyncRedis

from backend.core.dependencies import require_permission
from backend.core.redis import get_redis
from backend.loader import DEBUG_LOG_KEY_TMPL

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/debug",
    tags=["debug"],
    dependencies=[Depends(require_permission("settings:edit"))],
)


@router.get("/integrations/{entity_id}/log")
async def get_integration_debug_log(
    entity_id: str,
    redis: Annotated[AsyncRedis, Depends(get_redis)],
) -> list[dict[str, Any]]:
    """Returns this instance's last (up to) 100 raw `qecomp:events`
    messages, most-recent-first (the natural order of the underlying Redis
    list, since each event is `LPUSH`ed onto its head as it arrives).

    Returns an empty list for an entity with no recorded events (never
    existed, never emitted an event yet, or its debug log already expired)
    rather than 404ing — this is a diagnostic view, not a resource lookup.
    """
    key = DEBUG_LOG_KEY_TMPL.format(entity_id=entity_id)
    raw_entries = await redis.lrange(key, 0, -1)

    entries: list[dict[str, Any]] = []
    for raw in raw_entries:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            entries.append(json.loads(raw))
        except (TypeError, ValueError):
            logger.warning("Skipping malformed debug log entry for '%s'", entity_id)
    return entries
