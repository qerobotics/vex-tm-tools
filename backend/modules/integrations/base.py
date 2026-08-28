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

from typing import Any


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

    def __init__(self, entity_id: str, config: dict[str, Any], redis: Any, db_pool: Any) -> None:
        self.entity_id = entity_id
        self.config = config
        self.tags = list(config.get("tags", []))
        self._redis = redis
        self._db_pool = db_pool

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
