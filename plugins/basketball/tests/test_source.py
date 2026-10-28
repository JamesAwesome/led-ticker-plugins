"""ESPNSource: host fallback, cadence, backoff, stale-on-failure, final-buzzer
baseline, yesterday feed, schedule lookup. No network: a fake aiohttp-shaped
session and injected clocks."""

import copy
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from led_ticker_basketball._models import FinalEvent
from led_ticker_basketball._source import (
    HOSTS,
    IDLE_INTERVAL,
    LIVE_INTERVAL,
    MIN_INTERVAL,
    PATH,
    PREGAME_INTERVAL,
    SCHEDULE_INTERVAL,
    SCHEDULE_RETRY,
    SCHEDULE_RETRY_LIVE,
    SCHEDULE_TIMEOUT,
    TIPOFF_INTERVAL,
    ESPNSource,
    shared_source,
)

FIX = Path(__file__).parent / "fixtures"
TZ = ZoneInfo("America/New_York")
SB = [f"{h}{PATH}/scoreboard" for h in HOSTS]
LIVE_ID = "401909089"
PRE_ID = "401909881"


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


# Wed 2026-10-28 14:00 local (18:00 UTC): the day payload's capture time.
NOW = datetime(2026, 10, 28, 18, 0, tzinfo=UTC)


def day(*events):
    return {"events": list(events)}


def _set_status(e, name, state, period=None, clock=None):
    comp = e["competitions"][0]
    status = {"type": {"name": name, "state": state}}
    status["type"]["detail"] = "Final" if state == "post" else "In Progress"
    if period is not None:
        status["period"] = period
    status["displayClock"] = clock or "0.0"
    e["status"] = status
    comp["status"] = status


def live_event(away=98, home=101, gid=LIVE_ID):
    e = copy.deepcopy(fx("event_live"))
    e["id"] = gid
    for k in e["competitions"][0]["competitors"]:
        k["score"] = str(home if k["homeAway"] == "home" else away)
    return e


def final_event_json(away=112, home=108, gid=LIVE_ID):
    e = live_event(away, home, gid)
    _set_status(e, "STATUS_FINAL", "post", period=4)
    return e


def sched(start_utc: datetime, gid=PRE_ID):
    e = copy.deepcopy(fx("scoreboard_20261028")["events"][0])
    e["id"] = gid
    e["date"] = start_utc.strftime("%Y-%m-%dT%H:%MZ")
    e["competitions"][0]["date"] = e["date"]
    return e


def make(routes, teams=("PHI",), all_games=False, hold=24, wall=NOW):
    session = FakeSession(routes)
    clock = Clock()
    state = {"wall": wall}
    s = ESPNSource(session, clock=clock, wall=lambda: state["wall"])
    s.want(teams=set(teams), all_games=all_games, tz=TZ, final_hold_hours=hold)
    return s, session, clock, state


async def test_poll_parses_today():
    s, session, _, _ = make({SB[0]: (200, fx("scoreboard_20261028"))}, teams=("MIA",))
    snap = await s.poll()
    assert snap.stale is False
    assert snap.error is None
    assert len(snap.games) == 1
    assert snap.games[PRE_ID].state == "future"
    assert session.urls == [SB[0]]


async def test_host_fallback_on_403():
    s, session, _, _ = make(
        {SB[0]: (403, {}), SB[1]: (200, fx("scoreboard_20261028"))}, teams=("MIA",)
    )
    snap = await s.poll()
    assert snap.stale is False
    assert session.urls == [SB[0], SB[1]]
    assert PRE_ID in snap.games


async def test_both_hosts_fail_is_stale():
    s, session, _, _ = make({SB[0]: (403, {}), SB[1]: OSError("boom")})
    snap = await s.poll()
    assert snap.stale is True
    assert snap.error is not None
    assert "HTTP 403" in snap.error or "network" in snap.error
    assert session.urls == [SB[0], SB[1]]
    assert s.next_delay() == 2 * LIVE_INTERVAL
    await s.poll()  # gated inside the backoff window
    assert len(session.urls) == 2


async def test_malformed_payload_keeps_last_games():
    s, session, clock, _ = make(
        {SB[0]: (200, fx("scoreboard_20261028"))}, teams=("MIA",)
    )
    snap = await s.poll()
    assert PRE_ID in snap.games
    session.routes[SB[0]] = (200, {"events": "nope"})
    clock.advance()
    snap = await s.poll()
    assert snap.stale is True
    assert PRE_ID in snap.games


async def test_cadence_ladder():
    s, _, _, _ = make({SB[0]: (200, day(live_event()))})
    await s.poll()
    assert s.next_delay() == LIVE_INTERVAL
    s, _, _, _ = make(
        {SB[0]: (200, day(sched(NOW + timedelta(minutes=20))))}, teams=("MIA",)
    )
    await s.poll()
    assert s.next_delay() == TIPOFF_INTERVAL
    s, _, _, _ = make(
        {SB[0]: (200, day(sched(NOW + timedelta(hours=6))))}, teams=("MIA",)
    )
    await s.poll()
    assert s.next_delay() == PREGAME_INTERVAL
    s, _, _, _ = make(
        {SB[0]: (200, day(sched(NOW + timedelta(days=3))))}, teams=("MIA",)
    )
    await s.poll()
    assert s.next_delay() == IDLE_INTERVAL
    s, _, _, _ = make({SB[0]: (200, day(live_event()))})
    s.want(teams={"PHI"}, all_games=False, tz=TZ, final_hold_hours=24, live_interval=10)
    await s.poll()
    assert s.next_delay() == 10
    s, _, _, _ = make({SB[0]: (200, day(live_event()))})
    s.want(teams={"PHI"}, all_games=False, tz=TZ, final_hold_hours=24, live_interval=5)
    await s.poll()
    assert s.next_delay() == MIN_INTERVAL


async def test_first_sight_final_is_silent():
    s, _, _, _ = make({SB[0]: (200, day(final_event_json()))})
    snap = await s.poll()
    assert snap.games[LIVE_ID].state == "final"
    assert s.final_after_baseline(LIVE_ID) is None


async def test_live_to_final_emits_final_event():
    s, session, clock, _ = make({SB[0]: (200, day(live_event()))})
    await s.poll()
    assert s.final_after_baseline(LIVE_ID) is None
    session.routes[SB[0]] = (200, day(final_event_json(112, 108)))
    clock.advance()
    await s.poll()
    ev = s.final_after_baseline(LIVE_ID)
    assert ev is not None
    assert ev.winner == "PHI"
    assert ev.loser == "NY"
    assert (ev.away_score, ev.home_score) == (112, 108)
    assert ev.leader is not None and ev.leader.points == 31


async def test_final_event_is_non_consuming():
    s, session, clock, _ = make({SB[0]: (200, day(live_event()))})
    await s.poll()
    session.routes[SB[0]] = (200, day(final_event_json()))
    clock.advance()
    await s.poll()
    first = s.final_after_baseline(LIVE_ID)
    assert first is not None
    assert s.final_after_baseline(LIVE_ID) is first
    clock.advance()
    await s.poll()  # still final next poll: the event is not overwritten
    assert s.final_after_baseline(LIVE_ID) is first


async def test_yesterday_feed_keeps_late_game():
    yday = (NOW.astimezone(TZ).date() - timedelta(days=1)).strftime("%Y%m%d")
    yday_url = f"{SB[0]}?dates={yday}"
    s, session, clock, _ = make(
        {SB[0]: (200, day(live_event())), yday_url: (200, day(live_event()))}
    )
    await s.poll()
    assert not any("?dates=" in u for u in session.urls)  # today still has it
    session.routes[SB[0]] = (200, day())
    clock.advance()
    snap = await s.poll()
    assert snap.stale is False
    assert snap.games[LIVE_ID].state == "live"
    assert s.next_delay() == LIVE_INTERVAL
    assert [u for u in session.urls if "?dates=" in u] == [yday_url]
    assert s._yesterday_ids == {LIVE_ID}


async def test_yesterday_feed_uses_eastern_date_for_western_users():
    # 00:30 ET Oct 29 is 21:30 PT Oct 28: ESPN's default slate is already the
    # 29th (Eastern), so yesterday is the 28th -- not the 27th a PT-local
    # computation gives.
    wall = datetime(2026, 10, 29, 4, 30, tzinfo=UTC)
    session = FakeSession({SB[0]: (200, day(live_event()))})
    clock = Clock()
    s = ESPNSource(session, clock=clock, wall=lambda: wall)
    s.want(
        teams={"PHI"},
        all_games=False,
        tz=ZoneInfo("America/Los_Angeles"),
        final_hold_hours=24,
    )
    await s.poll()
    session.routes[SB[0]] = (200, day())
    session.routes[f"{SB[0]}?dates=20261028"] = (200, day(final_event_json(112, 108)))
    clock.advance()
    snap = await s.poll()
    yday = [u for u in session.urls if "?dates=" in u]
    assert yday == [f"{SB[0]}?dates=20261028"]
    assert not any("dates=20261027" in u for u in session.urls)
    assert snap.games[LIVE_ID].state == "final"
    assert isinstance(s.final_after_baseline(LIVE_ID), FinalEvent)


async def test_yesterday_feed_failure_is_soft():
    s, session, clock, _ = make({SB[0]: (200, day(live_event()))})
    await s.poll()
    session.routes[SB[0]] = (200, day())
    clock.advance()
    snap = await s.poll()  # yesterday route 404s on both hosts
    assert snap.stale is False
    assert snap.games[LIVE_ID].state == "live"


async def test_vanished_game_keeps_state_until_hold():
    s, session, clock, state = make({SB[0]: (200, day(final_event_json()))}, hold=24)
    snap = await s.poll()
    assert LIVE_ID in snap.games
    session.routes[SB[0]] = (200, day())
    clock.advance()
    snap = await s.poll()
    assert LIVE_ID in snap.games  # never inferred away
    assert snap.games[LIVE_ID].state == "final"
    state["wall"] = NOW + timedelta(hours=25)
    clock.advance()
    snap = await s.poll()
    assert LIVE_ID not in snap.games
    assert s.final_after_baseline(LIVE_ID) is None


async def test_next_game_from_schedule():
    sched_url = f"{HOSTS[0]}{PATH}/teams/PHI/schedule"
    s, session, clock, _ = make(
        {SB[0]: (200, day()), sched_url: (200, fx("schedule_phi"))}, teams=("PHI",)
    )
    snap = await s.poll()
    assert snap.next_games["PHI"].game_id == "401909884"
    assert snap.next_games["PHI"].state == "future"
    assert session.urls.count(sched_url) == 1
    clock.advance(SCHEDULE_INTERVAL / 2)
    await s.poll()
    assert session.urls.count(sched_url) == 1
    clock.advance(SCHEDULE_INTERVAL)
    await s.poll()
    assert session.urls.count(sched_url) == 2


async def test_today_pre_game_beats_schedule():
    s, session, _, _ = make({SB[0]: (200, fx("scoreboard_20261028"))}, teams=("MIA",))
    snap = await s.poll()
    assert PRE_ID in snap.games
    assert "MIA" not in snap.next_games
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
        {SB[0]: (200, fx("scoreboard_20261028"))}, teams=("PHI",), all_games=mode_all
    )
    snap = await s.poll()
    assert (PRE_ID in snap.games) is mode_all


async def test_first_poll_failure_backs_off_from_live_interval():
    s, _, clock, _ = make({})
    snap = await s.poll()
    assert snap.stale is True
    assert s.next_delay() == 2 * LIVE_INTERVAL
    clock.advance(s.next_delay())
    await s.poll()
    assert s.next_delay() == 4 * LIVE_INTERVAL


async def test_backoff_after_a_success_uses_the_cadence():
    s, session, clock, _ = make(
        {SB[0]: (200, day(sched(NOW + timedelta(days=3))))}, teams=("MIA",)
    )
    await s.poll()
    assert s.next_delay() == IDLE_INTERVAL
    session.routes = {}
    clock.advance(IDLE_INTERVAL)
    await s.poll()
    assert s.next_delay() == 2 * IDLE_INTERVAL


async def test_partial_payload_keeps_the_live_cadence():
    s, session, clock, _ = make({SB[0]: (200, day(live_event()))})
    await s.poll()
    session.routes[SB[0]] = (200, day())
    clock.advance()
    snap = await s.poll()
    assert snap.stale is False and LIVE_ID in snap.games
    assert s.next_delay() == LIVE_INTERVAL
    assert "PHI" in s._playing()


async def test_schedule_failure_retries_on_the_next_poll():
    sched_url = f"{HOSTS[0]}{PATH}/teams/PHI/schedule"
    s, session, clock, _ = make({SB[0]: (200, day())})
    snap = await s.poll()
    assert "PHI" not in snap.next_games
    assert session.urls.count(sched_url) == 1
    clock.advance(SCHEDULE_RETRY - 1)
    await s.poll()
    assert session.urls.count(sched_url) == 1
    session.routes[sched_url] = (200, fx("schedule_phi"))
    clock.advance(IDLE_INTERVAL)
    snap = await s.poll()
    assert session.urls.count(sched_url) == 2
    assert "PHI" in snap.next_games


async def test_schedule_fetched_while_a_final_is_held():
    sched_url = f"{HOSTS[0]}{PATH}/teams/PHI/schedule"
    s, session, _, _ = make(
        {SB[0]: (200, day(final_event_json())), sched_url: (200, fx("schedule_phi"))}
    )
    snap = await s.poll()
    assert snap.games[LIVE_ID].state == "final"
    assert session.urls.count(sched_url) == 1


async def test_schedule_retry_waits_longer_while_a_game_is_live():
    sched_url = f"{HOSTS[0]}{PATH}/teams/NY2/schedule"
    s, session, clock, _ = make({SB[0]: (200, day(live_event()))}, teams=("PHI", "NY2"))
    await s.poll()
    assert session.urls.count(sched_url) == 1
    calls = [kw for url, kw in session.calls if url == sched_url]
    assert calls[0]["timeout"].total == SCHEDULE_TIMEOUT
    clock.advance(SCHEDULE_RETRY + LIVE_INTERVAL)
    await s.poll()
    assert session.urls.count(sched_url) == 1
    clock.advance(SCHEDULE_RETRY_LIVE)
    await s.poll()
    assert session.urls.count(sched_url) == 2
