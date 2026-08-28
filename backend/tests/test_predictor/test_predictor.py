"""Tests for backend.modules.predictor.Predictor (plan §14 test_predictor.py).

Verifies: OPR regression correctness on a small hand-verifiable dataset,
high-potential flagging threshold logic, and — critically per §5.12 — that
`predicted_red`/`predicted_blue` never leak outside the internal event bus
payload (they must never appear in any DB row, and any consumer other than
`predict_match()`'s raw internal return value must only see the boolean
flag).
"""
from __future__ import annotations

import time
import uuid

import numpy as np
import pytest
import redis.asyncio as redis
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.core.settings import settings
from backend.models.settings import SystemSetting
from backend.models.team import TeamProfile
from backend.modules.predictor.predictor import Predictor, match_id_for
from backend.schemas.events import EventBusMessage

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def real_redis():
    client = redis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        await client.ping()
    except Exception:
        pytest.skip("Real Redis not reachable; skipping predictor tests")
    yield client
    await client.aclose()


@pytest.fixture
async def db_engine():
    engine = create_async_engine(settings.POSTGRES_DSN)
    try:
        async with engine.connect() as conn:
            await conn.exec_driver_sql("SELECT 1")
    except Exception:
        pytest.skip("Real Postgres not reachable; skipping predictor tests")
    yield engine
    await engine.dispose()


@pytest.fixture
async def session_factory(db_engine):
    return async_sessionmaker(bind=db_engine, expire_on_commit=False)


@pytest.fixture
async def predictor(real_redis, session_factory):
    p = Predictor(redis=real_redis, session_factory=session_factory)
    yield p
    await real_redis.delete("qecomp:predictor:opr")
    await real_redis.delete("qecomp:predictor:flags")


TEST_TEAMS = ["1111A", "2222B", "3333C", "4444D"]


@pytest.fixture
async def seeded_matches(session_factory):
    """A tiny, hand-verifiable 2-alliance-per-team dataset.

    Two matches:
      Match 1: red = [1111A, 2222B] score 100, blue = [3333C, 4444D] score 60
      Match 2: red = [1111A, 3333C] score 80,  blue = [2222B, 4444D] score 80

    With 4 unknowns and 4 equations this system is exactly determined (not
    least-squares-approximate), so the OPR solution can be hand-verified:
      1111A + 2222B = 100
      3333C + 4444D = 60
      1111A + 3333C = 80
      2222B + 4444D = 80
    Solving: subtract eq3 from eq1 -> 2222B - 3333C = 20.
    From eq2: 4444D = 60 - 3333C. Substitute into eq4:
      2222B + 60 - 3333C = 80 -> 2222B - 3333C = 20 (consistent, one free var).
    This system is actually rank-deficient (only 3 independent equations for
    4 unknowns), so `numpy.linalg.lstsq` returns the minimum-norm solution.
    We verify against numpy's own minimum-norm solution directly rather than
    hand-picking one of infinitely many exact solutions.
    """
    matches = [
        {"matchNum": 1, "round": "QUAL", "redTeams": ["1111A", "2222B"], "blueTeams": ["3333C", "4444D"], "redScore": 100, "blueScore": 60},
        {"matchNum": 2, "round": "QUAL", "redTeams": ["1111A", "3333C"], "blueTeams": ["2222B", "4444D"], "redScore": 80, "blueScore": 80},
    ]
    # Each team's cached_stats.matches redundantly stores the full match list
    # it participated in (matching Scraper's storage convention) — the
    # predictor dedupes by (matchNum, round) when reading across teams.
    async with session_factory() as session:
        for team in TEST_TEAMS:
            team_matches = [m for m in matches if team in m["redTeams"] or team in m["blueTeams"]]
            session.add(TeamProfile(team_number=team, cached_stats={"matches": team_matches}))
        await session.commit()

    yield matches

    async with session_factory() as session:
        for team in TEST_TEAMS:
            await session.execute(delete(TeamProfile).where(TeamProfile.team_number == team))
        await session.commit()


def _expected_min_norm_opr(matches):
    teams = sorted({t for m in matches for t in [*m["redTeams"], *m["blueTeams"]]})
    idx = {t: i for i, t in enumerate(teams)}
    rows, scores = [], []
    for m in matches:
        red = [0.0] * len(teams)
        for t in m["redTeams"]:
            red[idx[t]] = 1.0
        rows.append(red)
        scores.append(float(m["redScore"]))
        blue = [0.0] * len(teams)
        for t in m["blueTeams"]:
            blue[idx[t]] = 1.0
        rows.append(blue)
        scores.append(float(m["blueScore"]))
    A = np.array(rows)
    b = np.array(scores)
    solution, *_ = np.linalg.lstsq(A, b, rcond=None)
    return dict(zip(teams, solution))


async def test_collect_matches_dedupes_across_teams(predictor, seeded_matches):
    matches = await predictor._collect_matches()
    assert len(matches) == 2  # not 2*4=8 (each match appears in 2-4 team rows)
    match_nums = sorted(m["matchNum"] for m in matches)
    assert match_nums == [1, 2]


async def test_solve_opr_matches_hand_verified_minimum_norm_solution(seeded_matches):
    ratings = Predictor._solve_opr(seeded_matches)
    expected = _expected_min_norm_opr(seeded_matches)
    for team in TEST_TEAMS:
        assert ratings[team] == pytest.approx(expected[team], abs=1e-6)

    # Sanity check: predicted alliance sums reproduce the actual scores for
    # this exactly-fit (rank-3-of-4, but consistent) toy system.
    assert ratings["1111A"] + ratings["2222B"] == pytest.approx(100.0, abs=1e-6)
    assert ratings["3333C"] + ratings["4444D"] == pytest.approx(60.0, abs=1e-6)
    assert ratings["1111A"] + ratings["3333C"] == pytest.approx(80.0, abs=1e-6)
    assert ratings["2222B"] + ratings["4444D"] == pytest.approx(80.0, abs=1e-6)


async def test_solve_opr_simple_overdetermined_system():
    """A simple, unambiguous 3-team case with a clear least-squares answer."""
    matches = [
        {"matchNum": 1, "round": "QUAL", "redTeams": ["A"], "blueTeams": ["B"], "redScore": 50, "blueScore": 30},
        {"matchNum": 2, "round": "QUAL", "redTeams": ["A"], "blueTeams": ["C"], "redScore": 50, "blueScore": 20},
        {"matchNum": 3, "round": "QUAL", "redTeams": ["B"], "blueTeams": ["C"], "redScore": 30, "blueScore": 20},
    ]
    ratings = Predictor._solve_opr(matches)
    # This system is exactly solvable: A=50, B=30, C=20.
    assert ratings["A"] == pytest.approx(50.0, abs=1e-6)
    assert ratings["B"] == pytest.approx(30.0, abs=1e-6)
    assert ratings["C"] == pytest.approx(20.0, abs=1e-6)


async def test_combined_score_percentile_threshold_top_x_pct():
    matches = [
        {"redScore": s, "blueScore": 0} for s in [10, 20, 30, 40, 100]
    ]
    # Top 20% threshold -> 80th percentile of [10,20,30,40,100] = 60.8 (numpy default interpolation)
    threshold = Predictor._combined_score_percentile_threshold(matches, 20)
    assert threshold == pytest.approx(float(np.percentile([10, 20, 30, 40, 100], 80)))


async def test_predict_match_flags_high_potential_above_threshold(predictor):
    predictor._opr_ratings = {"1111A": 60.0, "2222B": 50.0, "3333C": 10.0, "4444D": 5.0}
    predictor._combined_score_threshold = 100.0

    high = predictor.predict_match(["1111A"], ["2222B"])  # 60 + 50 = 110 >= 100
    assert high["high_potential"] is True

    low = predictor.predict_match(["3333C"], ["4444D"])  # 10 + 5 = 15 < 100
    assert low["high_potential"] is False


async def test_predict_match_unknown_teams_default_to_zero_rating(predictor):
    predictor._opr_ratings = {"1111A": 60.0}
    predictor._combined_score_threshold = 1000.0
    result = predictor.predict_match(["1111A"], ["unknown_team"])
    assert result["predicted_red"] == 60.0
    assert result["predicted_blue"] == 0.0
    assert result["high_potential"] is False


async def test_get_flag_returns_none_for_unknown_match():
    p = Predictor()
    assert p.get_flag("1:999") is None


async def test_full_refresh_and_predict_flow_end_to_end(predictor, seeded_matches):
    await predictor._refresh_threshold_setting()
    await predictor._refresh_opr()

    assert set(predictor._opr_ratings.keys()) == set(TEST_TEAMS)

    result = predictor.predict_match(["1111A", "2222B"], ["3333C", "4444D"])
    assert "high_potential" in result
    assert isinstance(result["high_potential"], bool)


async def test_high_potential_threshold_pct_read_from_system_settings(predictor, session_factory):
    async with session_factory() as session:
        setting = await session.get(SystemSetting, "predictor")
        original = dict(setting.value) if setting else None
        setting.value = {"high_potential_threshold_pct": 42}
        await session.commit()

    try:
        await predictor._refresh_threshold_setting()
        assert predictor._threshold_pct == 42.0
    finally:
        async with session_factory() as session:
            setting = await session.get(SystemSetting, "predictor")
            if original is not None:
                setting.value = original
                await session.commit()


async def test_handle_field_match_assigned_publishes_and_caches_flag(predictor, real_redis, mocker):
    predictor._opr_ratings = {"1111A": 60.0, "2222B": 50.0, "3333C": 1.0, "4444D": 1.0}
    predictor._combined_score_threshold = 50.0

    publish_spy = mocker.patch.object(real_redis, "publish", new_callable=mocker.AsyncMock)

    event = EventBusMessage(
        entity_id="vex_tm.division_1", entity_tags=[], type="fieldMatchAssigned",
        timestamp=time.time(),
        payload={"redTeams": ["1111A"], "blueTeams": ["2222B"], "matchNum": 7, "divisionId": 3, "fieldID": 1, "round": "QUAL"},
    )
    await predictor._handle_raw_message(event.model_dump_json())

    mid = match_id_for(3, 7)
    assert predictor.get_flag(mid) is True
    publish_spy.assert_awaited_once()

    published_payload = publish_spy.await_args.args[1]
    assert '"type":"match_prediction"' in published_payload or '"type": "match_prediction"' in published_payload


async def test_predicted_scores_never_persisted_to_team_profiles(
    predictor, seeded_matches, session_factory
):
    """CRITICAL leakage check (§5.12): running a full predict cycle must
    never write predicted_red/predicted_blue into any Postgres row — the
    predictor only ever writes to its own Redis cache keys and the internal
    event bus, and TeamProfile rows are owned exclusively by the scraper."""
    await predictor._refresh_threshold_setting()
    await predictor._refresh_opr()
    predictor.predict_match(TEST_TEAMS[:2], TEST_TEAMS[2:])

    async with session_factory() as session:
        for team in TEST_TEAMS:
            row = await session.get(TeamProfile, team)
            assert row is not None
            # cached_stats is scraper-owned and must contain no predictor keys.
            stats = row.cached_stats or {}
            assert "predicted_red" not in stats
            assert "predicted_blue" not in stats
            assert "high_potential" not in stats


async def test_get_flag_is_synchronous_and_returns_plain_bool(predictor):
    """`get_flag` is a sync method per the frozen §C.2 public API — verify it
    can be called without awaiting and returns a bare bool, so a Wave 3/4
    router can safely expose exactly this (and nothing else) to the UI."""
    predictor._flags["1:1"] = True
    flag = predictor.get_flag("1:1")
    assert flag is True
    assert isinstance(flag, bool)
