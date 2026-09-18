"""The `Integration` base class — FROZEN INTERFACE (plan §9 / §C.2).

Every concrete integration client (`backend/modules/integrations/<domain>/integration.py`,
built in Wave 2) must subclass this exactly. Do not change these method
signatures without coordinating every dependent wave.

Location: this is the canonical home. It is re-exported from
`backend.modules.integrations` (this package's `__init__.py`) so Wave 2 can
import it as either:

    from backend.modules.integrations.base import Integration
    from backend.modules.integrations import Integration

May import from: `backend/core/` only (per §C.2's boundary rule for
integration modules). Must NOT import from `loader/`, `routers/`, `models/`,
`schemas/`, or other integration domains.
"""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

# Shared with `backend/loader.py` (imported from there, not redefined) so
# every reader/writer of an instance's connection status — the loader
# itself and every concrete integration client — agrees on the exact Redis
# key format. Previously this template was duplicated verbatim across
# loader.py and three of the five integration files, which risked drifting
# out of sync on a future rename.
STATUS_KEY_TMPL = "qecomp:integration:{entity_id}:status"


class Integration:
    """Base class for all integration clients (vex_tm, spotify, atem, zeros, obs).

    Concrete subclasses own all connection logic, reconnection, service
    execution, and state reporting for their domain. They communicate with
    the rest of the system ONLY by publishing `EventBusMessage`s
    (see `backend.schemas.events`) to the `qecomp:events` Redis pub/sub
    channel — never by calling other modules directly.
    """

    entity_id: str
    config: dict[str, Any]
    tags: list[str]

    # Set by the loader (`backend/loader.py`) after construction, before
    # `setup()` is called — never passed via `__init__` since that
    # signature is frozen. A subclass that self-detects a mid-session
    # reconnect/degrade (e.g. on a dropped WebSocket) must call
    # `await self.report_status(...)` rather than writing to Redis
    # directly, so the loader's own in-memory bookkeeping (the backing
    # store for the frozen `get_instance_status()` API) stays in sync with
    # whatever status Redis actually holds. Left `None` for integrations
    # constructed outside the loader (e.g. in unit tests) — `report_status`
    # degrades gracefully to a direct Redis write in that case.
    _status_hook: Callable[[str, str], Awaitable[None]] | None = None

    def __init__(self, entity_id: str, config: dict[str, Any], redis: Any, db_pool: Any) -> None:
        self.entity_id = entity_id
        self.config = config
        self.tags = list(config.get("tags", []))
        self._redis = redis
        self._db_pool = db_pool

    async def report_status(self, status: str) -> None:
        """Report a status change (CONNECTED/DEGRADED/DISCONNECTED) for this
        instance. Concrete subclasses that detect their own mid-session
        connection state changes (e.g. a reconnect loop) must call this
        instead of writing to the status Redis key directly — see
        `_status_hook`'s docstring above. Never raises.
        """
        hook = self._status_hook
        if hook is not None:
            try:
                await hook(self.entity_id, status)
                return
            except Exception:
                logger.exception(
                    "Loader status hook failed for '%s'; falling back to direct Redis write",
                    self.entity_id,
                )
        try:
            await self._redis.set(STATUS_KEY_TMPL.format(entity_id=self.entity_id), status)
        except Exception:
            logger.exception("Failed to write status to Redis for '%s'", self.entity_id)

    async def setup(self) -> None:
        """Establish connections. Raise on unrecoverable error.

        On failure, the loader (Wave 2) marks this instance DEGRADED in Redis
        and retries in the background with exponential backoff.
        """
        raise NotImplementedError

    async def teardown(self) -> None:
        """Gracefully close all connections. Must NEVER raise (per §C.7.4).

        Must complete within 5 seconds — the leader election's split-brain
        protection depends on prompt teardown.
        """
        raise NotImplementedError

    async def call_service(self, service: str, data: dict[str, Any]) -> dict[str, Any]:
        """Execute a named service call. Return a result dict.

        Raise `ValueError` for an unknown service name.
        """
        raise NotImplementedError

    async def get_state(self) -> dict[str, Any]:
        """Return current state for dashboard telemetry. Must NEVER raise —
        return the last-known/cached state instead of raising on transient
        failures.
        """
        raise NotImplementedError
