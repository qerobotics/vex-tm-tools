"""Team Profile & Stats Scraper (plan §5.11 / §C.2).

Owns: triggering team data fetches when `fieldMatchAssigned` fires, fetching
from the TM REST API and the Robot Events API, computing derived stats,
writing to `team_profiles` Postgres table, Redis caching.

May import from: `backend.core` (DB, Redis), `backend.models` (team_profiles,
system_settings), `backend.schemas.events` (the frozen `EventBusMessage`).

Must NOT import from: `routers/`, `modules/automation/`, `modules/timer/`,
`modules/media/`, `modules/predictor/`.

── Note on TM REST access (coordination note for Wave 2a — Loader & Integrations) ──
Per §C.2 this module "may import from `backend.loader` (to get the vex_tm
instance for REST calls)". `backend.loader` and the `vex_tm` integration are
being built concurrently in a sibling worktree and are not available here.
The `Integration` ABC (`backend.modules.integrations.base.Integration`) only
exposes `call_service()` (for commands) and `get_state()` (telemetry) — no
read-only "give me the raw REST data" method. Rather than hard-depend on
Wave 2a's exact (not-yet-frozen) internals, this module fetches TM REST data
via its own lightweight `httpx.AsyncClient`, using:
  * `base_url` read directly from the `integration_instances` row for the
    given `tm_entity_id` (a non-secret config field per the vex_tm
    manifest's `config_schema`, so no Fernet decryption is required here).
  * the bearer token from the frozen Redis keyspace key
    `qecomp:tm:<entity_id>:token` (§8's Redis key space table — written by
    the vex_tm integration's `setup()`, already plaintext per that table).
This means the Scraper only depends on the DB row shape and the documented
Redis key convention, not on Wave 2a's class internals. If Wave 2a's
`loader.get_instance()` later grows a read-only data-fetch method, this
module can be switched to call it without changing its public API — but
that is a coordination decision for the maintainers, not made here.
"""
from __future__ import annotations

import asyncio
import json
import logging
import statistics
import time
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.core.redis import redis_client as default_redis_client
from backend.models.integration import IntegrationInstance
from backend.models.settings import SystemSetting
from backend.models.team import TeamProfile
from backend.schemas.events import EventBusMessage

logger = logging.getLogger(__name__)

EVENTS_CHANNEL = "qecomp:events"
TEAM_PROFILE_CACHE_TTL = 60 * 60 * 24  # 24h, per plan §5.11 / §8.
ROBOT_EVENTS_BASE_URL = "https://www.robotevents.com/api/v2"


def _team_cache_key(team_number: str) -> str:
    return f"qecomp:team:{team_number}:profile"


def _tm_token_key(entity_id: str) -> str:
    return f"qecomp:tm:{entity_id}:token"


class Scraper:
    """Subscribes to `qecomp:events`, auto-creates/enriches `team_profiles`
    rows from TM + Robot Events data, and caches the result in Redis."""

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

        # Reused per C.7 (single persistent client, created once).
        self._re_http = httpx.AsyncClient(base_url=ROBOT_EVENTS_BASE_URL, timeout=10.0)
        # TM base_url varies per instance, so this client carries no base_url.
        self._tm_http = httpx.AsyncClient(timeout=10.0)

    # ── Lifecycle ────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Subscribe to `qecomp:events` and begin listening for
        `fieldMatchAssigned` events in a background task."""
        self._shutdown.clear()
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
                logger.exception("Error closing scraper pubsub connection")
            self._pubsub = None
        try:
            await self._re_http.aclose()
            await self._tm_http.aclose()
        except Exception:
            logger.exception("Error closing scraper HTTP clients")

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
            logger.exception("Scraper event listen loop crashed")

    async def _handle_raw_message(self, data: Any) -> None:
        try:
            payload = json.loads(data) if isinstance(data, (str, bytes)) else data
            event = EventBusMessage.model_validate(payload)
        except Exception:
            logger.warning("Scraper received malformed event bus message: %r", data)
            return

        if event.type != "fieldMatchAssigned":
            return

        tm_entity_id = event.entity_id
        red_teams = event.payload.get("redTeams") or []
        blue_teams = event.payload.get("blueTeams") or []
        for team_number in [*red_teams, *blue_teams]:
            try:
                await self._auto_create_if_missing(str(team_number), tm_entity_id)
            except Exception:
                logger.exception(
                    "Failed to auto-create/refresh team profile for %s", team_number
                )

    async def _auto_create_if_missing(self, team_number: str, tm_entity_id: str) -> None:
        async with self._session_factory() as session:
            row = await session.get(TeamProfile, team_number)
            exists = row is not None
        if not exists:
            await self.fetch_team(team_number, tm_entity_id)

    # ── Public API ───────────────────────────────────────────────────────

    async def invalidate_cache(self, team_number: str) -> None:
        await self._redis.delete(_team_cache_key(team_number))

    async def fetch_team(self, team_number: str, tm_entity_id: str) -> dict[str, Any]:
        """Fetch team data from the TM instance + Robot Events, compute
        derived stats, upsert `team_profiles`, cache in Redis (24h TTL), and
        publish a `team_profile_updated` event. Returns the profile dict."""
        cache_key = _team_cache_key(team_number)
        cached = await self._redis.get(cache_key)
        if cached:
            try:
                return json.loads(cached)
            except (TypeError, json.JSONDecodeError):
                pass  # fall through and refetch on corrupt cache

        tm_data = await self._fetch_from_tm(team_number, tm_entity_id)
        re_data = await self._fetch_from_robot_events(team_number)

        profile = self._merge_profile(team_number, tm_data, re_data)

        await self._upsert_team_profile(profile)
        await self._redis.set(cache_key, json.dumps(profile), ex=TEAM_PROFILE_CACHE_TTL)
        await self._publish_team_profile_updated(team_number)
        return profile

    # ── TM REST fetching ─────────────────────────────────────────────────

    async def _get_tm_base_url_and_token(self, tm_entity_id: str) -> tuple[str | None, str | None]:
        base_url: str | None = None
        async with self._session_factory() as session:
            result = await session.execute(
                select(IntegrationInstance).where(IntegrationInstance.entity_id == tm_entity_id)
            )
            instance = result.scalar_one_or_none()
            if instance is not None:
                base_url = instance.config.get("base_url")
        token = await self._redis.get(_tm_token_key(tm_entity_id))
        return base_url, token

    async def _tm_get(self, base_url: str, token: str | None, path: str) -> Any:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        resp = await self._tm_http.get(base_url.rstrip("/") + path, headers=headers)
        resp.raise_for_status()
        return resp.json()

    async def _fetch_from_tm(self, team_number: str, tm_entity_id: str) -> dict[str, Any]:
        base_url, token = await self._get_tm_base_url_and_token(tm_entity_id)
        if not base_url:
            logger.warning(
                "No base_url configured for TM instance %s; skipping TM fetch for team %s",
                tm_entity_id,
                team_number,
            )
            return {}

        try:
            teams = await self._tm_get(base_url, token, "/api/teams")
        except Exception:
            logger.exception("Failed to fetch /api/teams from %s", tm_entity_id)
            teams = []

        team_row = next(
            (t for t in teams if str(t.get("number")) == str(team_number)), None
        )
        division_id = None
        if team_row:
            division = team_row.get("division")
            if isinstance(division, dict):
                division_id = division.get("id")
            else:
                division_id = team_row.get("divisionId") or division

        result: dict[str, Any] = {"team_row": team_row or {}}

        try:
            result["event"] = await self._tm_get(base_url, token, "/api/event")
        except Exception:
            logger.exception("Failed to fetch /api/event from %s", tm_entity_id)
            result["event"] = {}

        if division_id is not None:
            try:
                rankings = await self._tm_get(
                    base_url, token, f"/api/rankings/{division_id}/QUAL"
                )
                result["ranking"] = next(
                    (
                        r
                        for r in rankings
                        if str(r.get("team", {}).get("number", r.get("number")))
                        == str(team_number)
                    ),
                    None,
                )
            except Exception:
                logger.exception("Failed to fetch rankings from %s", tm_entity_id)
                result["ranking"] = None

            try:
                matches = await self._tm_get(base_url, token, f"/api/matches/{division_id}")
                result["matches"] = self._extract_team_matches(matches, team_number)
            except Exception:
                logger.exception("Failed to fetch matches from %s", tm_entity_id)
                result["matches"] = []
        else:
            result["ranking"] = None
            result["matches"] = []

        try:
            skills = await self._tm_get(base_url, token, "/api/skills")
            result["skills"] = [
                s
                for s in skills
                if str(s.get("team", {}).get("number", s.get("number"))) == str(team_number)
            ]
        except Exception:
            logger.exception("Failed to fetch skills from %s", tm_entity_id)
            result["skills"] = []

        return result

    @staticmethod
    def _extract_team_matches(matches: list[dict[str, Any]], team_number: str) -> list[dict[str, Any]]:
        """Filter the division's match list down to matches this team played
        in (qualification matches only, per the `/api/matches/<div_id>`
        endpoint — skills runs are fetched separately via `/api/skills` and
        are naturally excluded here).

        Returns a compact per-match record: matchNum, round, redTeams,
        blueTeams, redScore, blueScore — enough for the predictor's OPR
        regression to reconstruct alliance compositions without re-fetching.
        """
        out = []
        for m in matches or []:
            red_teams = [str(t) for t in (m.get("redTeams") or m.get("red", {}).get("teams") or [])]
            blue_teams = [str(t) for t in (m.get("blueTeams") or m.get("blue", {}).get("teams") or [])]
            if str(team_number) not in red_teams and str(team_number) not in blue_teams:
                continue
            red_score = m.get("redScore", m.get("red", {}).get("score"))
            blue_score = m.get("blueScore", m.get("blue", {}).get("score"))
            if red_score is None or blue_score is None:
                continue  # unscored/future match — excluded from stats.
            out.append(
                {
                    "matchNum": m.get("matchNum") or m.get("match_num") or m.get("number"),
                    "round": m.get("round"),
                    "redTeams": red_teams,
                    "blueTeams": blue_teams,
                    "redScore": red_score,
                    "blueScore": blue_score,
                }
            )
        return out

    # ── Robot Events fetching ────────────────────────────────────────────

    async def _get_robot_events_token(self) -> str | None:
        async with self._session_factory() as session:
            setting = await session.get(SystemSetting, "robot_events_api")
            if setting is None:
                return None
            return (setting.value or {}).get("token") or None

    async def _fetch_from_robot_events(self, team_number: str) -> dict[str, Any]:
        token = await self._get_robot_events_token()
        if not token:
            logger.debug("No Robot Events API token configured; skipping RE fetch")
            return {}

        headers = {"Authorization": f"Bearer {token}"}
        try:
            resp = await self._re_http.get(
                "/teams", params={"number[]": team_number}, headers=headers
            )
            resp.raise_for_status()
            teams = resp.json().get("data", [])
        except Exception:
            logger.exception("Failed to fetch Robot Events team lookup for %s", team_number)
            return {}

        if not teams:
            return {}
        re_team = teams[0]
        team_id = re_team.get("id")

        result: dict[str, Any] = {
            "bio": re_team.get("description") or re_team.get("bio"),
            "robot_name": re_team.get("robot_name"),
        }

        if team_id is not None:
            # None of these three depend on each other's result — fetch
            # concurrently instead of paying for 3 sequential round-trips
            # per team (this runs once per auto-created team per match).
            rankings_result, awards_result, skills_result = await asyncio.gather(
                self._re_http.get(f"/teams/{team_id}/rankings", headers=headers),
                self._re_http.get(f"/teams/{team_id}/awards", headers=headers),
                self._re_http.get(f"/teams/{team_id}/skills", headers=headers),
                return_exceptions=True,
            )

            if isinstance(rankings_result, BaseException):
                logger.exception("Failed to fetch RE rankings for team %s", team_id, exc_info=rankings_result)
                result["previous_rankings"] = []
            else:
                try:
                    rankings_result.raise_for_status()
                    result["previous_rankings"] = rankings_result.json().get("data", [])
                except Exception:
                    logger.exception("Failed to fetch RE rankings for team %s", team_id)
                    result["previous_rankings"] = []

            if isinstance(awards_result, BaseException):
                logger.exception("Failed to fetch RE awards for team %s", team_id, exc_info=awards_result)
                result["awards"] = []
            else:
                try:
                    awards_result.raise_for_status()
                    result["awards"] = awards_result.json().get("data", [])
                except Exception:
                    logger.exception("Failed to fetch RE awards for team %s", team_id)
                    result["awards"] = []

            if isinstance(skills_result, BaseException):
                logger.exception("Failed to fetch RE skills for team %s", team_id, exc_info=skills_result)
            else:
                try:
                    skills_result.raise_for_status()
                    skills_data = skills_result.json().get("data", [])
                    result["world_skills_rank"] = next(
                        (
                            s.get("rank")
                            for s in skills_data
                            if (s.get("season", {}) or {}).get("program", {}).get("id") is not None
                        ),
                        None,
                    )
                    result["uk_skills_rank"] = next(
                        (
                            s.get("rank")
                            for s in skills_data
                            if "uk" in str(s.get("region", "")).lower()
                        ),
                        None,
                    )
                except Exception:
                    logger.exception("Failed to fetch RE skills for team %s", team_id)

        return result

    # ── Stats + persistence ──────────────────────────────────────────────

    @staticmethod
    def _merge_profile(
        team_number: str, tm_data: dict[str, Any], re_data: dict[str, Any]
    ) -> dict[str, Any]:
        team_row = tm_data.get("team_row", {}) or {}
        matches = tm_data.get("matches", []) or []

        scores: list[float] = []
        for m in matches:
            red_teams = m.get("redTeams", [])
            score = m["redScore"] if str(team_number) in red_teams else m["blueScore"]
            scores.append(float(score))

        cached_stats: dict[str, Any] = {
            "qual_avg": round(statistics.fmean(scores), 2) if scores else None,
            "qual_high": max(scores) if scores else None,
            "qual_low": min(scores) if scores else None,
            "matches": matches,
            "ranking": tm_data.get("ranking"),
            "skills": tm_data.get("skills", []),
            "event": tm_data.get("event"),
            "previous_rankings": re_data.get("previous_rankings", []),
            "awards": re_data.get("awards", []),
            "world_skills_rank": re_data.get("world_skills_rank"),
            "uk_skills_rank": re_data.get("uk_skills_rank"),
            # `team_profiles` has no dedicated organisation/location columns
            # (plan §8's DDL only defines bio/robot_name/etc.) — kept in the
            # flexible cached_stats JSONB rather than silently discarded.
            "organisation": team_row.get("organization") or team_row.get("organisation"),
            "location": team_row.get("location"),
        }

        return {
            "team_number": str(team_number),
            "pit_location": None,
            "bio": re_data.get("bio"),
            "robot_name": re_data.get("robot_name") or team_row.get("robotName"),
            "cached_stats": cached_stats,
            "fetched_at": time.time(),
        }

    async def _upsert_team_profile(self, profile: dict[str, Any]) -> None:
        async with self._session_factory() as session:
            stmt = pg_insert(TeamProfile).values(
                team_number=profile["team_number"],
                bio=profile.get("bio"),
                robot_name=profile.get("robot_name"),
                cached_stats=profile.get("cached_stats"),
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=[TeamProfile.team_number],
                set_={
                    "bio": stmt.excluded.bio,
                    "robot_name": stmt.excluded.robot_name,
                    "cached_stats": stmt.excluded.cached_stats,
                },
            )
            await session.execute(stmt)
            await session.commit()

    async def _publish_team_profile_updated(self, team_number: str) -> None:
        event = EventBusMessage(
            entity_id="scraper",
            entity_tags=[],
            type="team_profile_updated",
            timestamp=time.time(),
            payload={"team_number": str(team_number)},
        )
        try:
            await self._redis.publish(EVENTS_CHANNEL, event.model_dump_json())
        except Exception:
            logger.exception("Failed to publish team_profile_updated for %s", team_number)
