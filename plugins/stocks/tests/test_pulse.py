import math

from led_ticker.plugin import HeadlessBackend, ScaledCanvas

from led_ticker_stocks.layouts._common import (
    STATE_PULSE_PERIOD,
    endpoint_pulse,
    live_pulse,
)
from led_ticker_stocks.layouts.card import draw_card_story
from led_ticker_stocks.model import SymbolQuote
from led_ticker_stocks.state import MarketState


def test_pulse_helpers_vary_and_bounded():
    vals = [live_pulse(f) for f in range(0, 100)]
    assert min(vals) >= 0.09 and max(vals) <= 1.01
    assert max(vals) - min(vals) > 0.5  # genuinely pulses
    e = [endpoint_pulse(f) for f in range(0, 100)]
    assert min(e) >= 0.34 and max(e) <= 1.01 and max(e) - min(e) > 0.5


def _bigsign():
    real = HeadlessBackend(256, 64).create_canvas()
    return ScaledCanvas(real, scale=4, content_height=16), real


def _q():
    q = SymbolQuote(sym="AAPL", price=317.31, prev=315.32, d=1.99, dp=0.6311)
    for p in [315.0, 316.0, 317.31]:
        q.spark.append(p)
    return q


def _bright(real):
    return sum(sum(v) for v in real._pixels.values())


def test_live_chip_pulses_when_open():
    # two frames a half-period apart -> different total brightness
    # (chip + endpoint pulse)
    lo = int(STATE_PULSE_PERIOD * math.pi * 1.5)  # near the trough
    hi = int(STATE_PULSE_PERIOD * math.pi * 0.5)  # near the peak
    ch, rh = _bigsign()
    draw_card_story(
        ch, _q(), MarketState.OPEN, {}, [], focus_index=0, total=1, frame=hi
    )
    cl, rl = _bigsign()
    draw_card_story(
        cl, _q(), MarketState.OPEN, {}, [], focus_index=0, total=1, frame=lo
    )
    assert _bright(rh) != _bright(rl)


def test_no_pulse_when_closed():
    c0, r0 = _bigsign()
    draw_card_story(
        c0, _q(), MarketState.CLOSED, {}, [], focus_index=0, total=1, frame=0
    )
    c1, r1 = _bigsign()
    draw_card_story(
        c1, _q(), MarketState.CLOSED, {}, [], focus_index=0, total=1, frame=40
    )

    # CLOSED: the state chip is steady, but the sparkline endpoint still
    # pulses with `frame` regardless of market state — isolate the chip
    # region only. The card's CLOSED-state chip label draws at real coords
    # (192, 37 + yoff) with an "AT CLOSE" line below it at (192, 47 + yoff);
    # the sparkline sits at real x=4..182, well clear of x>=192, so a bbox
    # of x>=192, y<=57 (chip label + AT CLOSE row) cleanly excludes the
    # sparkline's endpoint pixel.
    def chip(real):
        return {xy: v for xy, v in real._pixels.items() if xy[0] >= 192 and xy[1] <= 57}

    assert chip(r0) == chip(r1)  # CLOSED chip does not pulse
