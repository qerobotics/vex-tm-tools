"""Tests for backend.modules.leader.LeaderElection against a REAL Redis
instance (the compose Redis, not fakeredis) — genuine lock semantics and
timing matter for HA failover correctness.

Requires REDIS_URL to point at a real reachable Redis (see conftest.py /
compose.yml — `docker compose up -d redis`).
"""
from __future__ import annotations

import asyncio
import uuid

import pytest
import redis.asyncio as redis

from backend.core.settings import settings
from backend.modules.leader import LeaderElection

pytestmark = pytest.mark.asyncio


def _unique_lock_key() -> str:
    return f"qecomp:test:leader:lock:{uuid.uuid4().hex}"


@pytest.fixture
async def redis_client():
    client = redis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        await client.ping()
    except Exception:
        pytest.skip("Real Redis not reachable at REDIS_URL; skipping leader election tests")
    yield client
    await client.aclose()


async def test_single_node_acquires_lock(redis_client):
    lock_key = _unique_lock_key()
    election = LeaderElection(
        redis_client, pod_ip="10.0.0.1", port=8000, lock_key=lock_key,
        lock_ttl=5, renew_interval=1,
    )

    promoted = asyncio.Event()

    async def on_promoted():
        promoted.set()

    election.on_promoted = on_promoted

    await election.start()
    try:
        await asyncio.wait_for(promoted.wait(), timeout=5)
        assert election.is_leader() is True
        assert election.get_leader_address() == "10.0.0.1:8000"

        value = await redis_client.get(lock_key)
        assert value == "10.0.0.1:8000"
    finally:
        await election.stop()

    # Lock released on stop().
    assert await redis_client.get(lock_key) is None


async def test_lock_renewed_periodically(redis_client):
    lock_key = _unique_lock_key()
    election = LeaderElection(
        redis_client, pod_ip="10.0.0.2", port=8000, lock_key=lock_key,
        lock_ttl=3, renew_interval=1,
    )
    await election.start()
    try:
        await asyncio.sleep(0.5)
        assert election.is_leader() is True

        # Wait longer than the initial TTL — if renewal works, the key
        # should still exist (and still be held by us).
        await asyncio.sleep(4)
        assert election.is_leader() is True
        ttl = await redis_client.ttl(lock_key)
        assert ttl > 0
    finally:
        await election.stop()


async def test_two_node_failover(redis_client):
    """Two LeaderElection instances contend for the same lock. Exactly one
    becomes leader. When the leader's renewal task is stopped (simulating a
    crash) and its lock is allowed to expire, the standby promotes within the
    TTL window.
    """
    lock_key = _unique_lock_key()
    ttl = 3
    renew_interval = 1

    node_a = LeaderElection(
        redis_client, pod_ip="10.0.0.10", port=8000, lock_key=lock_key,
        lock_ttl=ttl, renew_interval=renew_interval,
    )
    node_b = LeaderElection(
        redis_client, pod_ip="10.0.0.11", port=8000, lock_key=lock_key,
        lock_ttl=ttl, renew_interval=renew_interval,
    )

    a_promoted = asyncio.Event()
    b_promoted = asyncio.Event()
    node_a.on_promoted = a_promoted.set
    node_b.on_promoted = b_promoted.set

    await node_a.start()
    await node_b.start()
    try:
        await asyncio.sleep(2)

        leaders = [n for n in (node_a, node_b) if n.is_leader()]
        assert len(leaders) == 1
        leader, standby = (node_a, node_b) if node_a.is_leader() else (node_b, node_a)

        # Simulate the leader's process dying: cancel its renewal task
        # directly (without going through stop(), which would release the
        # lock cleanly — a real crash wouldn't) and let the lock expire.
        if leader._task is not None:
            leader._task.cancel()
            try:
                await leader._task
            except (asyncio.CancelledError, Exception):
                pass
        leader._is_leader = False

        # Wait for the lock TTL to lapse and the standby to notice and win.
        await asyncio.wait_for(b_promoted.wait() if standby is node_b else a_promoted.wait(), timeout=ttl + renew_interval + 10)

        assert standby.is_leader() is True
    finally:
        for n in (node_a, node_b):
            try:
                await n.stop()
            except Exception:
                pass
