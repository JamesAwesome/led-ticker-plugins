"""HockeyScoreMonitor: config validation, story selection per mode, card
reuse across polls, goal queueing, start() wiring, demo."""

import dataclasses
import logging
import unittest.mock as mock
from datetime import UTC, datetime, timedelta

import led_ticker_hockey.scores as mod
from led_ticker_hockey._card import HockeyGameCard
from led_ticker_hockey._models import GameInfo, Goal, build_demo_games
from led_ticker_hockey._source import MIN_INTERVAL, Snapshot
from led_ticker_hockey.scores import HockeyScoreMonitor, select_stories

from .conftest import TZ

# 2026-10-22 16:00 local (20:00 UTC)
NOW_DT = datetime(2026, 10, 22, 20, 0, tzinfo=UTC)
NOW = NOW_DT.timestamp()
_TEMPLATE = build_demo_games(NOW)[0]


def game(gid, state, away="PHI", home="NYI", *, start=None, **over) -> GameInfo:
    return dataclasses.replace(
        _TEMPLATE,
        game_id=gid,
        state=state,
        away=away,
        home=home,
        start_utc=start,
        goals=(),
        **over,
    )


def final_ended(gid, hours_ago, away="PHI", home="NYI"):
    """A final whose (estimated) end was `hours_ago` hours before NOW."""
    start = NOW_DT - timedelta(hours=hours_ago) - mod.GAME_LENGTH
    return game(gid, "final", away, home, start=start)


def goal(key, team="PHI"):
    return Goal(
        key=key,
        team=team,
        scorer="KONECNY",
        season_total=1,
        assists=(),
        period_label="1ST",
        time_in_period="1:00",
        strength="ev",
        empty_net=False,
        away_score=1,
        home_score=0,
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


# ----------------------------------------------------------- validation


class TestValidateConfig:
    def test_valid_is_empty(self):
        v = HockeyScoreMonitor.validate_config
        assert v({"teams": ["phi", "NYI"]}) == []
        assert v({"mode": "league"}) == []
        assert v({"mode": "live", "layout": "ticker", "update_interval": 15}) == []

    def test_validate_unknown_team_suggests(self):
        msgs = HockeyScoreMonitor.validate_config({"teams": ["PHL"]})
        assert len(msgs) == 1
        assert "hockey.scores teams has unknown code 'PHL'." in msgs[0]
        assert "Did you mean 'PHI'?" in msgs[0]

    def test_teams_must_be_list_of_str(self):
        v = HockeyScoreMonitor.validate_config
        assert v({"teams": "PHI"})
        assert v({"teams": ["PHI", 3]})

    def test_validate_teams_mode_requires_teams(self):
        msgs = HockeyScoreMonitor.validate_config({})
        assert msgs and "teams" in msgs[0]
        assert HockeyScoreMonitor.validate_config({"mode": "teams", "teams": []})
        # demo needs no teams; league/live use teams only as priority
        assert HockeyScoreMonitor.validate_config({"demo": True}) == []
        assert HockeyScoreMonitor.validate_config({"mode": "live"}) == []

    def test_validate_bad_mode(self):
        msgs = HockeyScoreMonitor.validate_config({"mode": "leage", "teams": ["PHI"]})
        assert len(msgs) == 1
        assert "mode='leage'" in msgs[0] and "Did you mean 'league'?" in msgs[0]

    def test_validate_bad_layout_suggests(self):
        msgs = HockeyScoreMonitor.validate_config(
            {"layout": "scoreboad", "teams": ["PHI"]}
        )
        assert len(msgs) == 1 and "Did you mean 'scoreboard'?" in msgs[0]

    def test_scalars(self):
        v = HockeyScoreMonitor.validate_config
        base = {"teams": ["PHI"]}
        assert v({**base, "timezone": "Mars/Base"})
        for bad in (0, -1, True, "8", 1.5):
            assert v({**base, "max_games": bad}), bad
        for bad in (-1, True, "6", 2.5):
            assert v({**base, "final_hold_hours": bad}), bad
        assert v({**base, "final_hold_hours": 0}) == []
        assert v({**base, "demo": "yes"})
        for bad in (0, True, "15", 10.0):
            assert v({**base, "update_interval": bad}), bad


# ------------------------------------------------------------ selection


class TestSelectTeams:
    def test_select_teams_mode_dedupes_head_to_head(self):
        out = select([game(1, "live")], teams=("PHI", "NYI"))
        assert ids(out) == [1]

    def test_live_beats_final_and_next(self):
        nxt = {"PHI": game(9, "future", start=NOW_DT + timedelta(days=2))}
        out = select([final_ended(2, 1), game(1, "live")], nxt)
        assert ids(out) == [1]

    def test_select_teams_mode_final_replaces_next_until_hold_expires(self):
        nxt = {"PHI": game(9, "future", start=NOW_DT + timedelta(days=2))}
        assert ids(select([final_ended(2, 2)], nxt)) == [2]
        assert ids(select([final_ended(2, 7)], nxt)) == [9]

    def test_final_without_start_time_counts_as_inside_hold(self):
        assert ids(select([game(2, "final")])) == [2]

    def test_select_teams_mode_game_later_today(self):
        tonight = game(5, "future", start=NOW_DT + timedelta(hours=3))
        nxt = {"PHI": game(9, "future", start=NOW_DT + timedelta(days=2))}
        out = select([tonight], nxt)
        assert ids(out) == [5]
        from led_ticker_hockey._models import status_lines

        assert status_lines(out[0], NOW, TZ)[0] == "TONIGHT"

    def test_next_game_fallback_and_config_order(self):
        nxt = {
            "PHI": game(9, "future", start=NOW_DT + timedelta(days=2)),
            "NYI": game(8, "future", "NYI", "BOS", start=NOW_DT + timedelta(days=1)),
        }
        assert ids(select([], nxt, teams=("NYI", "PHI"))) == [8, 9]

    def test_offseason_is_empty(self):
        assert select([], {}) == []

    def test_untracked_games_ignored(self):
        assert select([game(1, "live", "TOR", "MTL")]) == []


class TestSelectLeague:
    def test_select_league_order(self):
        games = [
            game(10, "future", "TOR", "MTL", start=NOW_DT + timedelta(hours=4)),
            game(11, "future", "BOS", "BUF", start=NOW_DT + timedelta(hours=2)),
            final_ended(12, 1, "SEA", "VAN"),
            final_ended(13, 8, "LAK", "ANA"),  # outside the hold: dropped
            game(14, "live", "DAL", "COL"),
            game(1, "live"),  # tracked
        ]
        nxt = {"NYI": game(9, "future", "NYI", "BOS", start=NOW_DT + timedelta(days=1))}
        out = select(games, nxt, mode="league", teams=("PHI", "NYI"))
        # tracked live, other live, finals, future by start; no next-game card
        assert ids(out) == [1, 14, 12, 11, 10]
        capped = select(games, nxt, mode="league", teams=("PHI",), max_games=3)
        assert ids(capped) == [1, 14, 12]

    def test_league_excludes_future_not_today(self):
        later = game(10, "future", "TOR", "MTL", start=NOW_DT + timedelta(days=2))
        assert select([later], mode="league", teams=()) == []


class TestSelectLive:
    def test_select_live_mode_empty_when_nothing_live(self):
        games = [final_ended(2, 1), game(3, "future", start=NOW_DT)]
        assert select(games, mode="live") == []

    def test_live_tracked_first_and_capped(self):
        games = [game(14, "live", "DAL", "COL"), game(15, "live", "TOR", "MTL")]
        games.append(game(1, "live"))
        out = select(games, mode="live", teams=("PHI",))
        assert ids(out)[0] == 1 and set(ids(out)) == {1, 14, 15}
        assert len(select(games, mode="live", max_games=2)) == 2


# --------------------------------------------------------------- update


class FakeSource:
    def __init__(self, snapshot, goals=None):
        self.snapshot = snapshot
        self.goals: dict[int, tuple[Goal, ...]] = goals or {}
        self.polls = 0
        self.displayed: list[tuple[object, set[int]]] = []

    async def poll(self):
        self.polls += 1
        return self.snapshot

    def note_displayed(self, consumer, game_ids):
        self.displayed.append((consumer, set(game_ids)))

    def goals_after_baseline(self, game_id):
        return self.goals.get(game_id, ())


def _widget(snapshot, goals=None, **kw):
    kw.setdefault("teams", ["PHI"])
    w = HockeyScoreMonitor(session=None, **kw)
    w._tz = TZ
    w._source = FakeSource(snapshot, goals)
    return w


def _snap(*games, next_games=None, stale=False):
    return Snapshot(
        games={g.game_id: g for g in games},
        next_games=next_games or {},
        stale=stale,
    )


class TestUpdate:
    async def test_update_reuses_cards_across_polls(self, caplog):
        live = game(1, "live")
        w = _widget(_snap(live))
        with caplog.at_level(logging.INFO, logger=mod.__name__):
            await w.update()
        assert "hockey.scores updated: 1 stories" in caplog.text
        card = w.feed_stories[0]
        assert isinstance(card, HockeyGameCard) and card.game is live
        moved = dataclasses.replace(live, away_score=5)
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

    async def test_stale_snapshot_marks_cards(self):
        w = _widget(_snap(game(1, "live")))
        await w.update()
        assert w.feed_stories[0].stale is False
        w._source.snapshot = _snap(game(1, "live"), stale=True)
        await w.update()
        assert w.feed_stories[0].stale is True

    async def test_note_displayed_passes_self_and_shown_ids(self):
        nxt = game(9, "future", "NYI", "BOS", start=NOW_DT + timedelta(days=2))
        w = _widget(_snap(game(1, "live"), next_games={"NYI": nxt}), teams=["PHI"])
        await w.update()
        assert w._source.displayed[-1] == (w, {1})

    async def test_offseason_shows_nothing(self):
        w = _widget(_snap())
        await w.update()
        assert w.feed_stories == []

    async def test_live_mode_empty(self):
        w = _widget(_snap(final_ended(2, 1)), mode="live")
        await w.update()
        assert w.feed_stories == []

    async def test_cards_dropped_when_games_leave(self):
        w = _widget(_snap(game(1, "live")))
        await w.update()
        w._source.snapshot = _snap()
        await w.update()
        assert w.feed_stories == [] and w._cards == {}

    async def test_update_without_source_is_noop(self):
        w = HockeyScoreMonitor(session=None, teams=["PHI"])
        await w.update()
        assert w.feed_stories == []

    async def test_update_never_raises(self, caplog):
        w = _widget(_snap(game(1, "live")))

        def boom(*a, **k):
            raise RuntimeError("bad")

        with mock.patch.object(mod, "select_stories", boom):
            await w.update()
        assert w.feed_stories == []
        assert "hockey.scores update failed" in caplog.text


class TestGoals:
    async def test_first_sight_silent_then_only_new_goals_queued(self):
        g1, g2, g3 = goal("a"), goal("b"), goal("c", "NYI")
        live = game(1, "live")
        w = _widget(_snap(live), goals={1: (g1, g2)})
        await w.update()
        card = w.feed_stories[0]
        assert card.pending_goals == []
        w._source.goals[1] = (g1, g2, g3)
        await w.update()
        assert card.pending_goals == [g3]
        await w.update()
        assert card.pending_goals == [g3]  # not re-queued

    async def test_celebrated_pruned_with_game(self):
        w = _widget(_snap(game(1, "live")), goals={1: (goal("a"),)})
        await w.update()
        assert w._celebrated == {1: {"a"}}
        w._source.snapshot = _snap()
        await w.update()
        assert w._celebrated == {}


# ---------------------------------------------------------------- start


class TestStart:
    async def test_demo_builds_four_stories_without_network(self):
        spawn = mock.Mock()
        with (
            mock.patch.object(mod, "spawn_tracked", spawn),
            mock.patch.object(mod, "shared_source", side_effect=AssertionError),
        ):
            w = await HockeyScoreMonitor.start(None, demo=True)
        assert len(w.feed_stories) == 4
        assert all(isinstance(c, HockeyGameCard) for c in w.feed_stories)
        assert w._source is None
        spawn.assert_not_called()

    async def test_start_registers_interest_updates_and_spawns(self):
        live = game(1, "live")
        src = FakeSource(_snap(live))
        src.want = mock.Mock()
        spawn = mock.Mock()
        loop = mock.Mock(return_value="LOOP")
        with (
            mock.patch.object(mod, "shared_source", return_value=src),
            mock.patch.object(mod, "spawn_tracked", spawn),
            mock.patch.object(mod, "run_monitor_loop", loop),
        ):
            w = await HockeyScoreMonitor.start(
                "SESSION",
                update_interval=3,
                teams=["phi", "nyi"],
                final_hold_hours=4,
                hold_time=7.5,
            )
        assert w.teams == ["PHI", "NYI"]
        src.want.assert_called_once()
        kw = src.want.call_args.kwargs
        assert kw["teams"] == {"PHI", "NYI"} and kw["all_games"] is False
        assert kw["final_hold_hours"] == 4 and str(kw["tz"]) == "America/New_York"
        assert src.polls == 1 and len(w.feed_stories) == 1
        assert w.feed_stories[0].hold_time == 7.5
        assert w.feed_stories[0].tracked == frozenset({"PHI", "NYI"})
        loop.assert_called_once_with(w, MIN_INTERVAL)
        spawn.assert_called_once_with("LOOP")

    async def test_league_mode_wants_all_games(self):
        src = FakeSource(_snap())
        src.want = mock.Mock()
        loop = mock.Mock(return_value="LOOP")
        with (
            mock.patch.object(mod, "shared_source", return_value=src),
            mock.patch.object(mod, "spawn_tracked", mock.Mock()),
            mock.patch.object(mod, "run_monitor_loop", loop),
        ):
            w = await HockeyScoreMonitor.start(
                "SESSION", mode="league", update_interval=30
            )
        assert src.want.call_args.kwargs["all_games"] is True
        loop.assert_called_once_with(w, 30)
