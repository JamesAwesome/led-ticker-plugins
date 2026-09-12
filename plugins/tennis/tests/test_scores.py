"""TennisScoreMonitor: config validation, key handling, start() wiring,
story building (live / upcoming fallback / nothing / rejected key)."""

import unittest.mock as mock

from led_ticker.plugin import TickerMessage

import led_ticker_tennis.scores as mod
from led_ticker_tennis._card import TennisMatchCard
from led_ticker_tennis._hires_line import HiresLine
from led_ticker_tennis._source import MIN_UPDATE_INTERVAL, Snapshot
from led_ticker_tennis.scores import (
    BAD_KEY_TEXT,
    NO_KEY_TEXT,
    NO_MATCHES_TEXT,
    TennisScoreMonitor,
)

from .test_models import COMPLETED_ROW, LIVE_ROW


def _row(**over):
    return {**LIVE_ROW, **over}


def _wta_row():
    return _row(
        id=2,
        tour="wta",
        players={"p1": {"name": "Iga Swiatek"}, "p2": {"name": "Aryna Sabalenka"}},
    )


def _doubles_row():
    return _row(
        id=3,
        is_doubles=True,
        players={"p1": {"name": "Cash/Glasspool"}, "p2": {"name": "Ram/Salisbury"}},
    )


class FakeSource:
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.polls = 0

    async def poll(self):
        self.polls += 1
        return self.snapshot


def _widget(snapshot=None, **kw):
    w = TennisScoreMonitor(session=None, **kw)
    w._tz = mod.ZoneInfo(w.timezone)
    if snapshot is not None:
        w._source = FakeSource(snapshot)
    return w


def _line_text(story):
    assert isinstance(story, HiresLine)
    assert isinstance(story.legacy, TickerMessage)
    return story.legacy.text


class TestValidateConfig:
    def test_valid_is_empty(self):
        cfg = {"layout": "scoreboard", "tours": ["ATP", "wta"], "draw": "singles"}
        assert TennisScoreMonitor.validate_config(cfg) == []
        assert TennisScoreMonitor.validate_config({}) == []

    def test_bad_layout_suggests(self):
        msgs = TennisScoreMonitor.validate_config({"layout": "scoreboad"})
        assert len(msgs) == 1 and "Did you mean 'scoreboard'" in msgs[0]

    def test_tours_must_be_list_of_known_strings(self):
        assert TennisScoreMonitor.validate_config({"tours": "atp"})
        assert TennisScoreMonitor.validate_config({"tours": ["atp", 3]})
        msgs = TennisScoreMonitor.validate_config({"tours": ["nba"]})
        assert msgs and "unknown value(s) ['nba']" in msgs[0]

    def test_draw_demo_max_matches(self):
        assert TennisScoreMonitor.validate_config({"draw": "mixed"})
        assert TennisScoreMonitor.validate_config({"demo": "yes"})
        for bad in (0, -1, True, "8"):
            assert TennisScoreMonitor.validate_config({"max_matches": bad}), bad
        assert TennisScoreMonitor.validate_config({"max_matches": 3}) == []


class TestStart:
    async def test_no_key_renders_message_and_never_fetches(self, monkeypatch):
        monkeypatch.delenv("LIVETENNIS_API_KEY", raising=False)
        session = mock.Mock()
        session.get.side_effect = AssertionError("must not fetch without a key")
        spawn = mock.Mock()
        with mock.patch.object(mod, "spawn_tracked", spawn):
            w = await TennisScoreMonitor.start(session)
        assert [_line_text(s) for s in w.feed_stories] == [NO_KEY_TEXT]
        assert w._source is None
        spawn.assert_not_called()

    async def test_env_key_clamps_interval_updates_and_spawns_loop(self, monkeypatch):
        monkeypatch.setenv("LIVETENNIS_API_KEY", "ltapi_env")
        spawn = mock.Mock()
        loop = mock.Mock(return_value="LOOP")
        snap = Snapshot(live=[_row()])

        async def fake_poll(self):
            return snap

        with (
            mock.patch.object(mod, "spawn_tracked", spawn),
            mock.patch.object(mod, "run_monitor_loop", loop),
            mock.patch.object(mod.LiveTennisSource, "poll", fake_poll),
        ):
            w = await TennisScoreMonitor.start(
                mock.Mock(), update_interval=60, tours=["ATP"]
            )
        assert w.api_key == "ltapi_env" and w.tours == ["atp"]
        assert w._source is not None and w._source.interval == MIN_UPDATE_INTERVAL
        loop.assert_called_once_with(w, MIN_UPDATE_INTERVAL)
        spawn.assert_called_once_with("LOOP")
        assert len(w.feed_stories) == 1 and isinstance(
            w.feed_stories[0], TennisMatchCard
        )

    async def test_config_key_beats_env(self, monkeypatch):
        monkeypatch.setenv("LIVETENNIS_API_KEY", "ltapi_env")
        # explicit Mocks: patch.object would auto-AsyncMock the async
        # run_monitor_loop and leave an un-awaited coroutine behind.
        with (
            mock.patch.object(mod, "spawn_tracked", mock.Mock()),
            mock.patch.object(mod, "run_monitor_loop", mock.Mock(return_value="LOOP")),
            mock.patch.object(
                mod.LiveTennisSource, "poll", mock.AsyncMock(return_value=Snapshot())
            ),
        ):
            w = await TennisScoreMonitor.start(mock.Mock(), api_key="ltapi_cfg")
        assert w._source is not None and w._source.api_key == "ltapi_cfg"

    async def test_demo_needs_no_key_and_no_session(self, monkeypatch):
        monkeypatch.delenv("LIVETENNIS_API_KEY", raising=False)
        spawn = mock.Mock()
        with mock.patch.object(mod, "spawn_tracked", spawn):
            w = await TennisScoreMonitor.start(None, demo=True)
        assert len(w.feed_stories) == 4
        assert {s.match.state for s in w.feed_stories} == {"live", "final", "upcoming"}
        spawn.assert_not_called()

    async def test_demo_respects_filters(self):
        w = await TennisScoreMonitor.start(None, demo=True, tours=["wta"])
        assert [s.match.tour for s in w.feed_stories] == ["wta"]


class TestUpdate:
    async def test_no_source_is_a_noop(self):
        w = _widget()
        await w.update()
        assert w.feed_stories == []

    async def test_live_rows_become_cards_main_tours_first(self):
        itf = _row(id=9, tour="itf")
        w = _widget(Snapshot(live=[itf, _wta_row(), _row()]))
        await w.update()
        cards = w.feed_stories
        assert all(isinstance(c, TennisMatchCard) for c in cards)
        assert [c.match.tour for c in cards] == ["atp", "wta", "itf"]
        assert [(c.story_index, c.story_total) for c in cards] == [
            (0, 3),
            (1, 3),
            (2, 3),
        ]
        assert cards[0].cfg_layout == "auto" and cards[0].padding == 6

    async def test_tour_and_draw_filters_and_cap(self):
        rows = [_row(), _wta_row(), _doubles_row()]
        w = _widget(Snapshot(live=rows), tours=["atp"])
        await w.update()
        assert {c.match.match_id for c in w.feed_stories} == {90211, 3}
        w = _widget(Snapshot(live=rows), draw="singles")
        await w.update()
        assert {c.match.match_id for c in w.feed_stories} == {90211, 2}
        w = _widget(Snapshot(live=rows), draw="doubles")
        await w.update()
        assert [c.match.match_id for c in w.feed_stories] == [3]
        w = _widget(Snapshot(live=rows), max_matches=1)
        await w.update()
        assert len(w.feed_stories) == 1

    async def test_falls_back_to_upcoming_when_nothing_live(self):
        upcoming = _row(id=7, status="upcoming", score=None)
        w = _widget(Snapshot(live=[], upcoming=[upcoming, COMPLETED_ROW]))
        await w.update()
        assert [c.match.match_id for c in w.feed_stories] == [7]
        assert w.feed_stories[0].match.state == "upcoming"

    async def test_nothing_at_all_renders_a_line(self):
        w = _widget(Snapshot())
        await w.update()
        assert [_line_text(s) for s in w.feed_stories] == [NO_MATCHES_TEXT]

    async def test_rejected_key_with_no_data_says_so(self):
        w = _widget(Snapshot(key_rejected=True, stale=True))
        await w.update()
        assert [_line_text(s) for s in w.feed_stories] == [BAD_KEY_TEXT]

    async def test_stale_snapshot_still_renders_cached_matches(self):
        w = _widget(Snapshot(live=[_row()], stale=True, last_error="HTTP 503"))
        await w.update()
        assert isinstance(w.feed_stories[0], TennisMatchCard)

    async def test_show_ranking_and_fonts_reach_the_card(self):
        w = _widget(Snapshot(live=[_row()]), show_ranking=True, layout="ticker")
        await w.update()
        card = w.feed_stories[0]
        assert card.show_ranking and card.cfg_layout == "ticker"
        assert card.font is not None and card.small_font is not None

    def test_list_field_hints_are_three_tuples(self):
        for key, hint in TennisScoreMonitor._LIST_FIELD_HINTS.items():
            assert isinstance(hint, tuple) and len(hint) == 3, key
