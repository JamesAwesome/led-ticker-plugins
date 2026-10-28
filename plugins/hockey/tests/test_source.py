"""NHLSource: cadence, backoff, stale-on-failure, landing gating, goal baseline.
No network: a fake aiohttp-shaped session and injected clocks."""

import copy
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from led_ticker_hockey import _source as src
from led_ticker_hockey._source import (
    IDLE_INTERVAL,
    LIVE_GRACE,
    LIVE_INTERVAL,
    MAX_BACKOFF,
    PREGAME_INTERVAL,
    NHLSource,
    shared_source,
)

FIX = Path(__file__).parent / "fixtures"
TZ = ZoneInfo("America/New_York")
BASE = "https://api-web.nhle.com"
LIVE_ID = 2026020101


def fx(name):
    return json.loads((FIX / f"{name}.json").read_text())


class FakeResp:
    def __init__(self, status=200, body=None):
        self.status = status
        self.body = body

    async def json(self):
        if isinstance(self.body, BaseException):
            raise self.body
        return self.body


class _Ctx:
    def __init__(self, resp):
        self.resp = resp

    async def __aenter__(self):
        if isinstance(self.resp, BaseException):
            raise self.resp
        return self.resp

    async def __aexit__(self, *exc):
        return False


class FakeSession:
    """URL -> (status, body) map; unmapped URLs 404."""

    def __init__(self, routes=None):
        self.routes = dict(routes or {})
        self.calls: list[tuple[str, dict]] = []

    def get(self, url, **kw):
        self.calls.append((url, kw))
        route = self.routes.get(url)
        if route is None:
            return _Ctx(FakeResp(404, {}))
        if isinstance(route, BaseException):
            return _Ctx(route)
        status, body = route
        return _Ctx(FakeResp(status, body))

    @property
    def urls(self):
        return [u for u, _ in self.calls]


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, s=1e6):
        self.t += s


# 2026-10-22 16:00 local (20:00 UTC)
NOON = datetime(2026, 10, 22, 20, 0, tzinfo=UTC)
TODAY = f"{BASE}/v1/score/2026-10-22"
YDAY = f"{BASE}/v1/score/2026-10-21"


def make(routes, teams=("PHI",), all_games=False, hold=6, wall=NOON):
    session = FakeSession(routes)
    clock = Clock()
    s = NHLSource(session, clock=clock, wall=lambda: wall)
    s.want(teams=set(teams), all_games=all_games, tz=TZ, final_hold_hours=hold)
    return s, session, clock


async def test_poll_parses_today():
    s, _, _ = make({TODAY: (200, fx("score_live"))})
    snap = await s.poll()
    assert snap.stale is False
    assert snap.error is None
    assert LIVE_ID in snap.games
    assert snap.games[LIVE_ID].away == "PHI"
    # TOR/MTL is not a wanted game
    assert 2026020102 not in snap.games


async def test_all_games_mode_keeps_every_game():
    s, _, _ = make({TODAY: (200, fx("score_live"))}, teams=(), all_games=True)
    snap = await s.poll()
    assert set(snap.games) == {LIVE_ID, 2026020102}


async def test_user_agent_and_timeout():
    s, session, _ = make({TODAY: (200, fx("score_live"))})
    await s.poll()
    _, kw = session.calls[0]
    assert kw["headers"]["User-Agent"].startswith("led-ticker-hockey")
    assert kw["timeout"].total == src.REQUEST_TIMEOUT


async def test_failure_keeps_last_good_and_marks_stale():
    s, session, clock = make({TODAY: (200, fx("score_live"))})
    await s.poll()
    session.routes[TODAY] = (500, {})
    clock.advance()
    snap = await s.poll()
    assert snap.stale is True
    assert snap.error
    assert LIVE_ID in snap.games
    session.routes[TODAY] = (200, fx("score_live"))
    clock.advance()
    snap = await s.poll()
    assert snap.stale is False
    assert snap.error is None


@pytest.mark.parametrize("body", ["nope", {"games": "x"}, None, [], {"games": [3]}])
async def test_malformed_body_never_raises(body):
    s, _, _ = make({TODAY: (200, body)})
    snap = await s.poll()
    if body == {"games": [3]}:
        assert snap.games == {}
    else:
        assert snap.stale is True


async def test_json_error_and_exception_never_raise():
    s, session, clock = make({TODAY: (200, ValueError("bad json"))})
    assert (await s.poll()).stale is True
    session.routes[TODAY] = RuntimeError("boom")
    clock.advance()
    assert (await s.poll()).stale is True
    session.routes[TODAY] = TimeoutError()
    clock.advance()
    assert (await s.poll()).stale is True


async def test_backoff_ladder():
    s, session, clock = make({TODAY: (200, fx("score_live"))})
    await s.poll()
    assert s.next_delay() == LIVE_INTERVAL
    session.routes[TODAY] = (500, {})
    seen = []
    for _ in range(12):
        clock.advance()
        await s.poll()
        seen.append(s.next_delay())
    assert seen[:3] == [30, 60, 120]
    assert seen[-1] == MAX_BACKOFF == 14400
    assert max(seen) == MAX_BACKOFF
    session.routes[TODAY] = (200, fx("score_live"))
    clock.advance()
    await s.poll()
    assert s.next_delay() == LIVE_INTERVAL


async def test_poll_gated_until_delay_elapses():
    s, session, clock = make({TODAY: (200, fx("score_live"))})
    await s.poll()
    n = len(session.calls)
    clock.advance(1)
    await s.poll()
    assert len(session.calls) == n
    clock.advance(LIVE_INTERVAL)
    await s.poll()
    assert len(session.calls) > n


async def test_cadence_live_vs_idle():
    s, _, _ = make({TODAY: (200, fx("score_live"))})
    await s.poll()
    assert s.next_delay() == LIVE_INTERVAL

    future = fx("score_future")
    s2, _, _ = make({TODAY: (200, future)})
    await s2.poll()
    assert s2.next_delay() == PREGAME_INTERVAL

    s3, _, _ = make({TODAY: (200, {"games": []})})
    await s3.poll()
    assert s3.next_delay() == IDLE_INTERVAL
    s4 = NHLSource(FakeSession())
    assert s4.next_delay() == IDLE_INTERVAL


async def test_landing_only_for_displayed_live():
    landing = f"{BASE}/v1/gamecenter/{LIVE_ID}/landing"
    s, session, clock = make(
        {TODAY: (200, fx("score_live")), landing: (200, fx("landing_pp"))}
    )
    await s.poll()
    assert landing not in session.urls
    clock.advance()
    s.note_displayed(object(), {LIVE_ID})
    snap = await s.poll()
    assert landing in session.urls
    sit = snap.games[LIVE_ID].situation
    assert sit is not None and sit.pp_team is not None


async def test_landing_failure_is_soft():
    landing = f"{BASE}/v1/gamecenter/{LIVE_ID}/landing"
    s, _, _ = make({TODAY: (200, fx("score_live")), landing: (500, {})})
    s.note_displayed(object(), {LIVE_ID})
    snap = await s.poll()
    assert snap.stale is False
    assert snap.games[LIVE_ID].situation is None


def _with_goals(n):
    body = fx("score_live")
    game = body["games"][0]
    base = game["goals"][0]
    goals = []
    for i in range(n):
        g = copy.deepcopy(base)
        g["timeInPeriod"] = f"{i + 1:02d}:00"
        g["playerId"] = 100 + i
        goals.append(g)
    game["goals"] = goals
    return body


async def test_first_sight_goals_are_baseline():
    s, session, clock = make({TODAY: (200, _with_goals(2))})
    await s.poll()
    assert s.goals_after_baseline(LIVE_ID) == ()
    session.routes[TODAY] = (200, _with_goals(3))
    clock.advance()
    snap = await s.poll()
    third = snap.games[LIVE_ID].goals[2]
    assert s.goals_after_baseline(LIVE_ID) == (third,)
    # non-consuming: repeat reads (other widgets) see the same thing
    assert s.goals_after_baseline(LIVE_ID) == (third,)
    assert s.goals_after_baseline(999) == ()


async def test_disallowed_goal_vanishes_from_result():
    s, session, clock = make({TODAY: (200, _with_goals(2))})
    await s.poll()
    session.routes[TODAY] = (200, _with_goals(3))
    clock.advance()
    await s.poll()
    assert len(s.goals_after_baseline(LIVE_ID)) == 1
    session.routes[TODAY] = (200, _with_goals(2))
    clock.advance()
    await s.poll()
    assert s.goals_after_baseline(LIVE_ID) == ()
    # baseline goal removed and returned is still baseline
    session.routes[TODAY] = (200, _with_goals(1))
    clock.advance()
    await s.poll()
    session.routes[TODAY] = (200, _with_goals(2))
    clock.advance()
    await s.poll()
    assert s.goals_after_baseline(LIVE_ID) == ()


async def test_note_displayed_union_across_consumers():
    both = fx("score_live")
    both["games"][1]["gameState"] = "LIVE"
    both["games"][1]["awayTeam"]["abbrev"] = "NYI"
    both["games"][1]["homeTeam"]["abbrev"] = "TOR"
    other = both["games"][1]["id"]
    l1 = f"{BASE}/v1/gamecenter/{LIVE_ID}/landing"
    l2 = f"{BASE}/v1/gamecenter/{other}/landing"
    s, session, clock = make(
        {TODAY: (200, both), l1: (200, fx("landing_pp")), l2: (200, fx("landing_pp"))},
        teams=("PHI", "NYI"),
    )
    a, b = object(), object()
    await s.poll()
    n_score = session.urls.count(TODAY)
    for _ in range(3):  # alternate, no clock movement
        s.note_displayed(a, {LIVE_ID})
        s.note_displayed(b, {other})
    await s.poll()  # gate reopened once by the union growing
    s.note_displayed(a, {LIVE_ID})
    s.note_displayed(b, {other})
    await s.poll()
    assert session.urls.count(TODAY) == n_score + 1
    assert l1 in session.urls and l2 in session.urls


async def test_first_poll_failure_backs_off_from_live_interval():
    """Nothing has ever loaded, so the cadence says IDLE (1 h): a Pi that
    boots before the network is up on game day must not wait 2 h to retry."""
    s, _, clock = make({TODAY: (500, {})})
    snap = await s.poll()
    assert snap.stale is True
    assert s.next_delay() == 2 * LIVE_INTERVAL
    clock.advance(s.next_delay())
    await s.poll()
    assert s.next_delay() == 4 * LIVE_INTERVAL


async def test_failure_after_first_success_backs_off_from_cadence():
    s, session, clock = make({TODAY: (200, {"games": []})})
    await s.poll()
    session.routes[TODAY] = (500, {})
    clock.advance()
    await s.poll()
    assert s.next_delay() == 2 * IDLE_INTERVAL


@pytest.mark.parametrize("hold", [0, 6])
async def test_partial_payload_keeps_the_live_cadence(hold):
    """The feed occasionally answers without a live game. The card keeps
    showing it live, so polling must stay live, not drop to hourly. Holds
    at every final_hold_hours, 0 included."""
    now = [NOON]
    session = FakeSession({TODAY: (200, fx("score_live"))})
    clock = Clock()
    s = NHLSource(session, clock=clock, wall=lambda: now[0])
    s.want(teams={"PHI"}, all_games=False, tz=TZ, final_hold_hours=hold)
    await s.poll()
    assert s.next_delay() == LIVE_INTERVAL
    session.routes[TODAY] = (200, {"games": []})  # the game vanished for one poll
    session.routes[YDAY] = (200, {"games": []})
    now[0] += timedelta(seconds=20)
    clock.advance(20)
    snap = await s.poll()
    assert snap.stale is False and LIVE_ID in snap.games
    assert s.next_delay() == LIVE_INTERVAL
    assert "PHI" in s._playing()


async def test_hold_zero_live_game_survives_midnight():
    """A live game still running at 00:00:10 local is fetched from
    yesterday's feed even at hold 0, and kept live."""
    now = [NOON]
    session = FakeSession({TODAY: (200, fx("score_live"))})
    clock = Clock()
    s = NHLSource(session, clock=clock, wall=lambda: now[0])
    s.want(teams={"PHI"}, all_games=False, tz=TZ, final_hold_hours=0)
    await s.poll()
    now[0] = datetime(2026, 10, 23, 4, 0, 10, tzinfo=UTC)  # 00:00:10 local
    session.routes[YDAY.replace("10-21", "10-22")] = (200, fx("score_live"))
    session.routes[f"{BASE}/v1/score/2026-10-23"] = (200, {"games": []})
    clock.advance()
    snap = await s.poll()
    assert YDAY.replace("10-21", "10-22") in session.urls[1:]
    assert snap.games[LIVE_ID].state == "live"
    assert s.next_delay() == LIVE_INTERVAL


@pytest.mark.parametrize("hold", [0, 6])
async def test_partial_payload_survives_yesterday_feed_failure(hold):
    """The yesterday fetch a missing live game triggers is soft: its failure
    must not stale the poll or discard today's good payload."""
    now = [NOON]
    session = FakeSession({TODAY: (200, fx("score_live"))})
    clock = Clock()
    s = NHLSource(session, clock=clock, wall=lambda: now[0])
    s.want(teams={"PHI"}, all_games=False, tz=TZ, final_hold_hours=hold)
    await s.poll()
    session.routes[TODAY] = (200, {"games": []})
    session.routes[YDAY] = (503, {})
    now[0] += timedelta(seconds=20)
    clock.advance(20)
    snap = await s.poll()
    assert YDAY in session.urls
    assert snap.stale is False and LIVE_ID in snap.games
    assert s.next_delay() == LIVE_INTERVAL


async def test_partial_payload_keeps_team_out_of_next_game_lookup():
    s, session, clock = make({TODAY: (200, fx("score_live"))})
    await s.poll()
    session.routes[TODAY] = (200, {"games": []})
    session.routes[YDAY] = (200, {"games": []})
    clock.advance(20)
    n = len(session.calls)
    await s.poll()
    assert not [u for u in session.urls[n:] if "/club-schedule" in u]


async def test_grace_expires_for_a_live_game_missing_too_long():
    now = [NOON]
    session = FakeSession({TODAY: (200, fx("score_live"))})
    clock = Clock()
    s = NHLSource(session, clock=clock, wall=lambda: now[0])
    s.want(teams={"PHI"}, all_games=False, tz=TZ, final_hold_hours=6)
    await s.poll()
    session.routes[TODAY] = (200, {"games": []})
    session.routes[YDAY] = (200, {"games": []})
    now[0] = NOON + timedelta(seconds=LIVE_GRACE + 1)
    clock.advance()
    snap = await s.poll()
    assert LIVE_ID in snap.games  # still inside the final hold
    assert s.next_delay() == IDLE_INTERVAL


async def test_next_games_with_all_games_widget_sharing():
    month = f"{BASE}/v1/club-schedule/NYI/month/now"
    s, _, _ = make(
        {TODAY: (200, {"games": []}), month: (200, fx("club_season_nyi"))},
        teams=("NYI",),
        all_games=True,
    )
    snap = await s.poll()
    assert snap.next_games["NYI"].game_id == 2026020115


async def test_next_game_falls_back_to_season():
    month = f"{BASE}/v1/club-schedule/NYI/month/now"
    season = f"{BASE}/v1/club-schedule-season/NYI/now"
    routes = {
        TODAY: (200, {"games": []}),
        month: (200, {"games": []}),
        season: (200, fx("club_season_nyi")),
    }
    s, session, clock = make(routes, teams=("NYI",))
    snap = await s.poll()
    assert session.urls.count(season) == 1
    assert snap.next_games["NYI"].game_id == 2026020115
    clock.advance(3600 * 2)
    await s.poll()
    assert session.urls.count(season) == 1
    clock.advance(src.SEASON_INTERVAL)
    await s.poll()
    assert session.urls.count(season) == 2


async def test_next_game_from_month_and_dropped_when_playing():
    month = f"{BASE}/v1/club-schedule/PHI/month/now"
    routes = {TODAY: (200, {"games": []}), month: (200, fx("club_week_phi"))}
    s, session, clock = make(routes)
    snap = await s.poll()
    assert snap.next_games["PHI"].game_id == 2026020115
    assert not any("club-schedule-season" in u for u in session.urls)
    session.routes[TODAY] = (200, fx("score_live"))
    clock.advance()
    snap = await s.poll()
    assert "PHI" not in snap.next_games


async def test_next_game_failure_is_soft():
    s, _, _ = make({TODAY: (200, {"games": []})}, teams=("PHI",))
    snap = await s.poll()
    assert snap.stale is False
    assert snap.next_games == {}


async def test_yesterday_fetched_inside_hold_window():
    early = datetime(2026, 10, 22, 4, 30, tzinfo=UTC)  # 00:30 EDT
    s, session, _ = make(
        {TODAY: (200, {"games": []}), YDAY: (200, fx("score_final_ot"))}, wall=early
    )
    snap = await s.poll()
    assert YDAY in session.urls and TODAY in session.urls
    assert 2026020088 in snap.games
    # not in the window -> yesterday is not requested
    s2, session2, _ = make({TODAY: (200, {"games": []})})
    await s2.poll()
    assert YDAY not in session2.urls


async def test_vanished_game_kept_until_hold_expires():
    s, session, clock = make({TODAY: (200, fx("score_live"))})
    await s.poll()
    session.routes[TODAY] = (200, {"games": []})
    session.routes[YDAY] = (200, {"games": []})
    clock.advance()
    snap = await s.poll()
    g = snap.games[LIVE_ID]
    assert g.state == "live"  # never inferred final


async def test_vanished_game_dropped_after_hold():
    now = [NOON]
    session = FakeSession({TODAY: (200, fx("score_live"))})
    clock = Clock()
    s = NHLSource(session, clock=clock, wall=lambda: now[0])
    s.want(teams={"PHI"}, all_games=False, tz=TZ, final_hold_hours=1)
    await s.poll()
    session.routes[TODAY] = (200, {"games": []})
    session.routes[YDAY] = (200, {"games": []})
    now[0] = datetime(2026, 10, 22, 21, 30, tzinfo=UTC)
    clock.advance()
    snap = await s.poll()
    assert LIVE_ID not in snap.games


async def test_want_merges_interest():
    session = FakeSession({TODAY: (200, fx("score_live"))})
    clock = Clock()
    s = NHLSource(session, clock=clock, wall=lambda: NOON)
    s.want(teams={"TOR"}, all_games=False, tz=TZ, final_hold_hours=2)
    s.want(teams={"PHI"}, all_games=False, tz=TZ, final_hold_hours=6)
    snap = await s.poll()
    assert set(snap.games) == {LIVE_ID, 2026020102}


def test_shared_source_is_per_session_and_capped():
    sessions = [FakeSession() for _ in range(9)]
    first = shared_source(sessions[0])
    assert shared_source(sessions[0]) is first
    for sess in sessions[1:]:
        shared_source(sess)
    assert len(src._SHARED_SOURCES) == 8
    assert id(sessions[0]) not in src._SHARED_SOURCES
    assert shared_source(sessions[0]) is not first


async def test_polled_at_is_wall_epoch_not_monotonic():
    """Renderers tick clocks off `time.time()`; `polled_at` must share it."""
    month = f"{BASE}/v1/club-schedule/BOS/month/now"
    routes = {TODAY: (200, fx("score_live")), month: (200, fx("club_week_phi"))}
    s, _, _ = make(routes, teams=("PHI", "BOS"))
    snap = await s.poll()
    assert snap.games[LIVE_ID].polled_at == NOON.timestamp()
    assert snap.next_games["BOS"].polled_at == NOON.timestamp()


# ----------------------------------------- next game vs finals (C1, M2)

MONTH_PHI = f"{BASE}/v1/club-schedule/PHI/month/now"


def _select(snap, wall, hold=6):
    from led_ticker_hockey.scores import select_stories

    return select_stories(
        snap.games,
        snap.next_games,
        mode="teams",
        teams=["PHI"],
        max_games=8,
        now_wall=wall.timestamp(),
        final_hold_hours=hold,
        tz=TZ,
    )


async def test_next_game_returns_after_final_hold():
    # The final lingers in the source (last seen < hold ago) but is past
    # select_stories' hold: the team must fall back to its next game.
    final = fx("score_final_ot")
    final["games"][0]["startTimeUTC"] = "2026-10-22T17:00:00Z"
    wall = datetime(2026, 10, 23, 2, 0, tzinfo=UTC)  # hold ended 01:30Z
    routes = {
        f"{BASE}/v1/score/2026-10-22": (200, final),
        f"{BASE}/v1/score/2026-10-21": (200, {"games": []}),
        MONTH_PHI: (200, fx("club_week_phi")),
    }
    s, _, _ = make(routes, wall=wall)
    snap = await s.poll()
    assert 2026020088 in snap.games  # still held by the source
    picks = _select(snap, wall)
    assert [g.game_id for g in picks] == [2026020115]


async def test_final_inside_hold_still_wins_over_next():
    final = fx("score_final_ot")
    final["games"][0]["startTimeUTC"] = "2026-10-22T17:00:00Z"
    wall = datetime(2026, 10, 22, 21, 0, tzinfo=UTC)
    routes = {TODAY: (200, final), MONTH_PHI: (200, fx("club_week_phi"))}
    s, _, _ = make(routes, wall=wall)
    snap = await s.poll()
    assert [g.game_id for g in _select(snap, wall)] == [2026020088]


async def test_next_game_uses_shortest_widget_hold():
    # Two widgets share the source: hold 2 h and 6 h. Three hours after
    # the final the 2 h widget must still find the next game.
    final = fx("score_final_ot")
    final["games"][0]["startTimeUTC"] = "2026-10-22T14:30:00Z"  # ended 17:00Z
    routes = {TODAY: (200, final), MONTH_PHI: (200, fx("club_week_phi"))}
    s, _, _ = make(routes, hold=6)
    s.want(teams={"PHI"}, all_games=False, tz=TZ, final_hold_hours=2)
    snap = await s.poll()
    assert [g.game_id for g in _select(snap, NOON, hold=2)] == [2026020115]
    assert [g.game_id for g in _select(snap, NOON, hold=6)] == [2026020088]


async def test_post_midnight_game_shown_before_puck_drop():
    # In today's feed, but it starts after local midnight: not "later
    # today", so the card must come from the next-game lookup.
    future = fx("score_future")
    future["games"][0]["startTimeUTC"] = "2026-10-23T04:30:00Z"  # 00:30 local
    routes = {TODAY: (200, future), MONTH_PHI: (200, fx("club_week_phi"))}
    s, _, _ = make(routes)
    snap = await s.poll()
    assert _select(snap, NOON), "the tracked team has no card before puck drop"


async def test_update_interval_below_live_cadence_speeds_live_polls():
    s, _, _ = make({TODAY: (200, fx("score_live"))})
    s.want(teams={"PHI"}, all_games=False, tz=TZ, final_hold_hours=6, live_interval=12)
    await s.poll()
    assert s.next_delay() == 12
    s.want(teams={"PHI"}, all_games=False, tz=TZ, final_hold_hours=6, live_interval=30)
    assert s.next_delay() == 12  # union is the fastest ask
    s.want(teams={"PHI"}, all_games=False, tz=TZ, final_hold_hours=6, live_interval=3)
    assert s.next_delay() == src.MIN_INTERVAL  # floored


async def test_update_interval_does_not_change_idle_cadence():
    s, _, _ = make({TODAY: (200, {"games": []})})
    s.want(teams={"PHI"}, all_games=False, tz=TZ, final_hold_hours=6, live_interval=12)
    await s.poll()
    assert s.next_delay() == IDLE_INTERVAL
