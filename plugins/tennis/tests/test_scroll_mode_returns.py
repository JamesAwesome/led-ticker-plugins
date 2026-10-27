"""Hi-res `draw()` returns an ABSOLUTE end (`cursor_pos + width`), the core
contract (`widgets/message.py`). Core's `ticker` / `one_at_a_time` loops pop
a widget only when that end goes below 0; a cursor-relative return never
does, so the section wedged on its first card forever."""

import asyncio
import unittest.mock as mock

from led_ticker.plugin import (
    HeadlessBackend,
    ScaledCanvas,
    TickerMessage,
    make_color,
)
from led_ticker.ticker import Ticker

from led_ticker_tennis._card import TennisMatchCard
from led_ticker_tennis._hires_line import HiresLine

from .conftest import TZ, lit, live_match

WHITE = make_color(255, 255, 255)


def _fresh_bigsign():
    real = HeadlessBackend(256, 64).create_canvas()
    return ScaledCanvas(real, scale=4, content_height=16), real


def _cols(real):
    return {x for x, _ in lit(real)}


def _card(layout="auto"):
    return TennisMatchCard(match=live_match(), tz=TZ, cfg_layout=layout)


def _line():
    text = "No tennis matches right now"
    return HiresLine([(text, WHITE)], legacy=TickerMessage(text, font_color=WHITE))


async def _drive_one_by_one(widgets, monkeypatch):
    real_sleep = asyncio.sleep

    async def _zero_sleep(_s):
        await real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", _zero_sleep)
    canvas, _ = _fresh_bigsign()
    frame = mock.Mock()
    frame.swap.side_effect = lambda r: r
    queue: asyncio.Queue = asyncio.Queue()
    for w in [*widgets, None]:
        queue.put_nowait(w)
    ticker = Ticker(monitors=[], frame=frame, notif_queue=queue, scroll_speed=0)
    await asyncio.wait_for(ticker._scroll_one_by_one(canvas), 1.5)
    assert queue.empty()


async def test_one_at_a_time_advances_past_hires_scoreboards(monkeypatch):
    await _drive_one_by_one([_card(), _card()], monkeypatch)


async def test_one_at_a_time_advances_past_hires_crawls(monkeypatch):
    await _drive_one_by_one([_card("ticker"), _card("ticker")], monkeypatch)


async def test_one_at_a_time_advances_past_hires_status_lines(monkeypatch):
    await _drive_one_by_one([_line(), _line()], monkeypatch)


def test_scoreboard_end_is_absolute_and_paints_shifted():
    c0, r0 = _fresh_bigsign()
    _, end0 = _card().draw(c0)
    assert end0 == c0.width  # slideshow (cursor 0) unchanged
    cols0 = _cols(r0)
    assert any(x >= 160 for x in cols0)

    c, r = _fresh_bigsign()
    _, end = _card().draw(c, -40)
    assert end == -40 + c.width
    assert _cols(r) == {x - 160 for x in cols0 if x >= 160}


def test_crawl_end_is_absolute():
    c0, _ = _fresh_bigsign()
    _, end0 = _card("ticker").draw(c0)
    c, _ = _fresh_bigsign()
    _, end = _card("ticker").draw(c, -40)
    assert end == -40 + end0


def test_status_line_end_is_absolute_and_paints_shifted():
    c0, r0 = _fresh_bigsign()
    _, end0 = _line().draw(c0)
    assert end0 == c0.width
    cols0 = _cols(r0)

    c, r = _fresh_bigsign()
    _, end = _line().draw(c, -40)
    assert end == -40 + c.width
    assert _cols(r) == {x - 160 for x in cols0 if x >= 160}


def _fitting_crawl():
    m = live_match(
        p1="Fils",
        p2="Ruud",
        tournament="",
        round_code="",
        state="upcoming",
        sets=(0, 0),
        games=[],
        points=(None, None),
        server=None,
    )
    return TennisMatchCard(match=m, tz=TZ, cfg_layout="ticker")


def test_fitting_crawl_end_covers_its_centred_paint():
    """A crawl that fits is painted CENTRED across the panel, so its end
    must be the panel's right edge, not `cursor + run + padding` (which
    let core pop it / butt the next widget into it with its tail lit)."""
    width = 128  # longboi logical
    for cursor in (0, -40, -(width - 1)):
        real = HeadlessBackend(512, 64).create_canvas()
        c = ScaledCanvas(real, scale=4, content_height=16)
        _, end = _fitting_crawl().draw(c, cursor)
        assert end == cursor + width
        cols = _cols(real)
        assert cursor != 0 or cols
        assert not cols or max(cols) < end * 4


def test_shifted_real_subfill_and_pre_shift_clip():
    from led_ticker_tennis._paint import ShiftedReal

    real = HeadlessBackend(16, 4).create_canvas()
    ShiftedReal(real, -2).SubFill(0, 0, 4, 9, 255, 0, 0)
    assert _cols(real) == {0, 1}
    ShiftedReal(real, 20).SubFill(0, 0, 4, 4, 255, 0, 0)  # wholly off-panel
    assert _cols(real) == {0, 1}

    real = HeadlessBackend(16, 4).create_canvas()
    s = ShiftedReal(real, 4)
    s.SetPixel(-1, 0, 255, 0, 0)  # outside the card's own box: dropped
    s.SubFill(-3, 0, 5, 1, 255, 0, 0)  # clamped to pre-shift [0, 2)
    assert _cols(real) == {4, 5}
