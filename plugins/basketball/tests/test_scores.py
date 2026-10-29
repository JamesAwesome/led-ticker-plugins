"""BasketballScoreMonitor: config validation, story selection per mode, card
reuse across polls, final queueing, score pulse, start() wiring, demo."""

import dataclasses
import logging
import unittest.mock as mock
from datetime import UTC, datetime, timedelta

import pytest

import led_ticker_basketball.scores as mod
from led_ticker_basketball._card import BasketballGameCard
from led_ticker_basketball._models import (
    FinalEvent,
    GameInfo,
    build_demo_games,
)
from led_ticker_basketball._source import MIN_INTERVAL, Snapshot
from led_ticker_basketball.scores import BasketballScoreMonitor, select_stories

from .conftest import TZ

NOW_DT = datetime(2026, 10, 26, 15, 30, tzinfo=UTC)
NOW = NOW_DT.timestamp()
_TEMPLATE = build_demo_games(NOW)[0][0]


def game(gid, state, away="PHI", home="NY", *, start=None, **over) -> GameInfo:
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
        **over,
    )


def final_ended(gid, hours_ago, away="PHI", home="NY"):
    """A final whose (estimated) end was `hours_ago` hours before NOW."""
    start = NOW_DT - timedelta(hours=hours_ago) - timedelta(hours=3)
    return game(gid, "final", away, home, start=start)


def fin_event(gid="1", winner="PHI", key=None):
    return FinalEvent(
        key=key or f"{gid}:{winner}",
        game_id=gid,
        winner=winner,
        loser="NY" if winner == "PHI" else "PHI",
        away_score=110,
        home_score=100,
        final_ot=False,
        leader=None,
    )


def select(games, next_games=None, *, mode="teams", teams=("PHI",), **kw):
    kw.setdefault("max_games", 8)
    kw.setdefault("final_hold_hours", 6)
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


class TestValidate:
    def test_valid_is_empty(self):
        cfg = {"teams": ["PHI", "ny"], "mode": "teams", "layout": "auto"}
        assert BasketballScoreMonitor.validate_config(cfg) == []

    def test_validate_unknown_team_suggests(self):
        msgs = BasketballScoreMonitor.validate_config({"teams": ["NYK"]})
        assert len(msgs) == 1
        assert "Did you mean 'NY'?" in msgs[0]
        assert msgs[0].startswith("basketball.scores")

    def test_validate_rejects_small_font(self):
        msgs = BasketballScoreMonitor.validate_config(
            {"teams": ["PHI"], "small_font": "x"}
        )
        assert msgs == [
            "basketball.scores does not accept small_font: "
            "the smallsign board uses font"
        ]

    @pytest.mark.parametrize("name", ["logos", "ball_at"])
    def test_validate_bool_options(self, name):
        v = BasketballScoreMonitor.validate_config
        assert v({"teams": ["PHI"], name: "yes"})
        assert v({"teams": ["PHI"], name: False}) == []

    def test_teams_mode_requires_teams(self):
        msgs = BasketballScoreMonitor.validate_config({})
        assert len(msgs) == 1 and 'mode="teams"' in msgs[0]
        assert BasketballScoreMonitor.validate_config({"mode": "league"}) == []
        assert BasketballScoreMonitor.validate_config({"demo": True}) == []

    def test_bad_mode_layout_timezone_scalars(self):
        v = BasketballScoreMonitor.validate_config
        assert "Did you mean 'league'" in v({"teams": ["PHI"], "mode": "leage"})[0]
        assert "Did you mean 'ticker'" in v({"teams": ["PHI"], "layout": "tiker"})[0]
        assert "timezone" in v({"teams": ["PHI"], "timezone": "Mars/Olympus"})[0]
        assert v({"teams": ["PHI"], "max_games": 0})
        assert v({"teams": ["PHI"], "final_hold_hours": -1})
        assert v({"teams": ["PHI"], "update_interval": 0})
        assert v({"teams": ["PHI"], "demo": "yes"})
        assert v({"teams": ["PHI"], "hold_time": True})
        assert v({"teams": ["PHI"], "hold_time": 2.5, "padding": 3.0}) == []


class TestSelect:
    def test_teams_mode_selection_order(self):
        live = game(1, "live")
        final = final_ended(2, 1)
        later = game(3, "future", start=NOW_DT + timedelta(hours=5))
        nxt = game(9, "future", start=NOW_DT + timedelta(days=2))
        assert ids(select([live, final, later], {"PHI": nxt})) == ["1"]
        assert ids(select([final, later], {"PHI": nxt})) == ["2"]
        assert ids(select([later], {"PHI": nxt})) == ["3"]
        assert ids(select([], {"PHI": nxt})) == ["9"]
        assert ids(select([])) == []

    def test_head_to_head_is_one_card(self):
        assert ids(select([game(1, "live")], teams=("PHI", "NY"))) == ["1"]

    def test_final_hold_default_6h(self):
        nxt = game(9, "future", start=NOW_DT + timedelta(days=1))
        assert mod.DEFAULT_FINAL_HOLD_HOURS == 6
        assert ids(select([final_ended(2, 4)], {"PHI": nxt})) == ["2"]
        assert ids(select([final_ended(2, 9)], {"PHI": nxt})) == ["9"]

    def test_league_mode_order_and_cap(self):
        tracked_final = final_ended(1, 2)
        live_a = game(2, "live", "DAL", "BOS")
        live_b = game(3, "live", "LAL", "MIA")
        fin = final_ended(4, 3, "GS", "SEA")
        old = final_ended(5, 30, "DEN", "DET")
        up_late = game(6, "future", "MIL", "ORL", start=NOW_DT + timedelta(hours=9))
        up_soon = game(7, "future", "LAC", "SAC", start=NOW_DT + timedelta(hours=5))
        games = [up_late, old, live_b, fin, up_soon, tracked_final, live_a]
        out = select(games, mode="league")
        assert ids(out) == ["1", "2", "3", "4", "7", "6"]
        assert ids(select(games, mode="league", max_games=3)) == ["1", "2", "3"]

    def test_live_mode_empty_when_nothing_live(self):
        assert select([final_ended(2, 1)], mode="live") == []

    def test_live_tracked_first_and_capped(self):
        games = [
            game(14, "live", "DAL", "BOS"),
            game(1, "live"),
            game(15, "live", "LAL", "MIA"),
        ]
        out = select(games, mode="live")
        assert ids(out)[0] == "1" and set(ids(out)) == {"1", "14", "15"}
        assert len(select(games, mode="live", max_games=2)) == 2


class FakeSource:
    def __init__(self, snapshot, finals=None):
        self.snapshot = snapshot
        self.finals: dict[str, FinalEvent] = finals or {}
        self.polls = 0
        self.displayed: list[tuple[object, set[str]]] = []

    async def poll(self):
        self.polls += 1
        return self.snapshot

    def note_displayed(self, consumer, game_ids):
        self.displayed.append((consumer, set(game_ids)))

    def final_after_baseline(self, game_id):
        return self.finals.get(game_id)


def _widget(snapshot, finals=None, **kw):
    kw.setdefault("teams", ["PHI"])
    w = BasketballScoreMonitor(session=None, **kw)
    w._tz = TZ
    w._source = FakeSource(snapshot, finals)
    return w


def _snap(*games, next_games=None, stale=False):
    return Snapshot(
        games={g.game_id: g for g in games},
        next_games=next_games or {},
        stale=stale,
    )


class TestUpdate:
    async def test_cards_persist_across_polls(self, caplog):
        live = game(1, "live")
        w = _widget(_snap(live))
        with caplog.at_level(logging.INFO, logger=mod.__name__):
            await w.update()
        assert "basketball.scores updated: 1 stories" in caplog.text
        card = w.feed_stories[0]
        assert isinstance(card, BasketballGameCard) and card.game is live
        moved = dataclasses.replace(live, away_score=27)
        w._source.snapshot = _snap(moved)
        await w.update()
        assert w.feed_stories[0] is card and card.game is moved

    async def test_next_game_card_keyed_by_team_and_reused(self):
        nxt = game(9, "future", start=NOW_DT + timedelta(days=2))
        w = _widget(_snap(next_games={"PHI": nxt}))
        await w.update()
        card = w.feed_stories[0]
        assert w._cards == {"next:PHI": card}
        w._source.snapshot = _snap(next_games={"PHI": dataclasses.replace(nxt)})
        await w.update()
        assert w.feed_stories[0] is card

    async def test_stale_marks_cards(self):
        w = _widget(_snap(game(1, "live")))
        await w.update()
        assert w.feed_stories[0].stale is False
        w._source.snapshot = _snap(game(1, "live"), stale=True)
        await w.update()
        assert w.feed_stories[0].stale is True

    async def test_offseason_shows_nothing_and_cards_drop(self):
        w = _widget(_snap(game(1, "live")))
        await w.update()
        w._source.snapshot = _snap()
        await w.update()
        assert w.feed_stories == [] and w._cards == {}

    async def test_update_without_source_is_noop(self):
        w = BasketballScoreMonitor(session=None, teams=["PHI"])
        await w.update()
        assert w.feed_stories == []

    async def test_update_never_raises(self, caplog):
        w = _widget(_snap(game(1, "live")))
        with mock.patch.object(mod, "select_stories", side_effect=RuntimeError("x")):
            await w.update()
        assert w.feed_stories == []
        assert "basketball.scores update failed" in caplog.text

    async def test_score_change_pulses_that_team(self):
        live = game(1, "live", away_score=98, home_score=101)
        w = _widget(_snap(live))
        await w.update()
        card = w.feed_stories[0]
        assert card.highlights == {}  # first sight: no pulse
        w._source.snapshot = _snap(dataclasses.replace(live, away_score=100))
        await w.update()
        assert card.highlights == {"PHI": 30}
        w._source.snapshot = _snap(
            dataclasses.replace(live, away_score=102, home_score=103)
        )
        await w.update()
        assert set(card.highlights) == {"PHI", "NY"}


class TestFinals:
    async def test_tracked_win_queues_final(self):
        live = game(1, "live")
        w = _widget(_snap(live))
        await w.update()  # baseline: no event yet
        ev = fin_event("1", "PHI")
        w._source.finals["1"] = ev
        w._source.snapshot = _snap(game(1, "final"))
        await w.update()
        assert w.feed_stories[0].pending == [ev]

    async def test_untracked_win_does_not_queue(self):
        w = _widget(_snap(game(1, "live")))
        await w.update()
        w._source.finals["1"] = fin_event("1", "NY")
        w._source.snapshot = _snap(game(1, "final"))
        await w.update()
        assert w.feed_stories[0].pending == []

    async def test_reload_with_surviving_source_is_silent(self):
        ev = fin_event("1", "PHI")
        w = _widget(_snap(game(1, "final")), {"1": ev})
        await w.update()
        assert w.feed_stories[0].pending == []
        await w.update()  # same key again: still nothing
        assert w.feed_stories[0].pending == []

    async def test_live_mode_keeps_finished_card_until_shown(self):
        w = _widget(_snap(game(1, "live")), mode="live")
        await w.update()
        ev = fin_event("1", "PHI")
        w._source.finals["1"] = ev
        w._source.snapshot = _snap(game(1, "final"))
        await w.update()
        assert len(w.feed_stories) == 1 and w.feed_stories[0].pending == [ev]
        w.feed_stories[0].pending.clear()
        await w.update()
        assert w.feed_stories == []

    async def test_celebrated_pruned_with_game(self):
        w = _widget(_snap(game(1, "live")))
        await w.update()
        assert "1" in w._celebrated
        w._source.snapshot = _snap()
        await w.update()
        assert w._celebrated == {}


class TestDemo:
    async def test_demo_builds_four_cards_and_queues_final(self):
        w = await BasketballScoreMonitor.start(None, demo=True, teams=["PHI"])
        assert len(w.feed_stories) == 4
        live = w.feed_stories[0]
        assert live.game.game_id == "demo-live"
        assert len(live.pending) == 1 and live.demo_final is live.pending[0]
        assert live.pending[0].winner == "PHI"
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
            w = await BasketballScoreMonitor.start(
                "SESSION",
                update_interval=3,
                teams=["phi", "ny"],
                final_hold_hours=4,
                hold_time=7.5,
                logos=False,
                ball_at=False,
            )
        assert w.teams == ["PHI", "NY"]
        kw = src.want.call_args.kwargs
        assert kw["teams"] == {"PHI", "NY"} and kw["all_games"] is False
        assert kw["final_hold_hours"] == 4 and kw["live_interval"] == 3
        assert src.polls == 1 and len(w.feed_stories) == 1
        card = w.feed_stories[0]
        assert card.hold_time == 7.5 and card.logos is False
        assert card.ball_at is False
        assert card.tracked == frozenset({"PHI", "NY"})
        loop.assert_called_once_with(w, MIN_INTERVAL, splay=False)
        spawn.assert_called_once_with("LOOP")

    async def test_league_mode_wants_all_games(self):
        src = FakeSource(_snap())
        src.want = mock.Mock()
        with (
            mock.patch.object(mod, "shared_source", return_value=src),
            mock.patch.object(mod, "spawn_tracked", mock.Mock()),
            mock.patch.object(mod, "run_monitor_loop", mock.Mock()),
        ):
            await BasketballScoreMonitor.start(None, mode="league", teams=[])
        assert src.want.call_args.kwargs["all_games"] is True
