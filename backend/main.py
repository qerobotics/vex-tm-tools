"""FastAPI app factory + lifespan (plan §B.10 / §C.2).

Per §C.2, this is the ONLY file permitted to import and instantiate
`LeaderElection`, `AutomationEngine`, `TimerManager`, `Scraper`, `Predictor`,
and the `Loader`, and to wire `on_promoted`/`on_demoted` callbacks. Those
managers (other than `LeaderElection`) don't exist yet in Wave 1 — this file
only builds the skeleton (DB/Redis lifecycle + health endpoints) and leaves a
clearly marked extension point for later waves.

Run with (per Appendix B.1 — exactly 1 worker per pod):

    uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 1
"""
from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from backend.core.db import check_db_connection, engine
from backend.core.redis import check_redis_connection, redis_client
from backend.core.settings import settings
from backend.routers.teams import router as teams_router
from backend.schemas.health import HealthResponse, ReadyResponse

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup/shutdown orchestration.

    Wave 1 scope: verify DB/Redis connectivity (best-effort; never crash per
    Appendix A.10) and expose them on `app.state`.

    ─────────────────────────────────────────────────────────────────────
    EXTENSION POINT for later waves (do NOT add business logic elsewhere):

        from backend.loader import Loader
        from backend.modules.leader import LeaderElection
        from backend.modules.automation.engine import AutomationEngine
        from backend.modules.timer.manager import TimerManager
        from backend.modules.scraper.scraper import Scraper
        from backend.modules.predictor.predictor import Predictor

        loader = Loader(...)
        leader = LeaderElection(redis_client, port=settings.APP_PORT)
        engine_ = AutomationEngine(...)
        timer_manager = TimerManager(...)
        scraper = Scraper(...)
        predictor = Predictor(...)

        async def on_promoted():
            await loader.load_all()
            await engine_.start()
            await timer_manager.start()
            await scraper.start()
            await predictor.start()

        async def on_demoted():
            await engine_.stop()
            await timer_manager.stop()
            await scraper.stop()
            await predictor.stop()
            await loader.teardown_all()

        leader.on_promoted = on_promoted
        leader.on_demoted = on_demoted
        app.state.leader = leader
        await leader.start()
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

    yield

    # Shutdown
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

    return app


app = create_app()
