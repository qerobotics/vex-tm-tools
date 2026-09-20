"""Timer-Teleprompter instance manager (plan §5.10 / §7 / §C.2 / Appendix A.3).

FROZEN PUBLIC API — do not change method signatures without coordinating all
dependent waves (plan §C.2):

    class TimerManager:
        async def start(self) -> None
        async def stop(self) -> None
        async def reload(self) -> None
        async def start_countdown(self, entity_id: str) -> None
        async def stop_timer(self, entity_id: str) -> None
        async def reset_timer(self, entity_id: str) -> None
        def get_state(self, entity_id: str) -> dict

May import from: `backend/core/` (DB, Redis), `backend/models/`
(timer_instances, prompter_cues). `backend/loader` is imported lazily/
best-effort only to resolve a bound TM field's `field_set_id` when matching
`matchStopped` events (see `_handle_match_stopped`) — the Loader module is
being built in a parallel Wave 2 worktree and may not exist yet, so this
module must degrade gracefully (fall back to matching on `field_id` alone)
rather than hard-depend on it.

Must NOT import from: `routers/`, `modules/automation/`, `modules/scraper/`,
`modules/media/`, integration modules directly.

Runtime state (per §C.5 rule 2 — "no singleton state in modules") lives in
Redis at `qecomp:timer:<entity_id>:state` (plan §8's Redis key space table),
not in this process's memory: every tick recomputes `elapsed`/`remaining`
from the stored `start_ts` wall-clock timestamp, so a promoted leader that
restarts mid-countdown can resume ticking from where Redis says the timer
is. The only in-memory state is a read-through cache of the last-published
state per entity (`self._state_cache`) so the frozen `get_state()` API can
stay a plain synchronous method (Redis's client here is async-only, so a
truly synchronous method cannot perform a fresh Redis round-trip) and a set
of live `asyncio.Task` tick loops + pub/sub listeners, which are pure
execution machinery, not authoritative state.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import redis.asyncio as redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.core.db import async_session_factory
from backend.models.timer import TimerInstance
from backend.schemas.events import EventBusMessage

logger = logging.getLogger(__name__)

EVENTS_CHANNEL = "qecomp:events"
CONFIG_CHANGE_CHANNEL = "qecomp:config_change"

TICK_INTERVAL_SECONDS = 1.0

# Timer state machine phases, stored in the Redis hash's "phase" field.
PHASE_IDLE = "idle"
PHASE_COUNTDOWN = "countdown"
PHASE_MATCH_RUNNING = "match_running"
PHASE_MATCH_COMPLETE = "match_complete"


def _state_key(entity_id: str) -> str:
    return f"qecomp:timer:{entity_id}:state"


@dataclass
class _TimerConfig:
    """In-memory cache of a `timer_instances` row's config columns.

    This is a cache of Postgres-owned config, refreshed by `reload()` — not
    authoritative runtime state (that lives in Redis, see module docstring).
    """

    entity_id: str
    display_name: str
    field_set_id: int
    field_id: int
    tags: list[str]
    enabled: bool
    duration_s: int


@dataclass
class _RuntimeHandle:
    """Bookkeeping for one entity's live tick loop."""

    task: asyncio.Task | None = None
    last_state: dict[str, Any] = field(default_factory=dict)


class TimerManager:
    def __init__(
        self,
        redis_client: redis.Redis,
        *,
        session_factory: async_sessionmaker | None = None,
        tick_interval: float = TICK_INTERVAL_SECONDS,
    ) -> None:
        self._redis = redis_client
        self._session_factory = session_factory or async_session_factory
        self._tick_interval = tick_interval

        self._configs: dict[str, _TimerConfig] = {}
        self._runtime: dict[str, _RuntimeHandle] = {}

        self._events_task: asyncio.Task | None = None
        self._config_change_task: asyncio.Task | None = None
        self._shutdown = asyncio.Event()
        self._started = False

    # ── Public API (frozen — plan §C.2) ─────────────────────────────────

    async def start(self) -> None:
        """Load timer instance configs from Postgres, start the pub/sub
        listeners, and resume any timers that were mid-flight in Redis
        (e.g. after a leader promotion/restart)."""
        self._shutdown.clear()
        await self.reload()

        self._events_task = asyncio.create_task(self._events_listener())
        self._config_change_task = asyncio.create_task(self._config_change_listener())

        # Resume any instance whose Redis state says it's still running —
        # runtime state is authoritative in Redis, not in this process, so a
        # freshly promoted leader must pick these back up (§C.5 rule 2).
        # Instances disabled since they last ran are skipped: `enabled` is
        # config the operator can flip at any time (including while a
        # countdown/match is mid-flight), and a freshly promoted leader
        # should honor the current config rather than blindly resuming a
        # timer the operator has since turned off.
        for entity_id, cfg in list(self._configs.items()):
            if not cfg.enabled:
                continue
            try:
                state = await self._read_state(entity_id)
            except Exception:
                logger.exception("Failed to read Redis state for %s during start()", entity_id)
                continue
            # Always seed `last_state` from Redis on resume — not just for
            # `running` instances — otherwise get_state() (which is
            # synchronous and reads only the in-memory cache, see class
            # docstring) would report a fabricated idle/never-run state for
            # an instance that's actually PHASE_MATCH_COMPLETE (frozen,
            # running=False) until something else happens to touch it.
            self._runtime.setdefault(entity_id, _RuntimeHandle()).last_state = (
                self._public_state(cfg, state)
            )
            if state.get("running"):
                self._ensure_tick_task(entity_id)

        self._started = True

    async def stop(self) -> None:
        """Stop all background tasks. Does not clear Redis runtime state —
        that's left intact so a re-promoted leader (or this same process on
        the next start()) can resume mid-countdown timers."""
        self._shutdown.set()

        for handle in self._runtime.values():
            if handle.task is not None:
                handle.task.cancel()
        for handle in self._runtime.values():
            if handle.task is not None:
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await handle.task
                handle.task = None

        for task in (self._events_task, self._config_change_task):
            if task is not None:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
        self._events_task = None
        self._config_change_task = None
        self._started = False

    async def reload(self) -> None:
        """Re-read all `timer_instances` rows from Postgres (plan §5.2-style
        hot reload). Called on startup and on `qecomp:config_change`
        messages for `resource_type == "timer_instance"`."""
        async with self._session_factory() as session:
            result = await session.execute(select(TimerInstance))
            rows = result.scalars().all()

        new_configs: dict[str, _TimerConfig] = {}
        for row in rows:
            new_configs[row.entity_id] = _TimerConfig(
                entity_id=row.entity_id,
                display_name=row.display_name,
                field_set_id=row.field_set_id,
                field_id=row.field_id,
                tags=list(row.tags or []),
                enabled=row.enabled,
                duration_s=row.duration_s,
            )

        removed = set(self._configs) - set(new_configs)
        for entity_id in removed:
            await self._cancel_tick_task(entity_id)
            self._runtime.pop(entity_id, None)

        self._configs = new_configs
        logger.info("TimerManager.reload(): %d timer instance(s) loaded", len(new_configs))

    async def start_countdown(self, entity_id: str) -> None:
        """Begin (or restart) the countdown for `entity_id` (Appendix A.3:
        triggered only by the EMCEE's "Start Countdown" button)."""
        cfg = self._require_config(entity_id)
        if not cfg.enabled:
            raise ValueError(f"Timer instance {entity_id!r} is disabled")
        await self._cancel_tick_task(entity_id)

        now = time.time()
        state = {
            "phase": PHASE_COUNTDOWN,
            "start_ts": now,
            "duration_s": cfg.duration_s,
            "running": True,
        }
        await self._write_state(entity_id, state)
        self._runtime.setdefault(entity_id, _RuntimeHandle()).last_state = self._public_state(
            cfg, state
        )

        await self._publish(
            entity_id,
            cfg.tags,
            "timer_started",
            {
                "field_set_id": cfg.field_set_id,
                "field_id": cfg.field_id,
                "duration_s": cfg.duration_s,
            },
        )

        self._ensure_tick_task(entity_id)

    async def stop_timer(self, entity_id: str) -> None:
        """Manual stop (Appendix A.3 / plan §7 `timer_stopped`)."""
        cfg = self._require_config(entity_id)
        state = await self._read_state(entity_id)
        elapsed = self._compute_elapsed(state)

        await self._cancel_tick_task(entity_id)
        new_state = {
            "phase": PHASE_IDLE,
            "start_ts": 0.0,
            "duration_s": cfg.duration_s,
            "running": False,
            "frozen_elapsed": elapsed,
        }
        await self._write_state(entity_id, new_state)
        self._runtime.setdefault(entity_id, _RuntimeHandle()).last_state = self._public_state(
            cfg, new_state
        )

        await self._publish(
            entity_id,
            cfg.tags,
            "timer_stopped",
            {
                "field_set_id": cfg.field_set_id,
                "field_id": cfg.field_id,
                "elapsed": elapsed,
            },
        )

    async def reset_timer(self, entity_id: str) -> None:
        """Reset a timer back to idle without publishing `timer_stopped`
        (used to clear a finished/match-complete timer before the next
        match, per the Timers UI's "Reset" control)."""
        cfg = self._require_config(entity_id)
        await self._cancel_tick_task(entity_id)

        new_state = {
            "phase": PHASE_IDLE,
            "start_ts": 0.0,
            "duration_s": cfg.duration_s,
            "running": False,
        }
        await self._write_state(entity_id, new_state)
        self._runtime.setdefault(entity_id, _RuntimeHandle()).last_state = self._public_state(
            cfg, new_state
        )

    def get_state(self, entity_id: str) -> dict:
        """Synchronous accessor (frozen API — see module docstring for why
        this reads from an in-memory cache rather than Redis directly)."""
        handle = self._runtime.get(entity_id)
        if handle is not None and handle.last_state:
            return dict(handle.last_state)
        cfg = self._configs.get(entity_id)
        if cfg is None:
            return {}
        return self._public_state(
            cfg,
            {"phase": PHASE_IDLE, "start_ts": 0.0, "duration_s": cfg.duration_s, "running": False},
        )

    # ── Internal: config / state helpers ────────────────────────────────

    def _require_config(self, entity_id: str) -> _TimerConfig:
        cfg = self._configs.get(entity_id)
        if cfg is None:
            raise ValueError(f"Unknown timer instance: {entity_id!r}")
        return cfg

    def _public_state(self, cfg: _TimerConfig, raw: dict[str, Any]) -> dict[str, Any]:
        elapsed = self._compute_elapsed(raw)
        phase = raw.get("phase", PHASE_IDLE)
        duration_s = int(raw.get("duration_s", cfg.duration_s) or cfg.duration_s)
        remaining = max(duration_s - elapsed, 0) if phase == PHASE_COUNTDOWN else 0
        return {
            "entity_id": cfg.entity_id,
            "field_set_id": cfg.field_set_id,
            "field_id": cfg.field_id,
            "tags": list(cfg.tags),
            "phase": phase,
            "running": bool(raw.get("running", False)),
            "duration_s": duration_s,
            "elapsed": elapsed,
            "remaining": remaining,
        }

    @staticmethod
    def _compute_elapsed(raw: dict[str, Any]) -> int:
        start_ts = float(raw.get("start_ts") or 0.0)
        if not raw.get("running") or start_ts <= 0:
            # A stopped/idle timer's "elapsed" is whatever was last computed
            # before it stopped; callers that need that value (stop_timer)
            # compute it before mutating state, so this branch just
            # reports 0 for a never-started/reset timer.
            return int(raw.get("frozen_elapsed", 0) or 0)
        return max(int(time.time() - start_ts), 0)

    async def _read_state(self, entity_id: str) -> dict[str, Any]:
        raw = await self._redis.hgetall(_state_key(entity_id))
        if not raw:
            return {"phase": PHASE_IDLE, "start_ts": 0.0, "duration_s": 0, "running": False}
        return {
            "phase": raw.get("phase", PHASE_IDLE),
            "start_ts": float(raw.get("start_ts", 0.0) or 0.0),
            "duration_s": int(raw.get("duration_s", 0) or 0),
            "running": raw.get("running") in ("1", "true", "True"),
            "frozen_elapsed": int(raw.get("frozen_elapsed", 0) or 0),
        }

    async def _write_state(self, entity_id: str, state: dict[str, Any]) -> None:
        payload = {
            "phase": state["phase"],
            "start_ts": state.get("start_ts", 0.0),
            "duration_s": state.get("duration_s", 0),
            "running": "1" if state.get("running") else "0",
            # Always written (defaulting to 0), never left as a partial
            # `hset` — otherwise a stale `frozen_elapsed` from a prior
            # stop_timer()/_complete_match() call would survive a later
            # reset_timer() (which doesn't pass this key) and be reported
            # by a *subsequent* stop_timer() call on the now-idle instance.
            "frozen_elapsed": state.get("frozen_elapsed", 0),
        }
        await self._redis.hset(_state_key(entity_id), mapping=payload)

    # ── Internal: tick loop ──────────────────────────────────────────────

    def _ensure_tick_task(self, entity_id: str) -> None:
        handle = self._runtime.setdefault(entity_id, _RuntimeHandle())
        if handle.task is None or handle.task.done():
            handle.task = asyncio.create_task(self._tick_loop(entity_id))

    async def _cancel_tick_task(self, entity_id: str) -> None:
        handle = self._runtime.get(entity_id)
        if handle is None or handle.task is None:
            return
        handle.task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await handle.task
        handle.task = None

    async def _tick_loop(self, entity_id: str) -> None:
        """Per-instance async tick loop (never `threading.Timer` — plan
        §5.10). Each iteration re-reads Redis state so multiple instances
        remain fully isolated from one another (no shared in-process
        counters) and so state survives this task being cancelled/resumed."""
        try:
            while not self._shutdown.is_set():
                cfg = self._configs.get(entity_id)
                if cfg is None:
                    return  # instance was deleted out from under us

                state = await self._read_state(entity_id)
                if not state.get("running"):
                    return

                phase = state["phase"]
                elapsed = self._compute_elapsed(state)

                if phase == PHASE_COUNTDOWN:
                    remaining = state["duration_s"] - elapsed
                    if remaining <= 0:
                        await self._transition_to_match_running(entity_id, cfg)
                        continue  # re-read fresh state on the next loop iteration
                    self._runtime[entity_id].last_state = self._public_state(cfg, state)
                    await self._publish(
                        entity_id,
                        cfg.tags,
                        "timer_milestone",
                        {
                            "field_set_id": cfg.field_set_id,
                            "field_id": cfg.field_id,
                            "remaining": remaining,
                            "elapsed": elapsed,
                            # Consumers (frontend `stores/ws.ts`) replace their
                            # whole cached timer state with each event's
                            # payload rather than merging it — omitting these
                            # (unlike the PHASE_MATCH_RUNNING branch below,
                            # which does include them) made every countdown
                            # tick look like an idle timer in the UI even
                            # while remaining/elapsed were visibly changing.
                            "phase": PHASE_COUNTDOWN,
                            "running": True,
                        },
                    )
                elif phase == PHASE_MATCH_RUNNING:
                    self._runtime[entity_id].last_state = self._public_state(cfg, state)
                    await self._publish(
                        entity_id,
                        cfg.tags,
                        "timer_milestone",
                        {
                            "field_set_id": cfg.field_set_id,
                            "field_id": cfg.field_id,
                            # No fixed duration while counting up post-T0;
                            # `remaining` is 0 by convention (see
                            # `_public_state`) and `phase` disambiguates.
                            "remaining": 0,
                            "elapsed": elapsed,
                            "phase": PHASE_MATCH_RUNNING,
                        },
                    )
                else:
                    return

                await asyncio.sleep(self._tick_interval)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Timer tick loop for %s crashed", entity_id)

    async def _transition_to_match_running(self, entity_id: str, cfg: _TimerConfig) -> None:
        """At T-0: emit `timer_finished`, then switch to a count-up "Match
        Running" timer (Appendix A.3) until `matchStopped` is observed."""
        now = time.time()
        state = {
            "phase": PHASE_MATCH_RUNNING,
            "start_ts": now,
            "duration_s": cfg.duration_s,
            "running": True,
        }
        await self._write_state(entity_id, state)
        self._runtime.setdefault(entity_id, _RuntimeHandle()).last_state = self._public_state(
            cfg, state
        )
        await self._publish(
            entity_id,
            cfg.tags,
            "timer_finished",
            {"field_set_id": cfg.field_set_id, "field_id": cfg.field_id},
        )

    async def _complete_match(self, entity_id: str, cfg: _TimerConfig) -> None:
        """Transition to "Match Complete" on observing `matchStopped`
        (Appendix A.3). Freezes the elapsed count-up value."""
        state = await self._read_state(entity_id)
        elapsed = self._compute_elapsed(state)
        await self._cancel_tick_task(entity_id)

        new_state = {
            "phase": PHASE_MATCH_COMPLETE,
            "start_ts": 0.0,
            "duration_s": cfg.duration_s,
            "running": False,
            "frozen_elapsed": elapsed,
        }
        await self._write_state(entity_id, new_state)
        self._runtime.setdefault(entity_id, _RuntimeHandle()).last_state = self._public_state(
            cfg, new_state
        )

    # ── Internal: event bus ──────────────────────────────────────────────

    async def _publish(
        self, entity_id: str, tags: list[str], event_type: str, payload: dict[str, Any]
    ) -> None:
        msg = EventBusMessage(
            entity_id=entity_id,
            entity_tags=list(tags),
            type=event_type,
            timestamp=time.time(),
            payload=payload,
        )
        try:
            await self._redis.publish(EVENTS_CHANNEL, msg.model_dump_json())
        except Exception:
            logger.exception("Failed to publish %s event for %s", event_type, entity_id)

    async def _events_listener(self) -> None:
        """Subscribes to `qecomp:events` to detect `matchStopped` events from
        the bound TM field and transition matching timers to "Match
        Complete" (Appendix A.3)."""
        pubsub = self._redis.pubsub()
        try:
            await pubsub.subscribe(EVENTS_CHANNEL)
            while not self._shutdown.is_set():
                try:
                    message = await pubsub.get_message(
                        ignore_subscribe_messages=True, timeout=1.0
                    )
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("Error reading from %s pub/sub", EVENTS_CHANNEL)
                    await asyncio.sleep(1)
                    continue
                if message is None:
                    continue
                await self._handle_event_message(message)
        finally:
            with contextlib.suppress(Exception):
                await pubsub.unsubscribe(EVENTS_CHANNEL)
                await pubsub.aclose()

    async def _handle_event_message(self, message: dict[str, Any]) -> None:
        try:
            data = json.loads(message["data"])
        except (KeyError, TypeError, ValueError):
            return
        if data.get("type") != "matchStopped":
            return
        await self._handle_match_stopped(data)

    async def _handle_match_stopped(self, event: dict[str, Any]) -> None:
        """Match a `matchStopped` event to bound timer instance(s).

        The canonical `matchStopped` payload (plan §C.4) carries `fieldID`
        but not `field_set_id`; a `vex_tm` integration instance = one field
        set (plan §B.5), so in principle we should resolve the firing
        entity_id's `field_set_id` via `backend.loader.get_instance(...)`
        and match on `(field_set_id, field_id)`. The Loader is being built
        in a parallel Wave 2 worktree and may not be import-able yet, so we
        fall back to matching on `field_id` alone (sufficient for the
        common single-field-set event) when it isn't available. This is a
        known gap — see this module's docstring and the PR description.
        """
        field_id = event.get("payload", {}).get("fieldID")
        if field_id is None:
            return

        field_set_id = await self._resolve_field_set_id(event.get("entity_id"))

        for entity_id, cfg in list(self._configs.items()):
            if not cfg.enabled:
                # A disabled instance shouldn't have been able to reach
                # match_running via start_countdown() (which now rejects
                # disabled instances), but skip it defensively in case it
                # was disabled mid-flight after already starting.
                continue
            if cfg.field_id != field_id:
                continue
            if field_set_id is not None and cfg.field_set_id != field_set_id:
                continue
            state = await self._read_state(entity_id)
            if state.get("phase") == PHASE_MATCH_RUNNING:
                await self._complete_match(entity_id, cfg)

    async def _resolve_field_set_id(self, tm_entity_id: str | None) -> int | None:
        """Best-effort lookup of a `vex_tm` integration instance's bound
        `field_set_id` via the Loader's public API, per plan §B.5. Returns
        `None` (meaning "don't filter on field_set_id") if the Loader isn't
        available or the instance/config shape doesn't expose it."""
        if not tm_entity_id:
            return None
        try:
            from backend import loader as _loader  # local import — optional dep, see docstring
        except ImportError:
            return None
        try:
            instance = _loader.get_instance(tm_entity_id)
        except Exception:
            return None
        if instance is None:
            return None
        config = getattr(instance, "config", {}) or {}
        return config.get("field_set_id")

    async def _config_change_listener(self) -> None:
        """Subscribes to `qecomp:config_change` for `resource_type ==
        "timer_instance"` messages and hot-reloads config (plan §3.2-style
        hot reload, applied to Timer instances)."""
        pubsub = self._redis.pubsub()
        try:
            await pubsub.subscribe(CONFIG_CHANGE_CHANNEL)
            while not self._shutdown.is_set():
                try:
                    message = await pubsub.get_message(
                        ignore_subscribe_messages=True, timeout=1.0
                    )
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("Error reading from %s pub/sub", CONFIG_CHANGE_CHANNEL)
                    await asyncio.sleep(1)
                    continue
                if message is None:
                    continue
                try:
                    data = json.loads(message["data"])
                except (KeyError, TypeError, ValueError):
                    continue
                if data.get("payload", {}).get("resource_type") == "timer_instance":
                    await self.reload()
        finally:
            with contextlib.suppress(Exception):
                await pubsub.unsubscribe(CONFIG_CHANGE_CHANNEL)
                await pubsub.aclose()
