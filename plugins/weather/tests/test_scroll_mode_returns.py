"""`ForecastWidget.draw()` returns an ABSOLUTE end (`cursor_pos +
canvas.width`), the core contract (`widgets/message.py`). Core's `ticker` /
`one_at_a_time` loops pop a widget only when that end goes below 0; a bare
`canvas.width` never does, so the section wedged on the forecast forever.

`led_ticker.ticker.Ticker` is a core-internal import — fine in tests (the
import-purity tripwire walks `src/` only)."""

import asyncio
import unittest.mock as mock

import pytest
from led_ticker.plugin import HeadlessBackend, ScaledCanvas
from led_ticker.ticker import Ticker

from led_ticker_weather.forecast import ForecastWidget


def _fc():
    return ForecastWidget(location="", demo=True)


def _fresh(width, scale=4):
    real = HeadlessBackend(width, 64 if scale > 1 else 16).create_canvas()
    if scale == 1:
        return real, real
    return ScaledCanvas(real, scale=scale, content_height=16), real


def _cols(real):
    return {x for (x, _y), v in real._pixels.items() if v != (0, 0, 0)}


@pytest.mark.parametrize("width,scale", [(256, 4), (512, 4), (160, 1)])
async def test_one_at_a_time_advances_past_forecasts(width, scale, monkeypatch):
    real_sleep = asyncio.sleep

    async def _zero_sleep(_s):
        await real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", _zero_sleep)
    canvas, _ = _fresh(width, scale)
    frame = mock.Mock()
    frame.swap.side_effect = lambda r: r
    queue: asyncio.Queue = asyncio.Queue()
    for w in (_fc(), _fc(), None):
        queue.put_nowait(w)
    ticker = Ticker(monitors=[], frame=frame, notif_queue=queue, scroll_speed=0)
    await asyncio.wait_for(ticker._scroll_one_by_one(canvas), 1.5)
    assert queue.empty()


@pytest.mark.parametrize("width,scale", [(256, 4), (512, 4), (160, 1)])
def test_end_is_absolute_and_paints_shifted(width, scale):
    c0, r0 = _fresh(width, scale)
    _, end0 = _fc().draw(c0)
    assert end0 == c0.width  # slideshow (cursor 0) unchanged
    cols0 = _cols(r0)
    dx = 40 * scale
    assert any(x >= dx for x in cols0)

    c, r = _fresh(width, scale)
    _, end = _fc().draw(c, -40)
    assert end == -40 + c.width
    assert _cols(r) == {x - dx for x in cols0 if x >= dx}


def test_no_data_end_is_absolute():
    w = _fc()
    w._data = None
    c, _ = _fresh(256)
    assert w.draw(c, -5)[1] == -5 + c.width


def test_shifted_real_subfill_shifts_and_clips():
    from led_ticker_weather.paint import ShiftedReal, shift_canvas

    real = HeadlessBackend(16, 4).create_canvas()
    ShiftedReal(real, -2).SubFill(0, 0, 4, 9, 255, 0, 0)
    assert _cols(real) == {0, 1}
    ShiftedReal(real, 20).SubFill(0, 0, 4, 4, 255, 0, 0)  # wholly off-panel
    assert _cols(real) == {0, 1}
    c, _ = _fresh(256)
    assert shift_canvas(c, 0) is c


@pytest.mark.parametrize("cursor", [-64, -40, 20])
def test_shifted_strip_never_reveals_overflow_cursor_0_hid(cursor):
    """An explicit `layout = "strip"` at scale 4 lays its cells partly at
    negative x; cursor 0 clips that. Shifted, it must stay clipped to the
    card's own box: the lit set is exactly cursor 0's, translated."""
    c0, r0 = _fresh(256)
    w = ForecastWidget(location="", demo=True, layout="strip")
    w.draw(c0)
    cols0 = _cols(r0)
    dx = cursor * 4
    c, r = _fresh(256)
    ForecastWidget(location="", demo=True, layout="strip").draw(c, cursor)
    assert _cols(r) == {x + dx for x in cols0 if 0 <= x + dx < 256}


def test_shifted_real_drops_pixels_outside_the_cards_own_box():
    from led_ticker_weather.paint import ShiftedReal

    real = HeadlessBackend(16, 4).create_canvas()
    s = ShiftedReal(real, 4)
    s.SetPixel(-1, 0, 255, 0, 0)  # outside the card's own box: dropped
    s.SubFill(-3, 0, 5, 1, 255, 0, 0)  # clamped to pre-shift [0, 2)
    assert _cols(real) == {4, 5}
