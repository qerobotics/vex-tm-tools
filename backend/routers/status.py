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

    # Bug fix: `qecomp:integration:{entity_id}:status` (written by the
    # *leader's* `Loader`/`Integration._status_hook` — see
    # `backend/loader.py`) is a plain `SET` with no TTL/expiry. A graceful
    # demotion (`Loader.teardown_all()`) explicitly rewrites it to
    # "DISCONNECTED", but an ungraceful leader loss (the pod is killed/
    # crashes/network-partitions rather than shutting down cleanly — the
    # exact HA-failover scenario this endpoint needs to report correctly)
    # never runs that teardown code at all, so the last value the now-dead
    # leader wrote (typically "CONNECTED") is left behind in Redis
    # forever — nothing else ever clears or expires it. That previously
    # meant the dashboard kept reporting "CONNECTED" throughout an entire
    # leaderless gap even though a real service call would correctly 503
    # with "Integration '...' is not currently running".
    #
    # Fixed here rather than in `LeaderElection`/`Loader` (per plan §C.2
    # only `Integration`/`Loader` write this key, and there's no reliable
    # hook that fires on an *ungraceful* leader loss to clear it from the
    # dying pod's side): `leader_address` above is already a live Redis
    # read of the *current* lock holder, so `None` means no replica is
    # currently holding `qecomp:leader:lock` at all — nothing is running
    # any integration, so cached statuses are stale by definition and must
    # be reported as unknown/disconnected rather than blindly returned.
    leader_alive = leader_address is not None

    result = await db.execute(select(IntegrationInstance))
    rows = list(result.scalars().all())

    integrations: list[dict[str, Any]] = []
    for row in rows:
        status: str | None = None
        if leader_alive:
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
