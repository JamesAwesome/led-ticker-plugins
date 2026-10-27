"""HockeyGameCard scale dispatch: band board / ticker message at scale 1,
the physical renderers at scale>1; held cursor = the wrapper's LOGICAL
width; legacy story follows `game`; frame hooks forward."""

import asyncio
import dataclasses
import unittest.mock as mock
from typing import Any

import attrs
import pytest
from led_ticker.plugin import (
    HeadlessBackend,
    ScaledCanvas,
    SegmentMessage,
    unwrap_to_real,
)

import led_ticker_hockey._card as card_mod
from led_ticker_hockey._card import HockeyGameCard
from led_ticker_hockey._celebration import CELEBRATION_FRAMES
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
    assert c.pending == [g]


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


def _msg_text(msg):
    return "".join(t for t, _ in msg.segments)


def test_scale1_ticker_shows_stale_and_rebuilds_on_flip(smallsign):
    c = _card(layout="ticker")
    c.draw(smallsign)
    assert "STALE" not in _msg_text(c._legacy)
    c.stale = True
    c.draw(smallsign)
    assert "STALE" in _msg_text(c._legacy)
    c.stale = False
    c.draw(smallsign)
    assert "STALE" not in _msg_text(c._legacy)


def test_hires_ticker_passes_stale(bigsign):
    c = _card(layout="ticker", stale=True)
    with mock.patch.object(card_mod, "render_crawl", return_value=10) as spy:
        c.draw(bigsign)
    assert spy.call_args.kwargs["stale"] is True


# ------------------------------------- scroll sections (#113: hi-res wedge)


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


def test_scale4_crawl_returns_absolute_end(bigsign):
    """The crawl's end is `cursor_pos + run + padding` (core's absolute
    draw contract), not the run width alone."""
    c = _card(layout="ticker")
    _, at0 = c.draw(bigsign, 0)
    _, at30 = c.draw(bigsign, 30)
    _, at_neg = c.draw(bigsign, -50)
    assert at30 == at0 + 30 and at_neg == at0 - 50


def _bigsign_ticker(queue, monkeypatch, width=256):
    from led_ticker.frame import LedFrame
    from led_ticker.ticker import Ticker

    real_sleep = asyncio.sleep

    async def _yield(_delay=0, *a, **k):
        await real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", _yield)
    frame = LedFrame(backend=HeadlessBackend(width, 64))
    frame.setup()
    canvas = ScaledCanvas(frame.get_clean_canvas(), scale=4, content_height=16)
    ticker = Ticker(monitors=[], frame=frame, notif_queue=queue, scroll_speed=0.0)
    return ticker, canvas


@pytest.mark.parametrize("layout", ["auto", "ticker"])
@pytest.mark.parametrize("mode", ["one_by_one", "side_by_side"])
async def test_scroll_two_hires_cards_completes(mode, layout, monkeypatch):
    """Drive core's REAL scroll loops with two cards on a bigsign. A card
    whose end never goes negative (or never drops below the width) wedges
    the section on the first card forever (#113)."""
    queue: asyncio.Queue = asyncio.Queue()
    a, b = _card(layout, 0), _card(layout, 1)
    for item in (a, b, None):
        await queue.put(item)
    ticker, canvas = _bigsign_ticker(queue, monkeypatch)
    if mode == "one_by_one":
        run = ticker._scroll_one_by_one(canvas, cursor_pos=canvas.width)
    else:
        run = ticker._scroll_side_by_side(
            canvas, cursor_pos=canvas.width, hold_at_end=0
        )
    await asyncio.wait_for(run, 1.5)
    assert b._frame_count > 0  # the second card was reached


@pytest.mark.parametrize("mode", ["one_by_one", "side_by_side"])
async def test_scroll_with_celebration_completes(mode, monkeypatch):
    """A self-started takeover inside the real scroll loop still ends and
    hands over to the next card."""
    queue: asyncio.Queue = asyncio.Queue()
    a, b = _card("auto", 0), _card("auto", 1)
    a.queue_goals([build_demo_games(NOW)[0].goals[0]])
    for item in (a, b, None):
        await queue.put(item)
    ticker, canvas = _bigsign_ticker(queue, monkeypatch)
    if mode == "one_by_one":
        run = ticker._scroll_one_by_one(canvas, cursor_pos=canvas.width)
    else:
        run = ticker._scroll_side_by_side(
            canvas, cursor_pos=canvas.width, hold_at_end=0
        )
    await asyncio.wait_for(run, 1.5)
    assert a.pending == [] and b._frame_count > 0


def test_shifted_real_clips_both_edges_and_forwards_fills():
    from led_ticker_hockey._paint import ShiftedReal

    real = HeadlessBackend(8, 2).create_canvas()
    left, right = ShiftedReal(real, -3), ShiftedReal(real, 3)
    for x in range(8):
        left.SetPixel(x, 0, 255, 0, 0)
        right.SetPixel(x, 1, 0, 255, 0)
    assert {x for (x, y) in real._pixels if y == 0} == set(range(5))
    assert {x for (x, y) in real._pixels if y == 1} == set(range(3, 8))
    left.Fill(1, 2, 3)
    assert set(real._pixels.values()) == {(1, 2, 3)}
    right.Clear()
    assert not any(v != (0, 0, 0) for v in real._pixels.values())


@attrs.define
class _HoldSpy(HockeyGameCard):
    """Counts celebration frames drawn; queues `goal` once the engine has
    redrawn it at the same cursor `after` times (inside the end hold), or
    on its `at_draw`-th draw."""

    goal: Any = attrs.field(default=None, kw_only=True)
    after: int | None = attrs.field(default=None, kw_only=True)
    shown: int = attrs.field(default=0, kw_only=True)
    _prev: int | None = attrs.field(default=None, kw_only=True)
    _same: int = attrs.field(default=0, kw_only=True)
    at_draw: int | None = attrs.field(default=None, kw_only=True)
    draws: int = attrs.field(default=0, kw_only=True)

    def _celebrate(self, canvas, y_offset, cursor_pos, frozen):
        painted = super()._celebrate(canvas, y_offset, cursor_pos, frozen)
        self.shown += painted
        return painted

    def draw(self, canvas, cursor_pos=0, **kw):
        self._same = self._same + 1 if cursor_pos == self._prev else 0
        self._prev = cursor_pos
        self.draws += 1
        if self.after is not None and self._same > self.after:
            self.after = None
            self.queue_goals([self.goal])
        if self.at_draw is not None and self.draws >= self.at_draw:
            self.at_draw = None
            self.queue_goals([self.goal])
        return super().draw(canvas, cursor_pos, **kw)


async def _ticker_pass(cards, hold, monkeypatch, width=256):
    queue: asyncio.Queue = asyncio.Queue()
    for item in (*cards, None):
        await queue.put(item)
    ticker, canvas = _bigsign_ticker(queue, monkeypatch, width)
    run = ticker._scroll_side_by_side(canvas, cursor_pos=canvas.width, hold_at_end=hold)
    await asyncio.wait_for(run, 1.5)


def _hold_spy(idx=0, **kw):
    games = build_demo_games(NOW)
    return _HoldSpy(
        game=games[idx],
        tz=TZ,
        now_fn=lambda: NOW,
        tracked=frozenset({"PHI"}),
        goal=games[0].goals[0],
        **kw,
    )


async def test_wide_last_card_celebration_before_the_end_hold_plays_in_full(
    monkeypatch,
):
    """A last card at least as wide as the panel: the takeover's
    `canvas.width` end keeps core from fetching the section's end sentinel,
    so the end-of-scroll hold cannot start (and cut the run) until the run
    is over, even with a short `hold_time`."""
    b = _hold_spy()
    b.queue_goals([b.goal])
    await _ticker_pass([_card("auto", 1), b], 1.0, monkeypatch)
    assert b.shown == CELEBRATION_FRAMES and b.pending == []


async def test_goal_inside_the_end_hold_is_cut_then_resumes(monkeypatch):
    """README *Known limit*: a goal landing 10 ticks into a 3 s end hold
    gets the hold's remaining 50 frames; the rest plays on the next pass."""
    b = _hold_spy(after=10)
    a = _card("auto", 1)
    await _ticker_pass([a, b], 3.0, monkeypatch)
    assert b.shown == 3 * 20 - 10
    await _ticker_pass([a, b], 3.0, monkeypatch)
    assert b.shown == CELEBRATION_FRAMES and b.pending == []


@pytest.mark.parametrize("layout", ["scoreboard", "ticker"])
async def test_same_card_twice_per_tick_never_jumps(layout, monkeypatch):
    """A one-game `ticker` section cycles the SAME card object, so at the
    pass junction core draws it twice in one tick. Only the first draw may
    touch the scroll freeze, or the left copy teleports by the freeze."""
    a = _card(layout, 0)
    a.queue_goals([build_demo_games(NOW)[0].goals[0]])
    painted: dict[int, list[int]] = {}
    real_board, real_crawl = card_mod.render_scoreboard, card_mod.render_crawl

    def board(*args, **kw):
        painted.setdefault(a._frame_count, []).append(kw["x_offset"])
        return real_board(*args, **kw)

    def crawl(*args, **kw):
        painted.setdefault(a._frame_count, []).append(args[4])
        return real_crawl(*args, **kw)

    monkeypatch.setattr(card_mod, "render_scoreboard", board)
    monkeypatch.setattr(card_mod, "render_crawl", crawl)
    await _ticker_pass([a, a, a], 0.0, monkeypatch)
    assert a.pending == []
    ticks = sorted(painted)
    assert any(len(painted[t]) == 2 for t in ticks)  # the junction was drawn
    for prev, cur in zip(ticks, ticks[1:], strict=False):
        for x in painted[cur]:
            entering = x >= 64 - 2
            assert entering or any(abs(x - p) <= 1 for p in painted[prev]), (
                prev,
                painted[prev],
                cur,
                painted[cur],
            )


async def test_narrow_last_card_celebration_is_cut_then_resumes(monkeypatch):
    """README *Known limit*: a last card narrower than the panel (longboi,
    the OT-final crawl is under 128 logical px) is fully visible while the
    card before it is still on screen, so core has already fetched the end
    sentinel; once that card pops, the takeover's `canvas.width` end starts
    the hold at once and the run is cut to it, even though it started
    before the hold. The rest plays on the next pass."""
    # The goal lands on b's 120th draw: b is fully visible, a still on
    # screen and about 10 ticks from popping (a run started there needs 80
    # frames, the 3 s hold gives 60).
    b = _hold_spy(2, cfg_layout="ticker", at_draw=120)
    a = _card("ticker", 0)
    await _ticker_pass([a, b], 3.0, monkeypatch, width=512)
    assert 0 < b.shown < CELEBRATION_FRAMES
    await _ticker_pass([a, b], 3.0, monkeypatch, width=512)
    assert b.shown == CELEBRATION_FRAMES and b.pending == []
