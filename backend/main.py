"""FastAPI app factory + lifespan (plan §B.10 / §C.2).

Per §C.2, this is the ONLY file permitted to import and instantiate
`LeaderElection`, `AutomationEngine`, `TimerManager`, `Scraper`, `Predictor`,
and the `Loader`, and to wire `on_promoted`/`on_demoted` callbacks.

Wave 2b added `TimerManager` (`backend.modules.timer.manager`) to that
wiring alongside the `LeaderElection` Wave 1 already built. Wave 3a
(Automation Engine) adds the `Loader` (`backend.loader`) and
`AutomationEngine` (`backend.modules.automation.engine`) the same way:
instantiated here, started/stopped from `on_promoted`/`on_demoted`, exposed
on `app.state` only while this node is the leader. `Scraper` and
`Predictor` still don't exist as of this wave — the extension point for
those remains below.

Run with (per Appendix B.1 — exactly 1 worker per pod):

    uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 1
"""
from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import json
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.db import async_session_factory, check_db_connection, engine, get_db
from backend.core.redis import check_redis_connection, redis_client
from backend.core.security import validate_prompter_token
from backend.core.settings import settings
from backend.loader import Loader
from backend.modules.automation.engine import AutomationEngine
from backend.modules.leader import LeaderElection
from backend.modules.timer.manager import TimerManager
from backend.routers.automations import router as automations_router
from backend.routers.scripts import router as scripts_router
from backend.routers.teams import router as teams_router
from backend.routers.timers import get_timer_or_404
from backend.routers.timers import router as timers_router
from backend.schemas.health import HealthResponse, ReadyResponse

_STATIC_DIR = Path(__file__).parent / "static"

logger = logging.getLogger(__name__)

# Read once at import time and cached in memory — per Appendix C.5's
# no-blocking-I/O-in-request-handlers rule, `serve_prompter` below must not
# do a synchronous file read on every request. `prompter.html` is a static
# asset baked into the image, so a process restart is required (and already
# expected) to pick up a change to it.
_PROMPTER_HTML = (_STATIC_DIR / "prompter.html").read_text(encoding="utf-8")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup/shutdown orchestration.

    Verifies DB/Redis connectivity (best-effort; never crash per Appendix
    A.10), exposes them on `app.state`, and runs leader election + the
    `TimerManager` / `Loader` / `AutomationEngine` (only the leader
    instantiates/runs these — plan §3.1/§5.1).

    ─────────────────────────────────────────────────────────────────────
    EXTENSION POINT for later waves (do NOT add business logic elsewhere):
    add `Scraper`, `Predictor` the same way `timer_manager`/`loader`/
    `automation_engine` are wired below — instantiate them here, append
    their `.start()`/`.stop()` calls to `on_promoted`/`on_demoted`:

        from backend.modules.scraper.scraper import Scraper
        from backend.modules.predictor.predictor import Predictor

        scraper = Scraper(...)
        predictor = Predictor(...)
    ─────────────────────────────────────────────────────────────────────
    """
    db_ok = await check_db_connection()
    redis_ok = await check_redis_connection()
    if not db_ok:
        logger.warning("Postgres not reachable at startup — /readyz will report degraded")
    if not redis_ok:
        logger.warning(
            "Redis not reachable at startup (Appendix A.10: app degrades gracefully, "
            "does not crash)"
        )

    timer_manager = TimerManager(redis_client)
    loader = Loader(redis_client, async_session_factory)
    automation_engine = AutomationEngine(redis_client, async_session_factory)
    # Deliberately NOT set on `app.state` here — only the leader runs these
    # (plan §3.1/§5.1). They're set in `on_promoted` and cleared in
    # `on_demoted` below so that `backend.routers.timers._require_timer_manager`
    # / `backend.routers.automations._require_engine`'s 503 ("not the
    # current leader") is actually reachable on a passive node instead of
    # finding a constructed-but-never-started manager with an empty config
    # cache (which previously surfaced as a misleading 404).
    app.state.timer_manager = None
    app.state.automation_engine = None

    leader = LeaderElection(redis_client, port=settings.APP_PORT)

    async def on_promoted() -> None:
        # Loader first: AutomationEngine's `service`/`target_tag` actions
        # resolve entities exclusively via `backend.loader.get_instance()`/
        # `get_instances_by_tag()` (plan §C.5 rule 4), so integration
        # instances must be live before the engine starts processing
        # `qecomp:events`.
        await loader.load_all()
        await timer_manager.start()
        await automation_engine.start()
        app.state.timer_manager = timer_manager
        app.state.automation_engine = automation_engine

    async def on_demoted() -> None:
        app.state.timer_manager = None
        app.state.automation_engine = None
        await automation_engine.stop()
        await timer_manager.stop()
        await loader.teardown_all()

    leader.on_promoted = on_promoted
    leader.on_demoted = on_demoted
    app.state.leader = leader
    await leader.start()

    yield

    # Shutdown. Split-brain protection (plan §3.1): tear down every
    # leader-only service BEFORE releasing the Redis leader lock.
    # `LeaderElection.stop()` releases the lock unconditionally and does NOT
    # invoke `on_demoted` — that callback only fires from the election
    # loop's renewal-failure/RedisError branches — so calling `leader.stop()`
    # first would let a standby node acquire the lock and start its own
    # TimerManager/AutomationEngine/Loader while this node's tick loops/
    # pub-sub listeners/integration clients are still mid-teardown, causing
    # duplicate `qecomp:events` publishers and dual-command integration
    # conflicts (ATEM/OSC/Spotify).
    app.state.timer_manager = None
    app.state.automation_engine = None
    try:
        await automation_engine.stop()
    except Exception:
        logger.exception("Error stopping AutomationEngine during shutdown")
    try:
        await timer_manager.stop()
    except Exception:
        logger.exception("Error stopping TimerManager during shutdown")
    try:
        await loader.teardown_all()
    except Exception:
        logger.exception("Error tearing down Loader instances during shutdown")
    try:
        await leader.stop()
    except Exception:
        logger.exception("Error stopping leader election during shutdown")
    try:
        await redis_client.aclose()
    except Exception:
        logger.exception("Error closing Redis client during shutdown")
    try:
        await engine.dispose()
    except Exception:
        logger.exception("Error disposing DB engine during shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title="QEComp",
        version="1.0.0",
        lifespan=lifespan,
    )

    @app.get("/healthz", response_model=HealthResponse, tags=["health"])
    async def healthz() -> HealthResponse:
        """Liveness probe. No dependency checks — must always return 200 as
        long as the process is alive."""
        return HealthResponse(status="ok")

    @app.get("/readyz", tags=["health"])
    async def readyz():
        """Readiness probe. Checks DB + Redis connectivity.

        Per Appendix A.10, Redis being down must degrade gracefully rather
        than crash — Postgres remains the source of truth. We report 503 only
        when the *response itself* indicates the instance can't serve
        traffic acceptably; DB-only ("degraded") status is still reported
        with a 200-compatible payload plus an explicit `status` field, but we
        still return 503 to k8s readiness when DB is unreachable (Postgres is
        the source of truth and required), while a Redis-only outage keeps
        the pod marked ready and "degraded".
        """
        db_ok = await check_db_connection()
        redis_ok = await check_redis_connection()

        # "ok" only when everything is reachable; any single outage is
        # reported as "degraded" (DB-down is additionally reflected in the
        # HTTP status code below, since Postgres is the required source of
        # truth while Redis-only outages are a documented graceful-
        # degradation mode per Appendix A.10).
        status = "ok" if (db_ok and redis_ok) else "degraded"

        payload = ReadyResponse(status=status, db=db_ok, redis=redis_ok)
        # Only a dead Postgres makes the pod truly not-ready; Redis-only
        # outages are a documented graceful-degradation mode (Appendix A.10).
        http_status = 200 if db_ok else 503
        return JSONResponse(status_code=http_status, content=payload.model_dump())

    app.include_router(teams_router)

    @app.get("/prompter/{entity_id}", response_class=HTMLResponse, tags=["prompter"])
    async def serve_prompter(
        entity_id: str, token: str = "", session: AsyncSession = Depends(get_db)
    ):
        """Serves the standalone teleprompter page (plan Appendix B.3/B.4),
        with `entity_id`/`token` injected into a `<script>` block per the
        plan's templating instructions.

        Per Appendix B.8, the HMAC token is validated here (in addition to
        Wave 3's WebSocket-upgrade-time validation) purely so an invalid/
        stale link 403s immediately on page load rather than only failing
        silently once the WebSocket tries to connect. This is a page-level
        courtesy check, not a substitute for Wave 3's own validation at
        `/ws/prompter/{entity_id}`. Validation uses the same constant-time
        `validate_prompter_token` helper Wave 3's WS endpoint is expected to
        use, rather than a plain `!=` comparison, to avoid leaking timing
        information about the correct token.
        """
        # Reuses routers/timers.py's lookup (same 404 semantics) instead of
        # duplicating the query here.
        row = await get_timer_or_404(session, entity_id)

        if not validate_prompter_token(row.entity_id, row.token_nonce, token):
            raise HTTPException(status_code=403, detail="Invalid or expired teleprompter token")

        # JSON-encode before substitution (not a plain string replace) so an
        # entity_id/token containing quotes or other JS-special characters
        # can't break out of the `entityId: "__ENTITY_ID__"` string literal
        # and inject script into the page.
        html = _PROMPTER_HTML.replace('"__ENTITY_ID__"', json.dumps(entity_id))
        html = html.replace('"__TOKEN__"', json.dumps(token))
        return HTMLResponse(content=html)

    app.include_router(timers_router)
    app.include_router(automations_router)
    app.include_router(scripts_router)

    return app


app = create_app()
