"""AI Match Predictor — local OPR/DPR regression + high-potential flagging
(plan §5.12 / §C.2).

Owns: OPR computation from match history, high-potential match flagging,
result caching in Redis.

May import from: `backend.core` (DB for match history, Redis for cached
OPR), `backend.models` (team_profiles read-only), `backend.schemas.events`.

Must NOT import from: `routers/`, `loader/`, `modules/scraper/`,
`modules/automation/`, `modules/timer/`, `modules/media/`, integration
modules.

── CRITICAL — predicted-score leakage (plan §5.12) ─────────────────────────
"The predicted score is never shown to anyone except internally. Only the
flag appears on the teleprompter." §C.4's canonical event table nonetheless
lists `predicted_red`/`predicted_blue` as `match_prediction` payload fields
— this is intentional: the *internal* Redis pub/sub event (`qecomp:events`)
carries the full payload per the frozen schema, because other backend
modules subscribing to the raw bus is normal (§C.5 rule 5, "the event bus is
the only broadcast mechanism"). The contradiction is resolved at the
boundary between the event bus and anything user-facing:

  * `predict_match()` and `get_flag()` — this class's public API — MUST be
    used by callers (routers, WebSocket handlers) to expose **only**
    `high_potential`/the boolean flag. Never forward `predicted_red`/
    `predicted_blue` from a `match_prediction` event (or from
    `predict_match()`'s return dict) into any API response, WebSocket
    message, or log field that reaches the UI/teleprompter/operator tooling.
  * Wave 3/4 (whoever builds the router/WebSocket layer that surfaces
    predictions to the frontend, e.g. the teleprompter's ⚡ flag) must only
    read `get_flag(match_id)` (a bare `bool | None`) — never deserialize a
    raw `match_prediction` event body into a response.
This module cannot enforce that at the network layer by itself (routers are
built by later waves) — it is enforced by keeping `predict_match()`'s
detailed dict for internal/test use only, and by this comment.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.core.redis import redis_client as default_redis_client
from backend.models.settings import SystemSetting
from backend.models.team import TeamProfile
from backend.schemas.events import EventBusMessage

logger = logging.getLogger(__name__)

EVENTS_CHANNEL = "qecomp:events"
DEFAULT_HIGH_POTENTIAL_THRESHOLD_PCT = 15
OPR_CACHE_KEY = "qecomp:predictor:opr"
FLAGS_CACHE_KEY = "qecomp:predictor:flags"


def match_id_for(division_id: Any, match_num: Any) -> str:
    """Canonical `match_id` used for `get_flag()` lookups."""
    return f"{division_id}:{match_num}"


class Predictor:
    """Computes a local OPR (one-shot least-squares regression over all
    scored matches in the event so far) and flags "high potential" matches.

    `predict_match()`/`get_flag()` are intentionally synchronous per §C.2's
    frozen public API — they read from an in-memory cache of the last
    computed OPR ratings / threshold / flags, which is (re)populated by the
    async `start()`/event-handling machinery. This is a read-through cache,
    not authoritative state: the source of truth remains Postgres
    (`team_profiles.cached_stats`) and Redis (`qecomp:predictor:*`), both of
    which are re-read on every OPR refresh.
    """

    def __init__(
        self,
        redis: Any = None,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self._redis = redis if redis is not None else default_redis_client
        if session_factory is None:
            from backend.core.db import async_session_factory as _default_factory

            session_factory = _default_factory
        self._session_factory = session_factory

        self._task: asyncio.Task | None = None
        self._pubsub = None
        self._shutdown = asyncio.Event()

        # In-memory read-through cache (see class docstring).
        self._opr_ratings: dict[str, float] = {}
        self._threshold_pct: float = DEFAULT_HIGH_POTENTIAL_THRESHOLD_PCT
        self._combined_score_threshold: float | None = None
        self._flags: dict[str, bool] = {}

    # ── Lifecycle ────────────────────────────────────────────────────────

    async def start(self) -> None:
        self._shutdown.clear()
        await self._refresh_threshold_setting()
        await self._refresh_opr()
        await self._load_flags_from_redis()

        self._pubsub = self._redis.pubsub()
        await self._pubsub.subscribe(EVENTS_CHANNEL)
        self._task = asyncio.create_task(self._listen_loop())

    async def stop(self) -> None:
        self._shutdown.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
        if self._pubsub is not None:
            try:
                await self._pubsub.unsubscribe(EVENTS_CHANNEL)
                await self._pubsub.aclose()
            except Exception:
                logger.exception("Error closing predictor pubsub connection")
            self._pubsub = None

    async def _listen_loop(self) -> None:
        assert self._pubsub is not None
        try:
            async for message in self._pubsub.listen():
                if self._shutdown.is_set():
                    break
                if message is None or message.get("type") != "message":
                    continue
                await self._handle_raw_message(message.get("data"))
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Predictor event listen loop crashed")

    async def _handle_raw_message(self, data: Any) -> None:
        try:
            payload = json.loads(data) if isinstance(data, (str, bytes)) else data
            event = EventBusMessage.model_validate(payload)
        except Exception:
            logger.warning("Predictor received malformed event bus message: %r", data)
            return

        if event.type == "team_profile_updated":
            await self._refresh_opr()
            return

        if event.type != "fieldMatchAssigned":
            return

        division_id = event.payload.get("divisionId")
        match_num = event.payload.get("matchNum")
        red_teams = [str(t) for t in (event.payload.get("redTeams") or [])]
        blue_teams = [str(t) for t in (event.payload.get("blueTeams") or [])]

        result = self.predict_match(red_teams, blue_teams)
        mid = match_id_for(division_id, match_num)
        self._flags[mid] = result["high_potential"]
        try:
            await self._redis.hset(FLAGS_CACHE_KEY, mid, json.dumps(result["high_potential"]))
        except Exception:
            logger.exception("Failed to persist predictor flag for %s", mid)

        await self._publish_match_prediction(division_id, match_num, result)

    # ── Public API ───────────────────────────────────────────────────────

    def predict_match(self, red_teams: list[str], blue_teams: list[str]) -> dict[str, Any]:
        """Predict the combined alliance scores from the cached OPR ratings
        and flag whether this is a "high potential" match.

        NEVER forward `predicted_red`/`predicted_blue` from this return
        value to any user-facing surface — see module docstring.
        """
        predicted_red = sum(self._opr_ratings.get(t, 0.0) for t in red_teams)
        predicted_blue = sum(self._opr_ratings.get(t, 0.0) for t in blue_teams)
        combined = predicted_red + predicted_blue

        high_potential = (
            self._combined_score_threshold is not None
            and combined >= self._combined_score_threshold
        )

        return {
            "predicted_red": round(predicted_red, 2),
            "predicted_blue": round(predicted_blue, 2),
            "high_potential": bool(high_potential),
        }

    def get_flag(self, match_id: str) -> bool | None:
        return self._flags.get(match_id)

    # ── OPR computation ──────────────────────────────────────────────────

    async def _refresh_threshold_setting(self) -> None:
        async with self._session_factory() as session:
            setting = await session.get(SystemSetting, "predictor")
            if setting is not None:
                pct = (setting.value or {}).get("high_potential_threshold_pct")
                if isinstance(pct, (int, float)):
                    self._threshold_pct = float(pct)

    async def _collect_matches(self) -> list[dict[str, Any]]:
        """Read every team's cached match history from `team_profiles` and
        dedupe into a single list of scored matches (each team's profile
        redundantly stores the same match — see `Scraper._extract_team_matches`)."""
        seen: dict[tuple[Any, Any], dict[str, Any]] = {}
        async with self._session_factory() as session:
            result = await session.execute(select(TeamProfile))
            for row in result.scalars():
                stats = row.cached_stats or {}
                for m in stats.get("matches", []) or []:
                    key = (m.get("matchNum"), m.get("round"))
                    seen.setdefault(key, m)
        return list(seen.values())

    @staticmethod
    def _solve_opr(matches: list[dict[str, Any]]) -> dict[str, float]:
        """Classic OPR: for each alliance in each match, the sum of its
        teams' ratings should equal the alliance's score. Solved as a single
        least-squares system across every alliance (two rows per match: red
        and blue) via `numpy.linalg.lstsq`."""
        teams: list[str] = sorted(
            {t for m in matches for t in [*m["redTeams"], *m["blueTeams"]]}
        )
        if not teams:
            return {}
        team_index = {t: i for i, t in enumerate(teams)}

        rows: list[list[float]] = []
        scores: list[float] = []
        for m in matches:
            red_row = [0.0] * len(teams)
            for t in m["redTeams"]:
                red_row[team_index[t]] = 1.0
            rows.append(red_row)
            scores.append(float(m["redScore"]))

            blue_row = [0.0] * len(teams)
            for t in m["blueTeams"]:
                blue_row[team_index[t]] = 1.0
            rows.append(blue_row)
            scores.append(float(m["blueScore"]))

        A = np.array(rows, dtype=float)
        b = np.array(scores, dtype=float)
        solution, _residuals, _rank, _sv = np.linalg.lstsq(A, b, rcond=None)
        return {team: float(rating) for team, rating in zip(teams, solution)}

    @staticmethod
    def _combined_score_percentile_threshold(
        matches: list[dict[str, Any]], threshold_pct: float
    ) -> float | None:
        """Value at the (100 - threshold_pct)th percentile of historical
        combined (red + blue) scores — matches at/above this are "top X%"."""
        if not matches:
            return None
        combined_scores = sorted(
            float(m["redScore"]) + float(m["blueScore"]) for m in matches
        )
        percentile = max(0.0, min(100.0, 100.0 - threshold_pct))
        return float(np.percentile(combined_scores, percentile))

    async def _refresh_opr(self) -> None:
        matches = await self._collect_matches()
        self._opr_ratings = self._solve_opr(matches)
        self._combined_score_threshold = self._combined_score_percentile_threshold(
            matches, self._threshold_pct
        )
        try:
            await self._redis.set(
                OPR_CACHE_KEY,
                json.dumps(
                    {
                        "ratings": self._opr_ratings,
                        "threshold": self._combined_score_threshold,
                        "computed_at": time.time(),
                    }
                ),
            )
        except Exception:
            logger.exception("Failed to persist OPR ratings cache to Redis")

    async def _load_flags_from_redis(self) -> None:
        try:
            raw = await self._redis.hgetall(FLAGS_CACHE_KEY)
        except Exception:
            logger.exception("Failed to load predictor flags cache from Redis")
            return
        for mid, value in (raw or {}).items():
            try:
                self._flags[mid] = bool(json.loads(value))
            except (TypeError, json.JSONDecodeError):
                continue

    async def _publish_match_prediction(
        self, division_id: Any, match_num: Any, result: dict[str, Any]
    ) -> None:
        event = EventBusMessage(
            entity_id="predictor",
            entity_tags=[],
            type="match_prediction",
            timestamp=time.time(),
            payload={
                "matchNum": match_num,
                "divisionId": division_id,
                "high_potential": result["high_potential"],
                "predicted_red": result["predicted_red"],
                "predicted_blue": result["predicted_blue"],
            },
        )
        try:
            await self._redis.publish(EVENTS_CHANNEL, event.model_dump_json())
        except Exception:
            logger.exception("Failed to publish match_prediction for %s/%s", division_id, match_num)
