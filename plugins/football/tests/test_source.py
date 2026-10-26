"""ESPNSource: host fallback, cadence, backoff, stale-on-failure, scoring
baseline, possession hold, schedule/bye lookup. No network: a fake
aiohttp-shaped session and injected clocks."""

import copy
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from led_ticker_football._source import (
    HOSTS,
    IDLE_INTERVAL,
    KICKOFF_INTERVAL,
    LIVE_INTERVAL,
    MIN_INTERVAL,
    PATH,
    PREGAME_INTERVAL,
    SCHEDULE_INTERVAL,
    ESPNSource,
    shared_source,
)

FIX = Path(__file__).parent / "fixtures"
TZ = ZoneInfo("America/New_York")
SB = [f"{h}{PATH}/scoreboard" for h in HOSTS]
LIVE_ID = "401873099"


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


# Mon 2026-10-26 11:30 local (15:30 UTC): the week-7 payload's capture time.
NOW = datetime(2026, 10, 26, 15, 30, tzinfo=UTC)


def week_with(*events):
    body = fx("scoreboard_week7")
    body["events"] = list(events)
    return body


def live_event(away=20, home=17, status=None, situation="keep"):
    e = copy.deepcopy(fx("event_live"))
    comps = e["competitions"][0]["competitors"]
    for k in comps:
        k["score"] = str(home if k["homeAway"] == "home" else away)
    if status is not None:
        e["status"] = status
        e["competitions"][0]["status"] = status
    if situation is None:
        e["competitions"][0].pop("situation", None)
    elif situation != "keep":
        e["competitions"][0]["situation"] = situation
    return e


def make(routes, teams=("PHI",), all_games=False, hold=24, wall=NOW):
    session = FakeSession(routes)
    clock = Clock()
    state = {"wall": wall}
    s = ESPNSource(session, clock=clock, wall=lambda: state["wall"])
    s.want(teams=set(teams), all_games=all_games, tz=TZ, final_hold_hours=hold)
    return s, session, clock, state


async def test_poll_parses_week():
    s, session, _, _ = make(
        {SB[0]: (200, fx("scoreboard_week7"))}, teams=("PHI", "NYG")
    )
    snap = await s.poll()
    assert snap.stale is False
    assert snap.error is None
    assert snap.week == 7
    assert snap.bye_teams == frozenset({"BUF", "LAC", "WSH", "JAX"})
    # DAL @ PHI (pre) and NYG @ HOU (final) are wanted; NE @ CHI is not.
    assert set(snap.games) == {"401873009", "401873016"}
    assert session.urls[0] == SB[0]


async def test_host_fallback_on_403():
    s, session, _, _ = make(
        {SB[0]: (403, {}), SB[1]: (200, fx("scoreboard_week7"))}, teams=("PHI",)
    )
    snap = await s.poll()
    assert snap.stale is False
    assert session.urls == [SB[0], SB[1]]
    assert "401873009" in snap.games


async def test_both_hosts_fail_is_stale():
    s, session, clock, _ = make({SB[0]: (403, {}), SB[1]: OSError("boom")})
    snap = await s.poll()
    assert snap.stale is True
    assert snap.error is not None
    assert "HTTP 403" in snap.error or "network" in snap.error
    assert session.urls == [SB[0], SB[1]]
    assert s.next_delay() == 2 * IDLE_INTERVAL
    # Gated: the next poll inside the backoff window makes no request.
    await s.poll()
    assert len(session.urls) == 2


async def test_malformed_payload_keeps_last_games():
    s, session, clock, _ = make({SB[0]: (200, fx("scoreboard_week7"))})
    snap = await s.poll()
    assert "401873009" in snap.games
    session.routes[SB[0]] = (200, {"events": "nope"})
    clock.advance()
    snap = await s.poll()
    assert snap.stale is True
    assert "401873009" in snap.games


def _sched(start_utc: datetime, gid="401873009"):
    e = copy.deepcopy(
        next(x for x in fx("scoreboard_week7")["events"] if x["id"] == gid)
    )
    e["date"] = start_utc.strftime("%Y-%m-%dT%H:%MZ")
    e["competitions"][0]["date"] = e["date"]
    return e


async def test_cadence_ladder():
    # Live → LIVE_INTERVAL.
    s, _, _, _ = make({SB[0]: (200, week_with(live_event()))})
    await s.poll()
    assert s.next_delay() == LIVE_INTERVAL
    # Kickoff in 20 min → KICKOFF_INTERVAL.
    s, _, _, _ = make({SB[0]: (200, week_with(_sched(NOW + timedelta(minutes=20))))})
    await s.poll()
    assert s.next_delay() == KICKOFF_INTERVAL
    # Later today → PREGAME_INTERVAL.
    s, _, _, _ = make({SB[0]: (200, week_with(_sched(NOW + timedelta(hours=6))))})
    await s.poll()
    assert s.next_delay() == PREGAME_INTERVAL
    # Later this week → IDLE_INTERVAL.
    s, _, _, _ = make({SB[0]: (200, week_with(_sched(NOW + timedelta(days=3))))})
    await s.poll()
    assert s.next_delay() == IDLE_INTERVAL
    # Faster live cadence on request, floored at MIN_INTERVAL.
    s, _, _, _ = make({SB[0]: (200, week_with(live_event()))})
    s.want(teams={"PHI"}, all_games=False, tz=TZ, final_hold_hours=24, live_interval=10)
    await s.poll()
    assert s.next_delay() == 10
    s, _, _, _ = make({SB[0]: (200, week_with(live_event()))})
    s.want(teams={"PHI"}, all_games=False, tz=TZ, final_hold_hours=24, live_interval=5)
    await s.poll()
    assert s.next_delay() == MIN_INTERVAL


async def test_first_sight_scores_are_baseline():
    s, _, _, _ = make({SB[0]: (200, week_with(live_event()))})
    await s.poll()
    assert s.plays_after_baseline(LIVE_ID) == ()


async def test_touchdown_detected_from_delta():
    s, session, clock, _ = make({SB[0]: (200, week_with(live_event()))})
    await s.poll()
    session.routes[SB[0]] = (200, week_with(live_event(away=26)))
    clock.advance()
    await s.poll()
    plays = s.plays_after_baseline(LIVE_ID)
    assert len(plays) == 1
    assert plays[0].kind == "TD"
    assert plays[0].team == "PHI"
    assert plays[0].key == f"{LIVE_ID}:26:17"
    assert plays[0].text == "JALEN HURTS 12 YD RUSH"


async def test_pat_follow_up_merges_into_touchdown():
    s, session, clock, _ = make({SB[0]: (200, week_with(live_event()))})
    await s.poll()
    session.routes[SB[0]] = (200, week_with(live_event(away=26)))
    clock.advance()
    await s.poll()
    session.routes[SB[0]] = (200, week_with(live_event(away=27)))
    clock.advance()
    await s.poll()
    plays = s.plays_after_baseline(LIVE_ID)
    assert len(plays) == 1
    assert plays[0].extra == "+PAT"
    assert plays[0].key == f"{LIVE_ID}:27:17"
    assert plays[0].away_score == 27
    assert plays[0].text == "JALEN HURTS 12 YD RUSH"


async def test_negative_delta_is_a_correction():
    s, session, clock, _ = make({SB[0]: (200, week_with(live_event()))})
    await s.poll()
    session.routes[SB[0]] = (200, week_with(live_event(away=27)))
    clock.advance()
    await s.poll()
    assert len(s.plays_after_baseline(LIVE_ID)) == 1
    session.routes[SB[0]] = (200, week_with(live_event(away=20)))
    clock.advance()
    snap = await s.poll()
    assert snap.stale is False
    assert s.plays_after_baseline(LIVE_ID) == ()
    # A fresh touchdown after the correction celebrates again.
    session.routes[SB[0]] = (200, week_with(live_event(away=27)))
    clock.advance()
    await s.poll()
    assert len(s.plays_after_baseline(LIVE_ID)) == 1


HALFTIME = {
    "clock": 0.0,
    "displayClock": "0:00",
    "period": 2,
    "type": {
        "id": "23",
        "name": "STATUS_HALFTIME",
        "state": "in",
        "completed": False,
        "description": "Halftime",
        "detail": "Halftime",
        "shortDetail": "Halftime",
    },
}


async def test_possession_held_across_dead_ball():
    s, session, clock, _ = make({SB[0]: (200, week_with(live_event()))})
    snap = await s.poll()
    assert snap.games[LIVE_ID].situation.possession == "NYG"
    dead = fx("event_live_deadball")["competitions"][0]["situation"]
    session.routes[SB[0]] = (200, week_with(live_event(situation=dead)))
    clock.advance()
    snap = await s.poll()
    sit = snap.games[LIVE_ID].situation
    assert sit.possession == "NYG"
    assert sit.down_distance == ""
    assert sit.red_zone is True
    session.routes[SB[0]] = (
        200,
        week_with(live_event(status=HALFTIME, situation=None)),
    )
    clock.advance()
    snap = await s.poll()
    assert snap.games[LIVE_ID].situation is None
    # Back in play with no possession key after halftime: nothing held over.
    session.routes[SB[0]] = (200, week_with(live_event(situation=dead)))
    clock.advance()
    snap = await s.poll()
    assert snap.games[LIVE_ID].situation.possession is None


async def test_vanished_game_keeps_state_until_hold():
    s, session, clock, state = make(
        {SB[0]: (200, fx("scoreboard_week7"))}, teams=("NYG",), hold=24
    )
    snap = await s.poll()
    assert "401873016" in snap.games
    session.routes[SB[0]] = (200, week_with())
    clock.advance()
    snap = await s.poll()
    assert "401873016" in snap.games  # never inferred away
    assert snap.games["401873016"].state == "final"
    state["wall"] = NOW + timedelta(hours=25)
    clock.advance()
    snap = await s.poll()
    assert "401873016" not in snap.games


async def test_next_game_from_schedule_for_bye_team():
    sched_url = f"{HOSTS[0]}{PATH}/teams/PHI/schedule"
    body = fx("scoreboard_week7")
    body["week"]["number"] = 10  # PHI's bye week in the schedule fixture
    body["events"] = [e for e in body["events"] if e["id"] != "401873009"]
    s, session, clock, _ = make(
        {SB[0]: (200, body), sched_url: (200, fx("schedule_phi"))}, teams=("PHI",)
    )
    snap = await s.poll()
    assert "PHI" in snap.next_games
    assert snap.next_games["PHI"].game_id == "401873170"
    assert snap.next_games["PHI"].state == "future"
    assert "PHI" in snap.bye_teams
    assert session.urls.count(sched_url) == 1
    clock.advance(SCHEDULE_INTERVAL / 2)
    await s.poll()
    assert session.urls.count(sched_url) == 1
    clock.advance(SCHEDULE_INTERVAL)
    await s.poll()
    assert session.urls.count(sched_url) == 2


async def test_week_pre_game_beats_schedule():
    s, session, _, _ = make({SB[0]: (200, fx("scoreboard_week7"))}, teams=("DAL",))
    snap = await s.poll()
    assert "401873009" in snap.games
    assert "DAL" not in snap.next_games
    assert not any("/schedule" in u for u in session.urls)


async def test_shared_source_is_per_session():
    a, b = object(), object()
    assert shared_source(a) is shared_source(a)
    assert shared_source(a) is not shared_source(b)


class _Boom:
    def get(self, *a, **k):
        raise RuntimeError("session exploded")


async def test_poll_never_raises():
    s = ESPNSource(_Boom(), clock=Clock(), wall=lambda: NOW)
    s.want(teams={"PHI"}, all_games=False, tz=TZ, final_hold_hours=24)
    snap = await s.poll()
    assert snap.stale is True
    assert "RuntimeError" in (snap.error or "")


@pytest.mark.parametrize("mode_all", [False, True])
async def test_all_games_interest(mode_all):
    s, _, _, _ = make(
        {SB[0]: (200, fx("scoreboard_week7"))}, teams=(), all_games=mode_all
    )
    snap = await s.poll()
    assert (len(snap.games) == 3) is mode_all


async def test_schedule_bye_flag_persists_across_polls():
    """A team on bye per the schedule's `byeWeek` but missing from the
    scoreboard's `teamsOnBye` stays flagged on every poll, not just the one
    that fetched the schedule."""
    sched_url = f"{HOSTS[0]}{PATH}/teams/PHI/schedule"
    body = fx("scoreboard_week7")
    body["week"]["number"] = 10
    body["week"]["teamsOnBye"] = []
    body["events"] = [e for e in body["events"] if e["id"] != "401873009"]
    s, session, clock, _ = make(
        {SB[0]: (200, body), sched_url: (200, fx("schedule_phi"))}, teams=("PHI",)
    )
    snap = await s.poll()
    assert "PHI" in snap.bye_teams
    clock.advance(IDLE_INTERVAL + 1)
    snap = await s.poll()
    assert session.urls.count(sched_url) == 1
    assert "PHI" in snap.bye_teams


async def test_new_score_closes_a_stale_open_touchdown():
    """TD with a missed PAT, then a FG, then +2: the +2 is a SAFETY, not the
    old touchdown's two-point conversion."""
    s, session, clock, _ = make({SB[0]: (200, week_with(live_event()))})
    await s.poll()
    for away in (26, 29, 31):
        session.routes[SB[0]] = (200, week_with(live_event(away=away)))
        clock.advance()
        await s.poll()
    plays = s.plays_after_baseline(LIVE_ID)
    assert [(p.kind, p.extra) for p in plays] == [
        ("TD", ""),
        ("FG", ""),
        ("SAFETY", ""),
    ]
