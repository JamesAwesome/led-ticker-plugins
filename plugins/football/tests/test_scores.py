"""FootballScoreMonitor: config validation, story selection per mode, card
reuse across polls, scoring-play queueing, start() wiring, demo."""

import dataclasses
import logging
import unittest.mock as mock
from datetime import UTC, datetime, timedelta

import led_ticker_football.scores as mod
from led_ticker_football._card import FootballGameCard
from led_ticker_football._models import (
    GAME_LENGTH,
    GameInfo,
    ScoringPlay,
    build_demo_games,
)
from led_ticker_football._source import MIN_INTERVAL, Snapshot
from led_ticker_football.scores import FootballScoreMonitor, select_stories

from .conftest import TZ

# Mon 2026-10-26 11:30 local (15:30 UTC)
NOW_DT = datetime(2026, 10, 26, 15, 30, tzinfo=UTC)
NOW = NOW_DT.timestamp()
_TEMPLATE = build_demo_games(NOW)[0][0]


def game(gid, state, away="PHI", home="NYG", *, start=None, **over) -> GameInfo:
    status = {"live": "STATUS_IN_PROGRESS", "final": "STATUS_FINAL"}.get(
        state, "STATUS_SCHEDULED"
    )
    return dataclasses.replace(
        _TEMPLATE,
        game_id=str(gid),
        state=state,
        status=status,
        away=away,
        home=home,
        start_utc=start,
        situation=None,
        **over,
    )


def final_ended(gid, hours_ago, away="PHI", home="NYG"):
    """A final whose (estimated) end was `hours_ago` hours before NOW."""
    start = NOW_DT - timedelta(hours=hours_ago) - GAME_LENGTH
    return game(gid, "final", away, home, start=start)


def play(key, team="PHI", away=26, home=17, kind="TD", extra=""):
    return ScoringPlay(
        key=key,
        team=team,
        kind=kind,
        extra=extra,
        text="",
        period_label="Q4",
        clock="2:13",
        away_score=away,
        home_score=home,
    )


def select(games, next_games=None, *, mode="teams", teams=("PHI",), **kw):
    kw.setdefault("max_games", 8)
    kw.setdefault("final_hold_hours", 24)
    return select_stories(
        {g.game_id: g for g in games},
        next_games or {},
        mode=mode,
        teams=list(teams),
        now_wall=NOW,
        tz=TZ,
        **kw,
    )


def ids(stories):
    return [g.game_id for g in stories]


# ----------------------------------------------------------- validation


class TestValidate:
    def test_valid_is_empty(self):
        cfg = {"teams": ["PHI", "nyg"], "mode": "teams", "layout": "auto"}
        assert FootballScoreMonitor.validate_config(cfg) == []

    def test_validate_unknown_team_suggests(self):
        msgs = FootballScoreMonitor.validate_config({"teams": ["PHL"]})
        assert len(msgs) == 1
        assert "Did you mean 'PHI'?" in msgs[0]

    def test_teams_must_be_list_of_str(self):
        assert FootballScoreMonitor.validate_config({"teams": "PHI"})
        assert FootballScoreMonitor.validate_config({"teams": [1]})

    def test_validate_teams_mode_requires_teams(self):
        msgs = FootballScoreMonitor.validate_config({})
        assert len(msgs) == 1 and 'mode="teams"' in msgs[0]
        assert FootballScoreMonitor.validate_config({"mode": "league"}) == []
        assert FootballScoreMonitor.validate_config({"demo": True}) == []

    def test_validate_bad_mode_layout_timezone(self):
        assert (
            "Did you mean 'league'"
            in FootballScoreMonitor.validate_config(
                {"teams": ["PHI"], "mode": "leage"}
            )[0]
        )
        assert (
            "Did you mean 'ticker'"
            in FootballScoreMonitor.validate_config(
                {"teams": ["PHI"], "layout": "tiker"}
            )[0]
        )
        assert (
            "timezone"
            in FootballScoreMonitor.validate_config(
                {"teams": ["PHI"], "timezone": "Mars/Olympus"}
            )[0]
        )

    def test_scalars(self):
        v = FootballScoreMonitor.validate_config
        assert v({"teams": ["PHI"], "max_games": 0})
        assert v({"teams": ["PHI"], "final_hold_hours": -1})
        assert v({"teams": ["PHI"], "update_interval": 0})
        assert v({"teams": ["PHI"], "demo": "yes"})
        assert v({"teams": ["PHI"], "hold_time": -1})
        assert v({"teams": ["PHI"], "padding": "6"})
        assert v({"teams": ["PHI"], "max_games": True})
        assert v({"teams": ["PHI"], "hold_time": 2.5, "padding": 3.0}) == []


# ------------------------------------------------------------ selection


class TestSelect:
    def test_teams_mode_selection_order(self):
        live = game(1, "live")
        final = final_ended(2, 1)
        later = game(3, "future", start=NOW_DT + timedelta(days=3))
        nxt = game(9, "future", start=NOW_DT + timedelta(days=10))
        assert ids(select([live, final, later], {"PHI": nxt})) == ["1"]
        assert ids(select([final, later], {"PHI": nxt})) == ["2"]
        assert ids(select([later], {"PHI": nxt})) == ["3"]
        assert ids(select([], {"PHI": nxt})) == ["9"]
        assert ids(select([])) == []

    def test_teams_mode_dedupes_head_to_head(self):
        out = select([game(1, "live")], teams=("PHI", "NYG"))
        assert ids(out) == ["1"]

    def test_final_hold_default_24h(self):
        nxt = game(9, "future", start=NOW_DT + timedelta(days=6))
        assert ids(select([final_ended(2, 20)], {"PHI": nxt})) == ["2"]
        assert ids(select([final_ended(2, 26)], {"PHI": nxt})) == ["9"]
        assert ids(select([final_ended(2, 7)], {"PHI": nxt}, final_hold_hours=6)) == [
            "9"
        ]

    def test_final_without_start_time_counts_as_inside_hold(self):
        assert ids(select([game(2, "final")])) == ["2"]

    def test_next_game_fallback_and_config_order(self):
        nyg = game(5, "live", "NYG", "DAL")
        phi_next = game(9, "future", start=NOW_DT + timedelta(days=4))
        out = select([nyg], {"PHI": phi_next}, teams=("PHI", "NYG"))
        assert ids(out) == ["9", "5"]

    def test_untracked_games_ignored(self):
        assert ids(select([game(7, "live", "DAL", "WSH")])) == []

    def test_league_mode_order_and_cap(self):
        tracked_final = final_ended(1, 2)
        live_a = game(2, "live", "DAL", "WSH")
        live_b = game(3, "live", "KC", "BUF")
        fin = final_ended(4, 3, "SF", "SEA")
        old = final_ended(5, 30, "GB", "DET")
        up_late = game(6, "future", "MIA", "NYJ", start=NOW_DT + timedelta(days=2))
        up_soon = game(7, "future", "LV", "LAC", start=NOW_DT + timedelta(hours=5))
        tbd = game(
            8, "future", "TEN", "HOU", start=NOW_DT + timedelta(days=1), time_tbd=True
        )
        games = [up_late, old, live_b, fin, up_soon, tracked_final, live_a, tbd]
        out = select(games, mode="league")
        assert ids(out) == ["1", "2", "3", "4", "7", "6", "8"]
        assert ids(select(games, mode="league", max_games=3)) == ["1", "2", "3"]

    def test_live_mode_empty_when_nothing_live(self):
        assert select([final_ended(2, 1)], mode="live") == []

    def test_live_tracked_first_and_capped(self):
        games = [
            game(14, "live", "DAL", "WSH"),
            game(1, "live"),
            game(15, "live", "KC", "BUF"),
        ]
        out = select(games, mode="live")
        assert ids(out)[0] == "1" and set(ids(out)) == {"1", "14", "15"}
        assert len(select(games, mode="live", max_games=2)) == 2


# --------------------------------------------------------------- update


class FakeSource:
    def __init__(self, snapshot, plays=None):
        self.snapshot = snapshot
        self.plays: dict[str, tuple[ScoringPlay, ...]] = plays or {}
        self.polls = 0
        self.displayed: list[tuple[object, set[str]]] = []

    async def poll(self):
        self.polls += 1
        return self.snapshot

    def note_displayed(self, consumer, game_ids):
        self.displayed.append((consumer, set(game_ids)))

    def plays_after_baseline(self, game_id):
        return self.plays.get(game_id, ())


def _widget(snapshot, plays=None, **kw):
    kw.setdefault("teams", ["PHI"])
    w = FootballScoreMonitor(session=None, **kw)
    w._tz = TZ
    w._source = FakeSource(snapshot, plays)
    return w


def _snap(*games, next_games=None, stale=False, bye=()):
    return Snapshot(
        games={g.game_id: g for g in games},
        next_games=next_games or {},
        bye_teams=frozenset(bye),
        week=7,
        stale=stale,
    )


class TestUpdate:
    async def test_cards_persist_across_polls(self, caplog):
        live = game(1, "live")
        w = _widget(_snap(live))
        with caplog.at_level(logging.INFO, logger=mod.__name__):
            await w.update()
        assert "football.scores updated: 1 stories" in caplog.text
        card = w.feed_stories[0]
        assert isinstance(card, FootballGameCard) and card.game is live
        moved = dataclasses.replace(live, away_score=27)
        w._source.snapshot = _snap(moved)
        await w.update()
        assert w.feed_stories[0] is card
        assert card.game is moved

    async def test_next_game_card_keyed_by_team_and_reused(self):
        nxt = game(9, "future", start=NOW_DT + timedelta(days=2))
        w = _widget(_snap(next_games={"PHI": nxt}))
        await w.update()
        card = w.feed_stories[0]
        assert w._cards == {"next:PHI": card}
        w._source.snapshot = _snap(next_games={"PHI": dataclasses.replace(nxt)})
        await w.update()
        assert w.feed_stories[0] is card

    async def test_bye_flag_reaches_next_card(self):
        nxt = game(9, "future", start=NOW_DT + timedelta(days=9))
        w = _widget(_snap(next_games={"PHI": nxt}, bye=("PHI",)))
        await w.update()
        assert w.feed_stories[0].bye is True
        w._source.snapshot = _snap(next_games={"PHI": nxt})
        await w.update()
        assert w.feed_stories[0].bye is False
        # A live card is never flagged, whatever the bye list says.
        w._source.snapshot = _snap(game(1, "live"), bye=("PHI",))
        await w.update()
        assert w.feed_stories[0].bye is False

    async def test_stale_marks_cards(self):
        w = _widget(_snap(game(1, "live")))
        await w.update()
        assert w.feed_stories[0].stale is False
        w._source.snapshot = _snap(game(1, "live"), stale=True)
        await w.update()
        assert w.feed_stories[0].stale is True

    async def test_offseason_shows_nothing(self):
        w = _widget(_snap())
        await w.update()
        assert w.feed_stories == []

    async def test_cards_dropped_when_games_leave(self):
        w = _widget(_snap(game(1, "live")))
        await w.update()
        w._source.snapshot = _snap()
        await w.update()
        assert w.feed_stories == [] and w._cards == {}

    async def test_update_without_source_is_noop(self):
        w = FootballScoreMonitor(session=None, teams=["PHI"])
        await w.update()
        assert w.feed_stories == []

    async def test_update_never_raises(self, caplog):
        w = _widget(_snap(game(1, "live")))

        def boom(*a, **k):
            raise RuntimeError("bad")

        with mock.patch.object(mod, "select_stories", boom):
            await w.update()
        assert w.feed_stories == []
        assert "football.scores update failed" in caplog.text


class TestPlays:
    async def test_first_sight_silent_then_only_new_plays_queued(self):
        live = game(1, "live")
        w = _widget(_snap(live), {"1": (play("1:26:17"),)})
        await w.update()
        assert w.feed_stories[0].pending == []  # first sight: baseline
        w._source.plays["1"] = (play("1:26:17"), play("1:26:24", "NYG", 26, 24))
        w._source.snapshot = _snap(
            dataclasses.replace(live, away_score=26, home_score=24)
        )
        await w.update()
        card = w.feed_stories[0]
        assert [p.key for p in card.pending] == []  # NYG untracked → highlight
        assert card.highlight is not None and card.highlight[0] == "NYG"
        w._source.plays["1"] = (
            play("1:26:17"),
            play("1:26:24", "NYG", 26, 24),
            play("1:33:24", "PHI", 33, 24),
        )
        w._source.snapshot = _snap(
            dataclasses.replace(live, away_score=33, home_score=24)
        )
        await w.update()
        assert [p.key for p in card.pending] == ["1:33:24"]

    async def test_follow_up_replaces_pending_play(self):
        live = game(1, "live", away_score=20, home_score=17)
        w = _widget(_snap(live))
        await w.update()
        card = w.feed_stories[0]
        w._source.plays["1"] = (play("1:26:17"),)
        w._source.snapshot = _snap(dataclasses.replace(live, away_score=26))
        await w.update()
        assert [p.key for p in card.pending] == ["1:26:17"]
        # The extra point re-keys the same play; nothing new celebrates.
        w._source.plays["1"] = (play("1:27:17", away=27, extra="+PAT"),)
        w._source.snapshot = _snap(dataclasses.replace(live, away_score=27))
        await w.update()
        assert [(p.key, p.extra) for p in card.pending] == [("1:27:17", "+PAT")]

    async def test_celebrated_pruned_with_game(self):
        w = _widget(_snap(game(1, "live")), {"1": ()})
        await w.update()
        assert "1" in w._celebrated
        w._source.snapshot = _snap()
        await w.update()
        assert w._celebrated == {}


class TestDemo:
    async def test_demo_builds_five_cards_and_queues_td(self):
        w = await FootballScoreMonitor.start(None, demo=True, teams=["PHI"])
        assert len(w.feed_stories) == 5
        live = w.feed_stories[0]
        assert [p.kind for p in live.pending] == ["TD"]
        assert live.demo_plays and live.demo_plays[0].team == "PHI"
        assert w.feed_stories[4].bye is True
        assert w._source is None


class TestStart:
    async def test_start_registers_interest_updates_and_spawns(self):
        src = FakeSource(_snap(game(1, "live")))
        src.want = mock.Mock()
        spawn = mock.Mock()
        loop = mock.Mock(return_value="LOOP")
        with (
            mock.patch.object(mod, "shared_source", return_value=src),
            mock.patch.object(mod, "spawn_tracked", spawn),
            mock.patch.object(mod, "run_monitor_loop", loop),
        ):
            w = await FootballScoreMonitor.start(
                "SESSION",
                update_interval=3,
                teams=["phi", "nyg"],
                final_hold_hours=4,
                hold_time=7.5,
            )
        assert w.teams == ["PHI", "NYG"]
        kw = src.want.call_args.kwargs
        assert kw["teams"] == {"PHI", "NYG"} and kw["all_games"] is False
        assert kw["final_hold_hours"] == 4 and str(kw["tz"]) == "America/New_York"
        assert kw["live_interval"] == 3
        assert src.polls == 1 and len(w.feed_stories) == 1
        assert w.feed_stories[0].hold_time == 7.5
        assert w.feed_stories[0].tracked == frozenset({"PHI", "NYG"})
        loop.assert_called_once_with(w, MIN_INTERVAL)
        spawn.assert_called_once_with("LOOP")

    async def test_league_mode_wants_all_games(self):
        src = FakeSource(_snap())
        src.want = mock.Mock()
        with (
            mock.patch.object(mod, "shared_source", return_value=src),
            mock.patch.object(mod, "spawn_tracked", mock.Mock()),
            mock.patch.object(mod, "run_monitor_loop", mock.Mock()),
        ):
            await FootballScoreMonitor.start(None, mode="league", teams=[])
        assert src.want.call_args.kwargs["all_games"] is True


class TestCorrections:
    async def test_overturned_then_rescored_touchdown_celebrates(self):
        """20-17 → 26-17 (TD) → 20-17 (overturned) → 26-17 (scored for real):
        the second touchdown has the same key and must still celebrate."""
        from led_ticker_football._source import ESPNSource

        from .test_source import SB, FakeSession, live_event, week_with

        session = FakeSession({SB[0]: (200, week_with(live_event()))})
        t = {"now": 1000.0}
        src = ESPNSource(session, clock=lambda: t["now"], wall=lambda: NOW_DT)
        src.want(teams={"PHI"}, all_games=False, tz=TZ, final_hold_hours=24)
        w = FootballScoreMonitor(session=None, teams=["PHI"])
        w._tz = TZ
        w._source = src
        await w.update()
        card = w.feed_stories[0]
        for away in (26, 20, 26):
            session.routes[SB[0]] = (200, week_with(live_event(away=away)))
            t["now"] += 1e6
            await w.update()
            if away == 20:
                assert card.pending == []
        assert [p.key for p in card.pending] == ["401873099:26:17"]
