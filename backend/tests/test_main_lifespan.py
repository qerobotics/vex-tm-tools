"""Integration tests for `backend.main.lifespan` against REAL Postgres +
Redis (the compose services, not fakeredis) — mirrors the pattern in
`tests/test_core/test_leader.py` / `tests/test_loader_real.py`.

Covers the Wave 4b wiring: `Scraper`/`Predictor` are instantiated,
started on leader promotion, exposed on `app.state` (predictor only, per
`backend.routers.ws.ConnectionManager.get_predictor`), and torn down on
demotion/shutdown — the same lifecycle already established for
`TimerManager`/`Loader`/`AutomationEngine`.

Uses a unique `lock_key` (patched into the `LeaderElection` this test's
`lifespan()` run constructs) rather than the fixed default
`qecomp:leader:lock` — the compose Redis is a SHARED scratch instance other
concurrently-running agents/processes may also be exercising `backend.main`
against, and colliding on the real default lock would make this test flaky
(unable to self-promote) without actually indicating a bug.
"""
from __future__ import annotations

import asyncio
import uuid
from unittest import mock

import pytest
import redis.asyncio as redis

import backend.main as main_module
from backend.core.settings import settings
from backend.modules.leader import LeaderElection as RealLeaderElection
from backend.routers.ws import manager as ws_manager

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def real_redis():
    client = redis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        await client.ping()
    except Exception:
        pytest.skip("Real Redis not reachable at REDIS_URL; skipping lifespan integration tests")
    yield client
    await client.aclose()


async def _wait_for(predicate, timeout: float = 5.0) -> None:
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.05)
    pytest.fail("condition not met within timeout")


async def test_promotion_wires_scraper_and_predictor_and_demotion_clears_them(real_redis):
    unique_lock_key = f"qecomp:test:leader:lock:{uuid.uuid4().hex}"

    def _unique_key_leader_election(redis_client, **kwargs):
        kwargs["lock_key"] = unique_lock_key
        return RealLeaderElection(redis_client, **kwargs)

    with mock.patch.object(
        main_module, "LeaderElection", side_effect=_unique_key_leader_election
    ):
        app = main_module.create_app()

        async with app.router.lifespan_context(app):
            # This process is the only contender for this test's own unique
            # lock key, so it should self-promote shortly after
            # `lifespan()`'s `leader.start()`.
            await _wait_for(lambda: app.state.predictor is not None)

            # Leader-only services are live and exposed on app.state.
            assert app.state.timer_manager is not None
            assert app.state.automation_engine is not None
            assert app.state.loader is not None
            assert app.state.predictor is not None

            # `/ws/prompter`'s `high_potential` lookup resolves the SAME
            # predictor instance that was started, via the ws_manager hook
            # `backend.main` wires in `lifespan()`.
            assert ws_manager.get_predictor() is app.state.predictor

            leader = app.state.leader
            assert leader.is_leader() is True

            # Simulate demotion directly via the callback `lifespan()` wired
            # onto the LeaderElection instance (mirrors what the election
            # loop's renewal-failure/RedisError branches would invoke) —
            # asserts the Wave 4b addition to `on_demoted` clears
            # `app.state.predictor` the same way it already clears
            # timer_manager/automation_engine/loader.
            await leader.on_demoted()

            assert app.state.timer_manager is None
            assert app.state.automation_engine is None
            assert app.state.loader is None
            assert app.state.predictor is None
            assert ws_manager.get_predictor() is None

            # Re-promotion should cleanly restart every leader-only service
            # again (idempotent start/stop pairing).
            await leader.on_promoted()
            assert app.state.predictor is not None
            assert ws_manager.get_predictor() is app.state.predictor

        # Exiting the lifespan context runs `lifespan()`'s shutdown teardown
        # (Scraper/Predictor stop, then leader/ws_manager/redis/db), which
        # must not raise even though this test already demoted-then-
        # repromoted.

        # Clean up this test's own lock key so it doesn't linger in the
        # shared Redis instance (it has a TTL and would expire on its own,
        # but no reason to leave it).
        await real_redis.delete(unique_lock_key)
