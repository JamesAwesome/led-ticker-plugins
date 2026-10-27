"""FootballGameCard scale dispatch: band board / ticker message at scale 1,
the physical renderers at scale>1; held cursor = the wrapper's LOGICAL
width; legacy story follows `game`; frame hooks forward."""

import dataclasses
import inspect
import unittest.mock as mock

from led_ticker.plugin import (
    HeadlessBackend,
    ScaledCanvas,
    SegmentMessage,
    unwrap_to_real,
)

import led_ticker_football._card as card_mod
from led_ticker_football._card import FootballGameCard
from led_ticker_football._models import build_demo_games
from led_ticker_football._scoreboard import FootballBandBoard
from led_ticker_football.layouts.scoreboard import render_scoreboard

from .conftest import TZ

NOW = 1_700_000_000.0
GAMES, TD = build_demo_games(NOW)


def _lit(canvas):
    return any(v != (0, 0, 0) for v in canvas._pixels.values())


def _card(layout="auto", idx=0, **kw):
    return FootballGameCard(
        game=GAMES[idx],
        tz=TZ,
        cfg_layout=layout,
        now_fn=lambda: NOW,
        tracked=frozenset({"PHI"}),
        **kw,
    )


def test_scale1_uses_band_board(smallsign):
    small = _card()
    _, cursor = small.draw(smallsign)
    assert isinstance(small._legacy, FootballBandBoard)
    assert cursor == smallsign.width
    assert _lit(smallsign)


def test_scale4_calls_render_scoreboard(bigsign):
    spy = mock.Mock()
    big = _card(stale=True, idx=4, bye=True)
    with mock.patch.object(card_mod, "render_scoreboard", spy):
        _, cursor = big.draw(bigsign, y_offset=2)
    assert cursor == bigsign.width == 64
    spy.assert_called_once()
    args, kw = spy.call_args
    assert args[0] is bigsign and args[1] is big.game and args[2] == NOW
    assert kw["y_offset"] == 2 and kw["stale"] is True and kw["highlight"] is None
    assert kw["bye"] is True
    assert big._legacy is None


def test_placeholder_scoreboard_never_raises(bigsign, longboi):
    for canvas in (bigsign, longboi):
        for g in GAMES:
            render_scoreboard(canvas, g, NOW, TZ)
        _, cursor = _card().draw(canvas)
        assert cursor == canvas.width
        assert _lit(unwrap_to_real(canvas))


def test_ticker_layout_adds_padding(bigsign):
    c = _card(layout="ticker", padding=9)
    with mock.patch.object(card_mod, "render_crawl", return_value=100) as spy:
        _, cursor = c.draw(bigsign, 5)
    assert cursor == 5 + 100 + 9  # a scroll section's cursor advances the run
    assert spy.call_args.kwargs["hold_padding"] == 9


def test_scale1_ticker_delegates_to_segment_message(smallsign):
    c = _card(layout="ticker")
    _, cursor = c.draw(smallsign)
    assert cursor > 0
    assert isinstance(c._legacy, SegmentMessage)


def test_legacy_story_follows_game_stale_and_bye(smallsign):
    board = _card()
    board.draw(smallsign)
    first = board._legacy
    moved = dataclasses.replace(board.game, away_score=9)
    board.game = moved
    board.stale = True
    board.bye = True
    board.draw(smallsign)
    assert board._legacy is first  # band board reused, fields synced
    assert first.game is moved and first.stale is True and first.bye is True

    ticker = _card(layout="ticker")
    ticker.draw(smallsign)
    msg = ticker._legacy
    ticker.draw(smallsign)
    assert ticker._legacy is msg  # cached while the game is unchanged
    ticker.game = moved
    ticker.draw(smallsign)
    assert ticker._legacy is not msg  # rebuilt: never shows a stale game


def test_has_play_shape_is_sync_draw():
    assert not hasattr(FootballGameCard, "play")
    assert not inspect.iscoroutinefunction(FootballGameCard.draw)


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


def test_hires_ticker_passes_stale_and_bye(bigsign):
    c = _card(layout="ticker", stale=True, bye=True, idx=4)
    with mock.patch.object(card_mod, "render_crawl", return_value=10) as spy:
        c.draw(bigsign)
    assert spy.call_args.kwargs["stale"] is True
    assert spy.call_args.kwargs["bye"] is True


def _lit_cols(real):
    return {x for (x, _y), v in real._pixels.items() if v != (0, 0, 0)}


def _fresh_bigsign():
    real = HeadlessBackend(256, 64).create_canvas()
    return ScaledCanvas(real, scale=4, content_height=16), real


def test_scale4_scoreboard_scrolls_with_cursor_pos(bigsign):
    """A `ticker` / `one_at_a_time` section hands the card a moving
    cursor; the board must paint there and report its right edge, or the
    engine never sees it leave and the section wedges forever."""
    _card().draw(bigsign)
    cols0 = _lit_cols(unwrap_to_real(bigsign))
    assert cols0

    canvas, real = _fresh_bigsign()
    _, cursor = _card().draw(canvas, 10)
    assert cursor == 10 + canvas.width
    assert _lit_cols(real) == {x + 40 for x in cols0 if x + 40 < 256}

    canvas, real = _fresh_bigsign()
    _, cursor = _card().draw(canvas, -20)
    assert cursor == -20 + canvas.width
    assert _lit_cols(real) == {x - 80 for x in cols0 if x >= 80}
