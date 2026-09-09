"""Dynamic integration module loader/registry (plan §C.2 / §3.2 / §5.2).

Scans `backend/modules/integrations/<domain>/` for folders containing
`manifest.yaml` + `integration.py`, imports each `integration.py` via
`importlib` (never a static `import` — this is how new integration domains
get added without touching any other module, per plan §C.5 rule 4), and
registers the `Integration` subclass it finds in `INTEGRATION_REGISTRY`.

Instance configuration lives exclusively in Postgres's
`integration_instances` table. On promotion, `Loader.load_all()` reads that
table, decrypts each `secret: true` config field (per the domain's
`manifest.yaml` `config_schema`) via `backend.core.security`, instantiates
the registered class, and calls `await instance.setup()`. If `setup()`
raises, the instance is marked `DEGRADED` in Redis and retried in the
background with exponential backoff (plan §3.2) — the loader itself never
crashes.

Hot-reload: `Loader.reconcile()` diffs the live in-memory instance set
against the current Postgres state and tears down/spins up instances
accordingly, live, with no process restart. It is triggered automatically
by a `config_change` message on the `qecomp:config_change` Redis pub/sub
channel (see plan §8's Redis key space table), and can also be called
directly (e.g. right after a router persists a config change).

Public API (the only way other modules access integration instances) —
frozen per plan §C.2:

    INTEGRATION_REGISTRY: dict[str, type[Integration]]
    get_instance(entity_id: str) -> Integration | None
    get_instances_by_tag(tag: str) -> list[Integration]
    get_all_instances() -> list[Integration]
    get_instance_status(entity_id: str) -> str   # CONNECTED/DEGRADED/DISCONNECTED
"""
from __future__ import annotations

import asyncio
import contextlib
import importlib.util
import logging
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select

from backend.core.db import async_session_factory
from backend.core.redis import redis_client
from backend.core.security import decrypt
from backend.models.integration import IntegrationInstance
from backend.modules.integrations.base import Integration

logger = logging.getLogger(__name__)

INTEGRATIONS_DIR = Path(__file__).parent / "modules" / "integrations"
CONFIG_CHANGE_CHANNEL = "qecomp:config_change"
STATUS_KEY_TMPL = "qecomp:integration:{entity_id}:status"

MAX_BACKOFF_SECONDS = 300  # 5 minutes, per plan §3.2 / §3.7

# domain -> registered Integration subclass.
INTEGRATION_REGISTRY: dict[str, type[Integration]] = {}
# domain -> parsed manifest.yaml (used to know which config fields are secrets).
_MANIFESTS: dict[str, dict[str, Any]] = {}


def _discover() -> None:
    """Scan `modules/integrations/<domain>/` and (re)populate
    `INTEGRATION_REGISTRY` + `_MANIFESTS`. Never raises — a domain folder
    that fails to load is logged and skipped so the rest of the system
    keeps working."""
    INTEGRATION_REGISTRY.clear()
    _MANIFESTS.clear()
    if not INTEGRATIONS_DIR.exists():
        logger.warning("Integrations directory %s does not exist", INTEGRATIONS_DIR)
        return

    for domain_dir in sorted(p for p in INTEGRATIONS_DIR.iterdir() if p.is_dir()):
        manifest_path = domain_dir / "manifest.yaml"
        integration_path = domain_dir / "integration.py"
        if not manifest_path.exists() or not integration_path.exists():
            continue
        try:
            manifest = yaml.safe_load(manifest_path.read_text()) or {}
            domain = manifest.get("domain") or domain_dir.name

            module_name = f"backend.modules.integrations.{domain_dir.name}._dynamic"
            spec = importlib.util.spec_from_file_location(module_name, integration_path)
            if spec is None or spec.loader is None:
                logger.error("Could not build import spec for %s", integration_path)
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            cls = getattr(module, "IntegrationClass", None)
            if cls is None:
                # Fallback: find the single Integration subclass defined in
                # the module (excludes Integration itself).
                for attr in vars(module).values():
                    if isinstance(attr, type) and issubclass(attr, Integration) and attr is not Integration:
                        cls = attr
                        break
            if cls is None:
                logger.error("No Integration subclass found in %s", integration_path)
                continue

            INTEGRATION_REGISTRY[domain] = cls
            _MANIFESTS[domain] = manifest
            logger.info("Registered integration domain=%s class=%s", domain, cls.__name__)
        except Exception:
            logger.exception("Failed to load integration domain from %s", domain_dir)


def _decrypt_config(domain: str, config: dict[str, Any]) -> dict[str, Any]:
    """Decrypt every `secret: true` field of `config` per the domain's
    manifest `config_schema`. Leaves non-secret fields untouched; a field
    that fails to decrypt is logged and left as-is rather than crashing the
    whole instance."""
    manifest = _MANIFESTS.get(domain, {})
    schema = manifest.get("config_schema", {}) or {}
    out = dict(config)
    for field, spec in schema.items():
        if spec.get("secret") and out.get(field):
            try:
                out[field] = decrypt(out[field])
            except Exception:
                logger.exception("Failed to decrypt config field '%s' for domain '%s'", field, domain)
    return out


class Loader:
    """Owns the live set of instantiated `Integration` objects for this
    process. Only the leader pod's `main.py` should construct and drive
    one of these (per §C.2) — but its module-level convenience functions
    (`get_instance`, etc.) always reflect whichever `Loader` was most
    recently constructed, which is how a passive-node process (that never
    calls `load_all()`) simply reports every entity as absent/DISCONNECTED.
    """

    def __init__(self, redis: Any = None, session_factory: Any = None) -> None:
        self._redis = redis if redis is not None else redis_client
        self._session_factory = session_factory if session_factory is not None else async_session_factory

        self._instances: dict[str, Integration] = {}
        self._entity_domain: dict[str, str] = {}
        self._entity_config_fingerprint: dict[str, tuple[Any, ...]] = {}
        self._status: dict[str, str] = {}
        self._retry_tasks: dict[str, asyncio.Task] = {}

        self._pubsub_task: asyncio.Task | None = None
        self._shutdown = asyncio.Event()

        global _loader
        _loader = self

    # ── discovery + startup ──────────────────────────────────────────
    def discover(self) -> None:
        _discover()

    async def load_all(self) -> None:
        """Discover integration domains (if not already done), instantiate
        every enabled `integration_instances` row, and start the
        `config_change` hot-reload listener."""
        if not INTEGRATION_REGISTRY:
            self.discover()
        self._shutdown = asyncio.Event()

        rows = await self._fetch_rows()
        for row in rows:
            if row.enabled:
                await self._spin_up(row)

        self._pubsub_task = asyncio.create_task(self._config_change_listener())

    async def _fetch_rows(self) -> list[IntegrationInstance]:
        async with self._session_factory() as session:
            result = await session.execute(select(IntegrationInstance))
            return list(result.scalars().all())

    # ── spin up / tear down a single instance ────────────────────────
    def _fingerprint(self, row: IntegrationInstance) -> tuple[Any, ...]:
        # A cheap, order-independent fingerprint of everything that should
        # trigger a teardown+respin when it changes.
        return (
            row.domain,
            tuple(sorted((row.config or {}).items())),
            tuple(sorted(row.tags or [])),
        )

    async def _spin_up(self, row: IntegrationInstance) -> None:
        entity_id = row.entity_id
        cls = INTEGRATION_REGISTRY.get(row.domain)
        if cls is None:
            logger.error("Unknown integration domain '%s' for entity '%s'", row.domain, entity_id)
            await self._set_status(entity_id, "DISCONNECTED")
            return

        config = _decrypt_config(row.domain, dict(row.config or {}))
        config["tags"] = list(row.tags or [])
        instance = cls(entity_id, config, self._redis, self._session_factory)

        try:
            await instance.setup()
        except Exception:
            logger.exception("setup() failed for '%s' (domain=%s)", entity_id, row.domain)
            await self._set_status(entity_id, "DEGRADED")
            self._entity_domain[entity_id] = row.domain
            self._entity_config_fingerprint[entity_id] = self._fingerprint(row)
            self._schedule_retry(row)
            return

        self._instances[entity_id] = instance
        self._entity_domain[entity_id] = row.domain
        self._entity_config_fingerprint[entity_id] = self._fingerprint(row)
        await self._set_status(entity_id, "CONNECTED")

    async def _tear_down(self, entity_id: str) -> None:
        instance = self._instances.pop(entity_id, None)
        self._entity_domain.pop(entity_id, None)
        self._entity_config_fingerprint.pop(entity_id, None)

        retry_task = self._retry_tasks.pop(entity_id, None)
        if retry_task is not None:
            retry_task.cancel()
            with contextlib.suppress(Exception, asyncio.CancelledError):
                await retry_task

        if instance is not None:
            try:
                await asyncio.wait_for(instance.teardown(), timeout=5)
            except Exception:
                logger.exception("teardown() failed for '%s'", entity_id)

        await self._set_status(entity_id, "DISCONNECTED")

    async def _set_status(self, entity_id: str, status: str) -> None:
        self._status[entity_id] = status
        try:
            await self._redis.set(STATUS_KEY_TMPL.format(entity_id=entity_id), status)
        except Exception:
            logger.exception("Failed to write status to Redis for '%s'", entity_id)

    # ── background retry with exponential backoff (plan §3.2) ───────
    def _schedule_retry(self, row: IntegrationInstance) -> None:
        if row.entity_id in self._retry_tasks:
            return
        task = asyncio.create_task(self._retry_loop(row))
        self._retry_tasks[row.entity_id] = task

    async def _retry_loop(self, row: IntegrationInstance) -> None:
        entity_id = row.entity_id
        backoff = 1
        try:
            while not self._shutdown.is_set():
                await asyncio.sleep(min(backoff, MAX_BACKOFF_SECONDS))
                backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)

                cls = INTEGRATION_REGISTRY.get(row.domain)
                if cls is None:
                    continue

                config = _decrypt_config(row.domain, dict(row.config or {}))
                config["tags"] = list(row.tags or [])
                instance = cls(entity_id, config, self._redis, self._session_factory)
                try:
                    await instance.setup()
                except Exception:
                    logger.warning("Retry setup() failed for '%s' (backoff=%ss)", entity_id, backoff)
                    continue

                self._instances[entity_id] = instance
                self._entity_domain[entity_id] = row.domain
                self._entity_config_fingerprint[entity_id] = self._fingerprint(row)
                await self._set_status(entity_id, "CONNECTED")
                return
        finally:
            self._retry_tasks.pop(entity_id, None)

    # ── hot reload (plan §3.2 / §5.2) ────────────────────────────────
    async def _config_change_listener(self) -> None:
        pubsub = self._redis.pubsub()
        try:
            await pubsub.subscribe(CONFIG_CHANGE_CHANNEL)
            async for message in pubsub.listen():
                if self._shutdown.is_set():
                    break
                if message is None or message.get("type") != "message":
                    continue
                try:
                    await self.reconcile()
                except Exception:
                    logger.exception("reconcile() failed while handling config_change")
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("config_change listener crashed")
        finally:
            with contextlib.suppress(Exception):
                await pubsub.unsubscribe(CONFIG_CHANGE_CHANNEL)
            with contextlib.suppress(Exception):
                await pubsub.aclose()

    async def reconcile(self) -> None:
        """Diff the live instance set against current Postgres state and
        tear down/spin up instances accordingly — live, with no restart."""
        if not INTEGRATION_REGISTRY:
            self.discover()

        rows = await self._fetch_rows()
        desired: dict[str, IntegrationInstance] = {r.entity_id: r for r in rows if r.enabled}
        desired_ids = set(desired.keys())
        current_ids = set(self._instances.keys()) | set(self._retry_tasks.keys())

        # Removed (deleted or disabled): tear down.
        for entity_id in current_ids - desired_ids:
            await self._tear_down(entity_id)

        # New: spin up.
        for entity_id in desired_ids - current_ids:
            await self._spin_up(desired[entity_id])

        # Existing: respin only if the config/domain/tags actually changed.
        for entity_id in desired_ids & current_ids:
            row = desired[entity_id]
            new_fingerprint = self._fingerprint(row)
            if self._entity_config_fingerprint.get(entity_id) != new_fingerprint:
                await self._tear_down(entity_id)
                await self._spin_up(row)

    # ── shutdown ─────────────────────────────────────────────────────
    async def teardown_all(self) -> None:
        # Capture every tracked entity — both live instances and ones still
        # stuck in a DEGRADED background retry loop (which are never added
        # to `self._instances`) — *synchronously*, before setting the
        # shutdown flag or awaiting anything. A retry task that was
        # `create_task()`-ed but hasn't run yet only checks
        # `self._shutdown.is_set()` the first time it's actually scheduled;
        # if that first run happens to land after we set the flag (e.g.
        # during the `await self._pubsub_task` below), it exits its loop
        # immediately and pops itself from `self._retry_tasks` *without*
        # ever going through `_tear_down()` — silently leaving its status
        # stuck at DEGRADED forever. Snapshotting `targets` first, before
        # any `await` gives that race a chance to happen, avoids it: even
        # if the retry task removes itself from `_retry_tasks` in the
        # meantime, its entity_id is still in `targets` and `_tear_down()`
        # tolerates `self._retry_tasks.pop(entity_id, None)` returning None.
        targets = set(self._instances.keys()) | set(self._retry_tasks.keys())

        self._shutdown.set()
        if self._pubsub_task is not None:
            self._pubsub_task.cancel()
            with contextlib.suppress(Exception, asyncio.CancelledError):
                await self._pubsub_task
            self._pubsub_task = None

        for entity_id in targets:
            await self._tear_down(entity_id)
        self._retry_tasks.clear()

    # ── accessors used by the module-level public API below ─────────
    def get_instance(self, entity_id: str) -> Integration | None:
        return self._instances.get(entity_id)

    def get_instances_by_tag(self, tag: str) -> list[Integration]:
        return [inst for inst in self._instances.values() if tag in inst.tags]

    def get_all_instances(self) -> list[Integration]:
        return list(self._instances.values())

    def get_instance_status(self, entity_id: str) -> str:
        return self._status.get(entity_id, "DISCONNECTED")


# ── module-level singleton + frozen public API (plan §C.2) ──────────────
#
# `main.py` is expected to construct its own `Loader(...)` (per §C.2, it is
# the only file permitted to do so) — that instance becomes this module's
# singleton automatically (see `Loader.__init__`), which is what the four
# public functions below delegate to. A process that never constructs a
# `Loader` (e.g. a passive-node instance) gets a lazily-created, inert one
# whose accessors simply report every entity as absent/DISCONNECTED.
_loader: Loader | None = None


def _get_loader() -> Loader:
    global _loader
    if _loader is None:
        _loader = Loader()
    return _loader


def get_instance(entity_id: str) -> Integration | None:
    return _get_loader().get_instance(entity_id)


def get_instances_by_tag(tag: str) -> list[Integration]:
    return _get_loader().get_instances_by_tag(tag)


def get_all_instances() -> list[Integration]:
    return _get_loader().get_all_instances()


def get_instance_status(entity_id: str) -> str:
    return _get_loader().get_instance_status(entity_id)
