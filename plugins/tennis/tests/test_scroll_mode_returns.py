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
