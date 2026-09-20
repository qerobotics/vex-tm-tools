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

from backend.core.ntfy import send_ntfy_notification

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
        # Holds fire-and-forget ntfy notification tasks (Appendix A.8) so
        # they aren't garbage-collected mid-flight (asyncio only guarantees
        # an unreferenced task keeps running until its next checkpoint, not
        # to completion).
        self._bg_tasks: set[asyncio.Task] = set()
        # Tracks the currently in-flight `on_promoted()` call (run as a
        # background task — see `_start_promotion` — so a slow promotion
        # can never block the renewal loop and let the lock's TTL expire
        # out from under an in-progress promotion). Anything that demotes
        # (renewal failure, Redis outage, `stop()`) must wait for/cancel
        # this before running `on_demoted`, so the two callbacks never run
        # concurrently against the same `app.state` objects.
        self._promotion_task: asyncio.Task | None = None

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

        # Make sure a background `on_promoted()` (see `_start_promotion`)
        # isn't still running/starting leader-only services underneath the
        # shutdown sequence below.
        await self._await_pending_promotion()

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
                        # Run `on_promoted` as a background task rather than
                        # `await`-ing it inline here.
                        #
                        # Root cause of the "stuck non-leader after cold
                        # start" bug: `on_promoted` (loader.load_all() +
                        # starting the timer manager/automation engine/
                        # scraper/predictor) does real network/DB I/O — DB
                        # connections, decrypting configs, standing up
                        # integration clients — which is exactly the work
                        # that is slowest on a cold boot (first-ever
                        # connections, cold connection pools, DNS not fully
                        # warm yet). Previously this coroutine was awaited
                        # *before* the loop fell through to its renewal
                        # sleep, so nothing renewed `qecomp:leader:lock`'s
                        # 30s TTL while promotion was in flight. If
                        # promotion took longer than `LOCK_TTL_SECONDS`
                        # (30s) — very plausible on a cold container with a
                        # handful of integrations to connect — the lock
                        # would expire in Redis *while this process still
                        # believed it was leader and was busy promoting*.
                        # The very next loop iteration's `_try_renew()`
                        # would then find the key gone/mismatched, log
                        # "Lost leader lock renewal" and demote — tearing
                        # down the services that had just started (or were
                        # still starting) — while the *same* replica
                        # immediately re-acquired the now-free lock and
                        # started promoting all over again. Depending on
                        # how much slower each retried cold-start attempt
                        # was (e.g. leaked connections from an interrupted
                        # `on_promoted`/`on_demoted` pair), this could keep
                        # re-triggering indefinitely without a restart,
                        # while an external observer sampling `is_leader`/
                        # the Redis key mid-flap would see exactly the
                        # reported symptom: the lock key persisting
                        # (re-acquired immediately after each expiry) while
                        # `is_leader` reads inconsistently.
                        #
                        # Running promotion in the background instead means
                        # the election loop keeps renewing the lock on
                        # schedule (every `renew_interval`) regardless of
                        # how long `on_promoted` takes, so the lock can no
                        # longer expire out from under an in-progress
                        # promotion.
                        self._start_promotion(self.on_promoted)
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
                        # Wait for any still-in-flight promotion (see
                        # `_start_promotion`) before demoting, so
                        # `on_promoted`/`on_demoted` never run concurrently
                        # against the same `app.state` objects.
                        await self._await_pending_promotion()
                        # Split-brain protection: tear down before releasing (§3.1).
                        await self._safe_call(self.on_demoted)
                        self._is_leader = False
                        self._notify_failover("lock renewal failed")
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
                    await self._await_pending_promotion()
                    await self._safe_call(self.on_demoted)
                    self._is_leader = False
                    self._notify_failover("Redis unavailable")
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

    def _start_promotion(self, callback: Callable[[], Awaitable]) -> None:
        """Run `on_promoted` as a background task instead of `await`-ing it
        inline in the election loop — see the long comment at the call site
        in `_election_loop` for why: it decouples promotion's duration
        (real DB/network I/O, slowest on a cold boot) from the lock renewal
        cadence, so a slow promotion can never let the lock's TTL expire
        out from under it.
        """
        task = asyncio.create_task(self._run_promotion(callback))
        self._promotion_task = task
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)

    async def _run_promotion(self, callback: Callable[[], Awaitable]) -> None:
        await self._safe_call(callback)

    async def _await_pending_promotion(self) -> None:
        """Wait for a background `on_promoted()` started by
        `_start_promotion` to finish (if one is still running) before
        proceeding to demote. Without this, a demotion triggered while
        promotion is still in flight could run `on_demoted` concurrently
        with `on_promoted` against the same `app.state` objects (e.g.
        `automation_engine.stop()` racing `automation_engine.start()`).
        """
        task = self._promotion_task
        if task is not None and not task.done():
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("Error awaiting in-flight promotion before demotion")

    def _notify_failover(self, reason: str) -> None:
        """Appendix A.8: fire an ntfy notification on unexpected demotion
        (renewal failure / Redis outage). Fire-and-forget — must never delay
        or block the election loop."""
        task = asyncio.create_task(
            send_ntfy_notification(
                "Leader failover",
                f"Node {self._lock_value} lost leadership ({reason}).",
                priority="high",
            )
        )
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)

    @staticmethod
    async def _safe_call(callback: Callable[[], Awaitable]) -> None:
        try:
            await callback()
        except Exception:
            logger.exception("Error in leader election on_promoted/on_demoted callback")
