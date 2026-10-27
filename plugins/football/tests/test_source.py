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
    assert s.next_delay() == 2 * LIVE_INTERVAL  # nothing ever loaded: retry soon
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


def _situation(possession, dd="", red=False):
    """A real-shaped `situation`: the text fields exist only on a live down."""
    sit = {
        "possession": possession,
        "down": 1 if dd else -1,
        "distance": 10 if dd else 0,
        "yardLine": 50,
        "isRedZone": red,
        "homeTimeouts": 3,
        "awayTimeouts": 3,
    }
    if dd:
        sit["shortDownDistanceText"] = dd
        sit["possessionText"] = "NYG 45"
    return sit


PHI_ID, NYG_ID = "21", "19"


async def test_pat_follow_up_merges_into_touchdown():
    s, session, clock, _ = make({SB[0]: (200, week_with(live_event()))})
    await s.poll()
    session.routes[SB[0]] = (200, week_with(live_event(away=26)))
    clock.advance()
    await s.poll()
    # The try: the scoring team still has the ball, no live down yet.
    session.routes[SB[0]] = (
        200,
        week_with(live_event(away=27, situation=_situation(PHI_ID))),
    )
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
    assert sit.red_zone is False  # red is for a live down only
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


async def test_schedule_fetched_while_a_final_is_held():
    """The next-game card must be ready the moment the hold expires, which
    happens between polls at the idle cadence: fetch the schedule while the
    final is still held, not an hour after it leaves."""
    sched_url = f"{HOSTS[0]}{PATH}/teams/NYG/schedule"
    s, session, _, _ = make(
        {SB[0]: (200, fx("scoreboard_week7")), sched_url: (200, fx("schedule_phi"))},
        teams=("NYG",),
    )
    snap = await s.poll()
    assert snap.games["401873016"].state == "final"  # NYG's held final
    assert session.urls.count(sched_url) == 1


async def test_other_side_correction_keeps_open_touchdown():
    """A correction to the OTHER team's score must not close this team's
    touchdown: its extra point would then arrive with nothing to attach to."""
    s, session, clock, _ = make({SB[0]: (200, week_with(live_event()))})
    await s.poll()
    phi = _situation(PHI_ID)
    for away, home, sit in ((26, 17, phi), (26, 14, phi), (27, 14, phi)):
        session.routes[SB[0]] = (
            200,
            week_with(live_event(away=away, home=home, situation=sit)),
        )
        clock.advance()
        await s.poll()
    plays = s.plays_after_baseline(LIVE_ID)
    assert [(p.kind, p.extra) for p in plays] == [("TD", "+PAT")]


async def test_open_touchdown_closes_when_opponent_has_a_live_down():
    """A TD whose try failed stays open only until the try is over: once the
    other team runs a live down, a later +2 by this team is a SAFETY."""
    s, session, clock, _ = make({SB[0]: (200, week_with(live_event()))})
    await s.poll()
    polls = (
        (26, "keep"),
        (26, _situation(NYG_ID, dd="1st & 10")),
        (28, _situation(PHI_ID)),
    )
    for away, sit in polls:
        session.routes[SB[0]] = (200, week_with(live_event(away=away, situation=sit)))
        clock.advance()
        await s.poll()
    plays = s.plays_after_baseline(LIVE_ID)
    assert [(p.kind, p.extra) for p in plays] == [("TD", ""), ("SAFETY", "")]


async def test_first_poll_failure_backs_off_from_live_interval():
    """Nothing has ever loaded, so the cadence says IDLE (1 h): a Pi that
    boots before the network is up on game day must not wait 2 h to retry."""
    s, _, clock, _ = make({})
    snap = await s.poll()
    assert snap.stale is True
    assert s.next_delay() == 2 * LIVE_INTERVAL
    clock.advance(s.next_delay())
    await s.poll()
    assert s.next_delay() == 4 * LIVE_INTERVAL


def _with_period(event, period, status_name="STATUS_IN_PROGRESS"):
    for st in (event["status"], event["competitions"][0]["status"]):
        st["period"] = period
        st["type"]["name"] = status_name
    return event


async def test_possession_not_held_across_a_period_change():
    s, session, clock, _ = make({SB[0]: (200, week_with(live_event()))})
    await s.poll()
    dead = fx("event_live_deadball")["competitions"][0]["situation"]
    session.routes[SB[0]] = (
        200,
        week_with(_with_period(live_event(situation=dead), 5)),
    )
    clock.advance()
    snap = await s.poll()
    assert snap.games[LIVE_ID].situation.possession is None


async def test_possession_not_held_at_end_of_period():
    s, session, clock, _ = make({SB[0]: (200, week_with(live_event()))})
    await s.poll()
    dead = fx("event_live_deadball")["competitions"][0]["situation"]
    ev = _with_period(live_event(situation=dead), 4, "STATUS_END_PERIOD")
    session.routes[SB[0]] = (200, week_with(ev))
    clock.advance()
    snap = await s.poll()
    assert snap.games[LIVE_ID].situation.possession is None


async def test_open_touchdown_closes_on_a_period_change():
    s, session, clock, _ = make({SB[0]: (200, week_with(live_event()))})
    await s.poll()
    polls = (
        (26, 4, _situation(PHI_ID)),
        (26, 5, _situation(PHI_ID)),
        (28, 5, _situation(PHI_ID)),
    )
    for away, period, sit in polls:
        ev = _with_period(live_event(away=away, situation=sit), period)
        session.routes[SB[0]] = (200, week_with(ev))
        clock.advance()
        await s.poll()
    assert [(p.kind, p.extra) for p in s.plays_after_baseline(LIVE_ID)] == [
        ("TD", ""),
        ("SAFETY", ""),
    ]


async def test_own_live_down_keeps_the_touchdown_open():
    s, session, clock, _ = make({SB[0]: (200, week_with(live_event()))})
    await s.poll()
    polls = (
        (26, _situation(PHI_ID)),
        (26, _situation(PHI_ID, dd="1st & 10")),
        (27, _situation(PHI_ID)),
    )
    for away, sit in polls:
        session.routes[SB[0]] = (200, week_with(live_event(away=away, situation=sit)))
        clock.advance()
        await s.poll()
    assert [(p.kind, p.extra) for p in s.plays_after_baseline(LIVE_ID)] == [
        ("TD", "+PAT")
    ]


async def test_backoff_after_a_success_uses_the_cadence():
    s, session, clock, _ = make(
        {SB[0]: (200, week_with(_sched(NOW + timedelta(days=3))))}
    )
    await s.poll()
    assert s.next_delay() == IDLE_INTERVAL
    session.routes = {}
    clock.advance(IDLE_INTERVAL)
    await s.poll()
    assert s.next_delay() == 2 * IDLE_INTERVAL


async def test_schedule_failure_retries_on_the_next_poll():
    """One failed schedule fetch must not blank a bye-week team's card for
    the whole SCHEDULE_INTERVAL (6 h): retry at the next poll instead."""
    from led_ticker_football._source import SCHEDULE_RETRY

    sched_url = f"{HOSTS[0]}{PATH}/teams/NYG/schedule"
    s, session, clock, _ = make({SB[0]: (200, fx("scoreboard_week7"))}, teams=("NYG",))
    snap = await s.poll()
    assert "NYG" not in snap.next_games
    assert session.urls.count(sched_url) == 1
    clock.advance(SCHEDULE_RETRY - 1)
    await s.poll()  # inside the retry spacing: no second attempt yet
    assert session.urls.count(sched_url) == 1
    session.routes[sched_url] = (200, fx("schedule_phi"))
    clock.advance(IDLE_INTERVAL)
    snap = await s.poll()
    assert session.urls.count(sched_url) == 2
    assert "NYG" in snap.next_games


async def test_partial_payload_keeps_the_live_cadence():
    """ESPN occasionally answers with a week payload missing a live game (or
    `events: []`). The card keeps showing the live score, so polling must
    stay at the live cadence — not drop to the hourly idle rate unflagged."""
    s, session, clock, _ = make({SB[0]: (200, week_with(live_event()))})
    await s.poll()
    assert s.next_delay() == LIVE_INTERVAL
    session.routes[SB[0]] = (200, week_with())  # the game vanished for one poll
    clock.advance()
    snap = await s.poll()
    assert snap.stale is False and LIVE_ID in snap.games
    assert s.next_delay() == LIVE_INTERVAL
    assert "PHI" in s._playing()  # and no needless schedule fetch


async def test_schedule_retry_waits_longer_while_a_game_is_live():
    """A failing schedule fetch for a bye team must not stall every live
    poll: with a game live it retries every SCHEDULE_RETRY_LIVE, not 60 s,
    and with a short timeout."""
    from led_ticker_football._source import (
        SCHEDULE_RETRY,
        SCHEDULE_RETRY_LIVE,
        SCHEDULE_TIMEOUT,
    )

    sched_url = f"{HOSTS[0]}{PATH}/teams/DAL/schedule"
    s, session, clock, _ = make(
        {SB[0]: (200, week_with(live_event()))}, teams=("PHI", "DAL")
    )
    await s.poll()
    assert session.urls.count(sched_url) == 1
    sched_calls = [kw for url, kw in session.calls if url == sched_url]
    assert sched_calls[0]["timeout"].total == SCHEDULE_TIMEOUT
    clock.advance(SCHEDULE_RETRY + LIVE_INTERVAL)
    await s.poll()
    assert session.urls.count(sched_url) == 1  # not every minute under a live game
    clock.advance(SCHEDULE_RETRY_LIVE)
    await s.poll()
    assert session.urls.count(sched_url) == 2
