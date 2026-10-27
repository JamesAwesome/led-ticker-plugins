"""`OverheadWidget.draw` returns an ABSOLUTE end (`cursor_pos + width`), the
core contract (`widgets/message.py`). Core's `ticker` / `one_at_a_time` loops
pop a widget only when that end goes below 0; the old `canvas, 0` return (and
painting at x=0 whatever the cursor) wedged the section on its first widget."""

import asyncio
import hashlib
import unittest.mock as mock

import PIL.features
import pytest
from led_ticker.plugin import HeadlessCanvas, ScaledCanvas
from led_ticker.ticker import Ticker

from led_ticker_flight.dashboard_layout import render_dashboard
from led_ticker_flight.data import SAMPLE_AIRCRAFT
from led_ticker_flight.hero_layout import render_hero
from led_ticker_flight.paint import shift_canvas
from led_ticker_flight.ticker_layout import render_ticker
from led_ticker_flight.widget import OverheadWidget

# Hi-res text is never pixel-pinned ACROSS platforms; these digests were
# recorded on `main` (before the change) with freetype 2.14.3 and are only
# comparable on that rasterizer.
_FT = PIL.features.version("freetype2")
needs_recorded_freetype = pytest.mark.skipif(
    _FT != "2.14.3",
    reason=f"slideshow digests recorded with freetype 2.14.3, have {_FT}",
)

_FLIGHTS = list(SAMPLE_AIRCRAFT[:3])
_CLOCK_MS = 1000.0  # mid-dwell: full brightness, no fade


def _bigsign():
    real = HeadlessCanvas(256, 64)
    return ScaledCanvas(real, scale=4, content_height=16), real


def _longboi():
    real = HeadlessCanvas(512, 64)
    return ScaledCanvas(real, scale=4, content_height=16), real


def _smallsign():
    real = HeadlessCanvas(160, 16)
    return real, real


def lit(real) -> dict:
    return {xy: v for xy, v in real._pixels.items() if v != (0, 0, 0)}


def _digest(real) -> str:
    blob = repr(sorted(lit(real).items()))
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


_DIGESTS = {
    "ticker-smallsign": "dd1eef9858a03d96",
    "ticker-bigsign": "37a0329fc7d41a44",
    "hero-bigsign": "72443644409a7cde",
    "dashboard-longboi": "25e6557a314dc508",
}
_CASES = {
    "ticker-smallsign": (render_ticker, _smallsign),
    "ticker-bigsign": (render_ticker, _bigsign),
    "hero-bigsign": (render_hero, _bigsign),
    "dashboard-longboi": (render_dashboard, _longboi),
}


@pytest.mark.parametrize(
    "name",
    [
        # BDF ticker on a scale-1 canvas has no freetype dependency.
        "ticker-smallsign",
        *(
            pytest.param(n, marks=needs_recorded_freetype)
            for n in ("ticker-bigsign", "hero-bigsign", "dashboard-longboi")
        ),
    ],
)
def test_slideshow_at_cursor_zero_is_unchanged(name):
    render, make = _CASES[name]
    canvas, real = make()
    render(canvas, _FLIGHTS, _CLOCK_MS)
    assert _digest(real) == _DIGESTS[name]


def _widget():
    w = OverheadWidget(demo=True)
    w._clock_ticks = 20  # 1 s in: past hero/dashboard's black frame at tick 0
    return w


async def _drive_one_by_one(widgets, make_canvas, monkeypatch):
    real_sleep = asyncio.sleep

    async def _zero_sleep(_s):
        await real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", _zero_sleep)
    canvas, _ = make_canvas()
    frame = mock.Mock()
    frame.swap.side_effect = lambda r: r
    queue: asyncio.Queue = asyncio.Queue()
    for w in [*widgets, None]:
        queue.put_nowait(w)
    ticker = Ticker(monitors=[], frame=frame, notif_queue=queue, scroll_speed=0)
    await asyncio.wait_for(ticker._scroll_one_by_one(canvas), 1.5)
    assert queue.empty()


async def test_one_at_a_time_advances_past_two_overhead_widgets_scale4(monkeypatch):
    await _drive_one_by_one([_widget(), _widget()], _bigsign, monkeypatch)


async def test_one_at_a_time_advances_past_two_overhead_widgets_scale1(monkeypatch):
    await _drive_one_by_one([_widget(), _widget()], _smallsign, monkeypatch)


@pytest.mark.parametrize("make", [_smallsign, _bigsign])
async def test_ticker_advances_past_two_overhead_widgets(make, monkeypatch):
    real_sleep = asyncio.sleep

    async def _zero_sleep(_s):
        await real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", _zero_sleep)
    canvas, _ = make()
    frame = mock.Mock()
    frame.swap.side_effect = lambda r: r
    queue: asyncio.Queue = asyncio.Queue()
    for w in [_widget(), _widget(), None]:
        queue.put_nowait(w)
    ticker = Ticker(monitors=[], frame=frame, notif_queue=queue, scroll_speed=0)
    await asyncio.wait_for(ticker._scroll_side_by_side(canvas), 1.5)
    assert queue.empty()


@pytest.mark.parametrize("make", [_smallsign, _bigsign, _longboi])
def test_draw_end_is_absolute(make):
    canvas, _ = make()
    _, end0 = _widget().draw(canvas)
    assert end0 == canvas.width  # slideshow (cursor 0): the card spans the panel
    for cursor in (-40, 17):
        _, end = _widget().draw(canvas, cursor)
        assert end == cursor + canvas.width


@pytest.mark.parametrize("make", [_smallsign, _bigsign, _longboi])
def test_partially_scrolled_card_paints_shifted(make):
    c0, r0 = make()
    _widget().draw(c0)
    base = lit(r0)
    scale = getattr(c0, "scale", 1)
    assert base

    for cursor in (-40, 30):
        dx = cursor * scale
        c, r = make()
        _widget().draw(c, cursor)
        expect = {
            (x + dx, y): v
            for (x, y), v in base.items()
            if 0 <= x < r.width and 0 <= x + dx < r.width
        }
        assert lit(r) == expect


@pytest.mark.parametrize("make", [_smallsign, _bigsign])
def test_empty_state_scrolls_too(make):
    w = _widget()
    w._flights = []
    c0, r0 = make()
    w.draw(c0)
    base = lit(r0)
    assert base
    scale = getattr(c0, "scale", 1)
    dx = 10 * scale
    c, r = make()
    _, end = w.draw(c, -10)
    assert end == -10 + c.width
    assert lit(r) == {(x - dx, y): v for (x, y), v in base.items() if x >= dx}


def test_shift_canvas_zero_returns_the_canvas_itself():
    c, _ = _bigsign()
    assert shift_canvas(c, 0) is c


def test_shifted_real_subfill_and_pre_shift_clip():
    from led_ticker_flight.paint import ShiftedReal

    real = HeadlessCanvas(16, 4)
    ShiftedReal(real, -2).SubFill(0, 0, 4, 9, 255, 0, 0)
    assert {x for x, _ in lit(real)} == {0, 1}
    ShiftedReal(real, 20).SubFill(0, 0, 4, 4, 255, 0, 0)  # wholly off-panel
    assert {x for x, _ in lit(real)} == {0, 1}

    real = HeadlessCanvas(16, 4)
    s = ShiftedReal(real, 4)
    s.SetPixel(-1, 0, 255, 0, 0)  # outside the card's own box: dropped
    s.SubFill(-3, 0, 5, 1, 255, 0, 0)  # clamped to pre-shift [0, 2)
    assert {x for x, _ in lit(real)} == {4, 5}
