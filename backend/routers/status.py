"""Cluster/leader/integration-health status API (plan §11 `GET /api/v1/status`;
audit finding 1.7).

No permission required — matches `/healthz`/`/readyz`'s pattern (plan §11's
API table lists no `Permission` column for this route, unlike every other
router's endpoints).

Response shape (frozen to match `frontend/src/types/api.ts`'s
`ClusterStatus`, built in parallel against this exact contract):

    {
      "leader": {"is_leader": bool, "leader_address": str | null},
      "integrations": [
        {"entity_id": str, "status": str, "last_event_at": float | null},
        ...
      ]
    }

`last_event_at` is always `null` for now — nothing in the system currently
tracks a per-instance "last event received" timestamp in Redis or Postgres
(see this module's docstring note below); wiring that up is a minor
follow-up, not invented here to avoid adding new tracking infrastructure
outside this task's scope.
"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.db import get_db
from backend.core.redis import get_redis
from backend.models.integration import IntegrationInstance
from backend.modules.integrations.base import STATUS_KEY_TMPL

router = APIRouter(prefix="/api/v1", tags=["status"])


def _get_leader(request: Request) -> Any:
    """Same `app.state.leader` access pattern already used by
    `backend/routers/integrations.py`'s `_proxy_to_leader` call site
    (`getattr(request.app.state, "leader", None)`) — `app.state.leader` is
    set once in `main.py`'s `lifespan()` and is always present after
    startup, but `getattr` with a default keeps this dependency safe even
    if it's ever probed before `lifespan()` finishes.
    """
    return getattr(request.app.state, "leader", None)


@router.get("/status")
async def get_cluster_status(
    db: Annotated[AsyncSession, Depends(get_db)],
    redis: Annotated[Any, Depends(get_redis)],
    leader: Annotated[Any, Depends(_get_leader)],
) -> dict[str, Any]:
    is_leader = False
    leader_address: str | None = None
    if leader is not None:
        is_leader = leader.is_leader()
        # Prefer a live Redis read so a passive node reports the *current*
        # leader's address rather than `None` (its own `get_leader_address()`
        # is a non-leader no-op by design — see `LeaderElection`'s
        # docstring) — matching how `_proxy_to_leader` resolves the leader.
        leader_address = await leader.get_leader_address_async()

    result = await db.execute(select(IntegrationInstance))
    rows = list(result.scalars().all())

    integrations: list[dict[str, Any]] = []
    for row in rows:
        try:
            status = await redis.get(STATUS_KEY_TMPL.format(entity_id=row.entity_id))
            if isinstance(status, bytes):
                status = status.decode("utf-8")
        except Exception:
            status = None
        integrations.append(
            {
                "entity_id": row.entity_id,
                "status": status or "DISCONNECTED",
                # No per-instance "last event received" timestamp is tracked
                # anywhere yet (checked `backend/routers/ws.py` and
                # `backend/loader.py` — neither records one); reported as
                # `null` rather than inventing new tracking infrastructure.
                "last_event_at": None,
            }
        )

    return {
        "leader": {"is_leader": is_leader, "leader_address": leader_address},
        "integrations": integrations,
    }
