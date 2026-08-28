"""Redis distributed-lock leader election (plan §3.1 / §5.1 / §C.2).

FROZEN PUBLIC API — do not change method signatures without coordinating all
dependent waves:

    class LeaderElection:
        async def start(self) -> None
        async def stop(self) -> None
        def is_leader(self) -> bool
        def get_leader_address(self) -> str | None
        on_promoted: Callable[[], Awaitable]
        on_demoted: Callable[[], Awaitable]

May import from: `backend/core/` (Redis) only.
"""
from __future__ import annotations

import asyncio
import logging
import socket
from collections.abc import Awaitable, Callable

import redis.asyncio as redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

LOCK_KEY = "qecomp:leader:lock"
LOCK_TTL_SECONDS = 30
RENEW_INTERVAL_SECONDS = 10
MAX_BACKOFF_SECONDS = 300  # 5 minutes

# Atomic check-and-renew / check-and-delete (Redlock-style). A plain
# GET-then-EXPIRE or GET-then-DELETE has a race window between the two
# round-trips where another node could acquire the lock in between,
# letting us renew/delete a lock we no longer own. Lua scripts execute
# atomically in Redis, closing that window.
_RENEW_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("expire", KEYS[1], ARGV[2])
else
    return 0
end
"""

_RELEASE_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""


async def _noop() -> None:
    return None


def _detect_local_ip() -> str:
    """Best-effort local IP detection for local dev, when POD_IP is unset."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return socket.gethostname()


class LeaderElection:
    """Acquires and renews `qecomp:leader:lock` in Redis.

    The lock value is `<pod_ip>:<port>` (plan §3.1) so the passive node can
    proxy leader-only requests directly to the current leader.
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        *,
        pod_ip: str | None = None,
        port: int = 8000,
        lock_key: str = LOCK_KEY,
        lock_ttl: int = LOCK_TTL_SECONDS,
        renew_interval: int = RENEW_INTERVAL_SECONDS,
    ) -> None:
        self._redis = redis_client
        self._pod_ip = pod_ip or _detect_local_ip()
        self._port = port
        self._lock_key = lock_key
        self._lock_ttl = lock_ttl
        self._renew_interval = renew_interval
        self._lock_value = f"{self._pod_ip}:{self._port}"

        self._is_leader = False
        self._shutdown = asyncio.Event()
        self._task: asyncio.Task | None = None

        # Set by main.py (per §C.2 — only main.py may set these callbacks).
        self.on_promoted: Callable[[], Awaitable] = _noop
        self.on_demoted: Callable[[], Awaitable] = _noop

    # ── Public API ────────────────────────────────────────────────────

    def is_leader(self) -> bool:
        return self._is_leader

    def get_leader_address(self) -> str | None:
        """Best-effort synchronous accessor. Returns the last-known leader
        address if this node currently holds the lock; otherwise `None`.

        Callers that need the *current* value from Redis (e.g. the passive
        node's proxy) should use `get_leader_address_async()` instead, since
        this method does not perform a Redis round-trip.
        """
        return self._lock_value if self._is_leader else None

    async def get_leader_address_async(self) -> str | None:
        """Read the current leader address directly from Redis."""
        try:
            value = await self._redis.get(self._lock_key)
        except RedisError:
            return None
        return value

    async def start(self) -> None:
        """Begin the election loop as a background asyncio task."""
        self._shutdown.clear()
        self._task = asyncio.create_task(self._election_loop())

    async def stop(self) -> None:
        """Release the lock (if held) and stop the renewal task."""
        self._shutdown.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("Unexpected error while awaiting cancelled election task")
            self._task = None

        if self._is_leader:
            try:
                await self._release_lock()
            except Exception:
                logger.exception("Error releasing leader lock during stop()")
            self._is_leader = False

    # ── Internal ─────────────────────────────────────────────────────

    async def _election_loop(self) -> None:
        backoff = 1
        while not self._shutdown.is_set():
            try:
                if not self._is_leader:
                    acquired = await self._try_acquire()
                    if acquired:
                        self._is_leader = True
                        logger.info("Leader lock acquired by %s", self._lock_value)
                        await self._safe_call(self.on_promoted)
                    else:
                        await self._sleep(self._renew_interval)
                        backoff = 1
                        continue
                else:
                    renewed = await self._try_renew()
                    if not renewed:
                        logger.warning(
                            "Lost leader lock renewal for %s — demoting", self._lock_value
                        )
                        # Split-brain protection: tear down before releasing (§3.1).
                        await self._safe_call(self.on_demoted)
                        self._is_leader = False
                        await self._sleep(self._renew_interval)
                        backoff = 1
                        continue

                backoff = 1
                await self._sleep(self._renew_interval)

            except RedisError:
                logger.warning(
                    "Redis unavailable during leader election, retrying in %ss", backoff
                )
                if self._is_leader:
                    # We can no longer talk to Redis to renew — assume the
                    # lock may have expired. Demote defensively.
                    await self._safe_call(self.on_demoted)
                    self._is_leader = False
                await self._sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Unexpected error in leader election loop")
                await self._sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)

    async def _sleep(self, seconds: float) -> None:
        try:
            await asyncio.wait_for(self._shutdown.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass

    async def _try_acquire(self) -> bool:
        result = await self._redis.set(
            self._lock_key, self._lock_value, nx=True, ex=self._lock_ttl
        )
        return bool(result)

    async def _try_renew(self) -> bool:
        """Atomically renew only if we still hold the lock (value matches
        ours) — see `_RENEW_SCRIPT` for why this must be a single Lua
        script rather than a GET followed by an EXPIRE."""
        result = await self._redis.eval(
            _RENEW_SCRIPT, 1, self._lock_key, self._lock_value, self._lock_ttl
        )
        return bool(result)

    async def _release_lock(self) -> None:
        """Atomically release only if we still hold the lock — see
        `_RELEASE_SCRIPT` for why this must be a single Lua script rather
        than a GET followed by a DELETE."""
        await self._redis.eval(_RELEASE_SCRIPT, 1, self._lock_key, self._lock_value)

    @staticmethod
    async def _safe_call(callback: Callable[[], Awaitable]) -> None:
        try:
            await callback()
        except Exception:
            logger.exception("Error in leader election on_promoted/on_demoted callback")
