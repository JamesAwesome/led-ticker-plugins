"""HockeyGameCard scale dispatch: band board / ticker message at scale 1,
the physical renderers at scale>1; held cursor = the wrapper's LOGICAL
width; legacy story follows `game`; frame hooks forward."""

import dataclasses
import unittest.mock as mock

from led_ticker.plugin import SegmentMessage, unwrap_to_real

import led_ticker_hockey._card as card_mod
from led_ticker_hockey._card import HockeyGameCard
from led_ticker_hockey._models import build_demo_games
from led_ticker_hockey._scoreboard import HockeyBandBoard
from led_ticker_hockey.layouts.scoreboard import render_scoreboard

from .conftest import TZ

NOW = 1_700_000_000.0


def _lit(canvas):
    return any(v != (0, 0, 0) for v in canvas._pixels.values())


def _card(layout="auto", idx=0, **kw):
    return HockeyGameCard(
        game=build_demo_games(NOW)[idx],
        tz=TZ,
        cfg_layout=layout,
        now_fn=lambda: NOW,
        tracked=frozenset({"PHI"}),
        **kw,
    )


def test_card_dispatch_scale1_vs_scale4(smallsign, bigsign):
    small = _card()
    _, cursor = small.draw(smallsign)
    assert isinstance(small._legacy, HockeyBandBoard)
    assert cursor == smallsign.width
    assert _lit(smallsign)

    spy = mock.Mock()
    big = _card(stale=True)
    with mock.patch.object(card_mod, "render_scoreboard", spy):
        _, cursor = big.draw(bigsign, y_offset=2)
    assert cursor == bigsign.width == 64
    spy.assert_called_once()
    args, kw = spy.call_args
    assert args[0] is bigsign and args[1] is big.game and args[2] == NOW
    assert kw["y_offset"] == 2 and kw["stale"] is True and kw["highlight"] is None
    assert big._legacy is None


def test_placeholder_scoreboard_never_raises(bigsign, longboi):
    for canvas in (bigsign, longboi):
        for g in build_demo_games(NOW):
            render_scoreboard(canvas, g, NOW, TZ)
        _, cursor = _card().draw(canvas)
        assert cursor == canvas.width
        assert _lit(unwrap_to_real(canvas))


def test_ticker_on_bigsign_scrolls_hires_crawl(bigsign):
    _, cursor = _card(layout="ticker").draw(bigsign)
    assert cursor > 64


def test_scale1_ticker_delegates_to_segment_message(smallsign):
    c = _card(layout="ticker")
    _, cursor = c.draw(smallsign)
    assert cursor > 0
    assert isinstance(c._legacy, SegmentMessage)


def test_legacy_story_follows_game_and_stale(smallsign):
    board = _card()
    board.draw(smallsign)
    first = board._legacy
    moved = dataclasses.replace(board.game, away_score=9)
    board.game = moved
    board.stale = True
    board.draw(smallsign)
    assert board._legacy is first  # band board reused, fields synced
    assert first.game is moved and first.stale is True

    ticker = _card(layout="ticker")
    ticker.draw(smallsign)
    msg = ticker._legacy
    ticker.draw(smallsign)
    assert ticker._legacy is msg  # cached while the game is unchanged
    ticker.game = moved
    ticker.draw(smallsign)
    assert ticker._legacy is not msg  # rebuilt: never shows a stale game


def test_hold_time_is_base_hold():
    assert _card(base_hold=4.0).hold_time == 4.0
    assert _card().hold_time == 0.0


def test_queue_goals_stub_stores():
    c = _card()
    g = build_demo_games(NOW)[0].goals[0]
    c.queue_goals([g])
    assert c.pending_goals == [g]


def test_frame_hooks_never_raise_before_or_after_draw(smallsign):
    c = _card(layout="ticker")
    c.advance_frame()
    c.pause_frame()
    c.resume_frame()
    c.reset_frame()
    c.draw(smallsign)
    c.advance_frame(visit_id=1)
    c.pause_frame()
    c.resume_frame()
    c.reset_frame()
    assert c._legacy is not None
