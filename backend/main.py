"""FastAPI app factory + lifespan (plan §B.10 / §C.2).

Per §C.2, this is the ONLY file permitted to import and instantiate
`LeaderElection`, `AutomationEngine`, `TimerManager`, `Scraper`, `Predictor`,
and the `Loader`, and to wire `on_promoted`/`on_demoted` callbacks.

Wave 2b added `TimerManager` (`backend.modules.timer.manager`) to that
wiring alongside the `LeaderElection` Wave 1 already built. Wave 3b adds the
`Loader` (Wave 2a built it but never wired it into the app lifecycle —
without this, `routers/integrations.py`'s `loader.get_instance(...)` calls
would always see an empty registry) plus the auth/RBAC/integrations/
overlays/settings routers and the `/ws/*` WebSocket routes.
`AutomationEngine`, `Scraper`, and `Predictor` still don't exist in the app
lifecycle as of this wave — wire them into `on_promoted`/`on_demoted` the
same way `timer_manager`/`loader` are wired here.

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

from backend.core.db import check_db_connection, engine, get_db
from backend.core.redis import check_redis_connection, redis_client
from backend.core.security import validate_prompter_token
from backend.core.settings import settings
from backend.loader import Loader
from backend.modules.leader import LeaderElection
from backend.modules.timer.manager import TimerManager
from backend.routers.auth import router as auth_router
from backend.routers.integrations import router as integrations_router
from backend.routers.overlays import router as overlays_router
from backend.routers.settings import router as settings_router
from backend.routers.teams import router as teams_router
from backend.routers.timers import get_timer_or_404
from backend.routers.timers import router as timers_router
from backend.routers.ws import manager as ws_manager
from backend.routers.ws import router as ws_router
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
    `TimerManager`/`Loader` (only the leader instantiates/runs them — plan
    §3.1/§5.1/§5.2). The WS `ConnectionManager`'s Redis fan-out runs on every
    node regardless of leadership (see comment below).

    ─────────────────────────────────────────────────────────────────────
    EXTENSION POINT for later waves (do NOT add business logic elsewhere):
    add `AutomationEngine`, `Scraper`, `Predictor` the same way
    `timer_manager`/`loader` are wired below — instantiate them here, append
    their `.start()`/`.stop()` calls to `on_promoted`/`on_demoted`:

        from backend.modules.automation.engine import AutomationEngine
        from backend.modules.scraper.scraper import Scraper
        from backend.modules.predictor.predictor import Predictor

        engine_ = AutomationEngine(...)
        scraper = Scraper(...)
        predictor = Predictor(...)

        # then extend on_promoted/on_demoted below with:
        #   await engine_.start(); await scraper.start(); await predictor.start()
        #   await engine_.stop(); await scraper.stop(); await predictor.stop()
        #
        # Once Predictor is wired, also set (so /ws/prompter's
        # `high_potential` flag lookup works):
        #   app.state.predictor = predictor  # in on_promoted
        #   app.state.predictor = None       # in on_demoted
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
    loader = Loader(redis_client)
    # Deliberately NOT set on `app.state` here — only the leader runs
    # TimerManager/Loader (plan §3.1/§5.1/§5.2). `app.state.timer_manager`/
    # `app.state.loader` are set in `on_promoted` and cleared in
    # `on_demoted` below so that `backend.routers.timers._require_timer_manager`'s
    # 503 ("not the current leader") and `/ws/prompter/{entity_id}`'s
    # equivalent close code are actually reachable on a passive node instead
    # of finding a constructed-but-never-started manager with an empty
    # config cache (which previously surfaced as a misleading 404/empty
    # registry).
    app.state.timer_manager = None
    app.state.loader = None

    # WS ConnectionManager's background Redis pub/sub fan-out runs on every
    # node (both leader and passive pods forward `qecomp:events` messages to
    # their own connected WebSocket clients) — unlike TimerManager/Loader,
    # it holds no leader-only state, so it starts/stops with the app itself
    # rather than with promotion/demotion.
    ws_manager.get_timer_manager = lambda: app.state.timer_manager
    ws_manager.get_predictor = lambda: getattr(app.state, "predictor", None)
    await ws_manager.start()

    leader = LeaderElection(redis_client, port=settings.APP_PORT)

    async def on_promoted() -> None:
        await timer_manager.start()
        app.state.timer_manager = timer_manager
        await loader.load_all()
        app.state.loader = loader

    async def on_demoted() -> None:
        app.state.timer_manager = None
        app.state.loader = None
        await timer_manager.stop()
        await loader.teardown_all()

    leader.on_promoted = on_promoted
    leader.on_demoted = on_demoted
    app.state.leader = leader
    await leader.start()

    yield

    # Shutdown. Split-brain protection (plan §3.1): tear down TimerManager/
    # Loader (and any other leader-only service) BEFORE releasing the Redis
    # leader lock. `LeaderElection.stop()` releases the lock unconditionally
    # and does NOT invoke `on_demoted` — that callback only fires from the
    # election loop's renewal-failure/RedisError branches — so calling
    # `leader.stop()` first would let a standby node acquire the lock and
    # start its own TimerManager/Loader while this node's tick loops/
    # pub-sub listeners are still mid-cancellation, causing duplicates to
    # run concurrently and double-publish `qecomp:events`.
    app.state.timer_manager = None
    app.state.loader = None
    try:
        await timer_manager.stop()
    except Exception:
        logger.exception("Error stopping TimerManager during shutdown")
    try:
        await loader.teardown_all()
    except Exception:
        logger.exception("Error tearing down Loader during shutdown")
    try:
        await leader.stop()
    except Exception:
        logger.exception("Error stopping leader election during shutdown")
    try:
        await ws_manager.stop()
    except Exception:
        logger.exception("Error stopping WS ConnectionManager during shutdown")
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
    app.include_router(auth_router)
    app.include_router(integrations_router)
    app.include_router(overlays_router)
    app.include_router(settings_router)
    app.include_router(ws_router)

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

    return app


app = create_app()
