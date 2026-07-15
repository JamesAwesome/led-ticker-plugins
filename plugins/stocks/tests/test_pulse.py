import math

from led_ticker.plugin import HeadlessBackend, ScaledCanvas

from led_ticker_stocks.layouts._common import (
    ENDPOINT_PULSE_PERIOD,
    STATE_PULSE_PERIOD,
    endpoint_pulse,
    live_pulse,
)
from led_ticker_stocks.layouts.card import draw_card_story
from led_ticker_stocks.layouts.dashboard import draw_dashboard_story
from led_ticker_stocks.model import SymbolQuote
from led_ticker_stocks.state import MarketState

# Two frames a half-period apart, derived from the period constants (not
# hardcoded) so a future retune of STATE_PULSE_PERIOD / ENDPOINT_PULSE_PERIOD
# can't silently desync these tests from the sine curve's actual peak/trough.
_STATE_HI = round(STATE_PULSE_PERIOD * math.pi * 0.5)  # near the peak
_STATE_LO = round(STATE_PULSE_PERIOD * math.pi * 1.5)  # near the trough
_ENDPOINT_HI = round(ENDPOINT_PULSE_PERIOD * math.pi * 0.5)  # near the peak
_ENDPOINT_LO = round(ENDPOINT_PULSE_PERIOD * math.pi * 1.5)  # near the trough


def test_pulse_helpers_vary_and_bounded():
    vals = [live_pulse(f) for f in range(0, 100)]
    assert min(vals) >= 0.09 and max(vals) <= 1.01
    assert max(vals) - min(vals) > 0.5  # genuinely pulses
    e = [endpoint_pulse(f) for f in range(0, 100)]
    assert min(e) >= 0.34 and max(e) <= 1.01 and max(e) - min(e) > 0.5


def _bigsign():
    real = HeadlessBackend(256, 64).create_canvas()
    return ScaledCanvas(real, scale=4, content_height=16), real


def _longboi():
    real = HeadlessBackend(512, 64).create_canvas()
    return ScaledCanvas(real, scale=4, content_height=16), real


def _q():
    q = SymbolQuote(sym="AAPL", price=317.31, prev=315.32, d=1.99, dp=0.6311)
    for p in [315.0, 316.0, 317.31]:
        q.spark.append(p)
    return q


def _dash_quotes():
    q = SymbolQuote(sym="AAPL", price=317.31, prev=315.32, d=1.99, dp=0.6311)
    for p in [315.0, 316.0, 317.31]:
        q.spark.append(p)
    return {"AAPL": q}, ["AAPL"]


def _bright(real):
    return sum(sum(v) for v in real._pixels.values())


def test_live_chip_pulses_when_open():
    # Isolate the CARD state-chip region only (the same bbox
    # `test_no_pulse_when_closed` uses below) so this test has teeth for the
    # chip-pulse wiring specifically: it must fail if
    # `chip_dim = dim * live_pulse(frame)` were reverted to `chip_dim = dim`,
    # independent of the sparkline endpoint (which pulses on its own period
    # regardless of state and would otherwise mask a reverted chip).
    ch, rh = _bigsign()
    draw_card_story(
        ch, _q(), MarketState.OPEN, {}, [], focus_index=0, total=1, frame=_STATE_HI
    )
    cl, rl = _bigsign()
    draw_card_story(
        cl, _q(), MarketState.OPEN, {}, [], focus_index=0, total=1, frame=_STATE_LO
    )

    def chip(real):
        return {xy: v for xy, v in real._pixels.items() if xy[0] >= 192 and xy[1] <= 57}

    assert chip(rh) != chip(rl)  # OPEN chip breathes with frame


def test_card_sparkline_endpoint_pulses_with_frame_in_layout():
    # Teeth for the `frame=frame` pass-through from `draw_card_story` into
    # `draw_sparkline` at the LAYOUT level (as opposed to `_sparkline.py`'s
    # own unit tests) — would fail if the card passed a constant instead of
    # `frame`. Isolate the sparkline's real-pixel bbox (x=4..182, y=41..60 at
    # y_offset=0, per `draw_card_story`'s `draw_sparkline(canvas, 4, 41+yoff,
    # 178, 19, ...)` call) so this is independent of the chip-pulse region
    # above. CLOSED state keeps the chip steady so any diff here is
    # unambiguously the sparkline endpoint.
    ch, rh = _bigsign()
    draw_card_story(
        ch,
        _q(),
        MarketState.CLOSED,
        {},
        [],
        focus_index=0,
        total=1,
        frame=_ENDPOINT_HI,
    )
    cl, rl = _bigsign()
    draw_card_story(
        cl,
        _q(),
        MarketState.CLOSED,
        {},
        [],
        focus_index=0,
        total=1,
        frame=_ENDPOINT_LO,
    )

    def spark(real):
        return {
            xy: v
            for xy, v in real._pixels.items()
            if 4 <= xy[0] <= 182 and 41 <= xy[1] <= 60
        }

    assert spark(rh) != spark(rl)  # sparkline endpoint twinkles with frame


def test_dashboard_live_chip_pulses_when_open():
    # Dashboard analogue of test_live_chip_pulses_when_open: isolate the
    # hero state-chip text region only (`draw_dashboard_story` draws
    # `meta.chip_label` at real x=32 (hero x=6 + chip width 26), y=48+yoff
    # while OPEN). Bbox excludes the symbol chip icon (x=6..25, y=6..25),
    # the price block (x>=150), and the watch column / paging dots
    # (x>=434), so a diff here is unambiguously the LIVE-chip pulse.
    quotes, symbols = _dash_quotes()
    ch, rh = _longboi()
    draw_dashboard_story(
        ch,
        quotes["AAPL"],
        MarketState.OPEN,
        quotes,
        symbols,
        focus_index=0,
        total=1,
        frame=_STATE_HI,
    )
    cl, rl = _longboi()
    draw_dashboard_story(
        cl,
        quotes["AAPL"],
        MarketState.OPEN,
        quotes,
        symbols,
        focus_index=0,
        total=1,
        frame=_STATE_LO,
    )

    def chip(real):
        return {
            xy: v
            for xy, v in real._pixels.items()
            if 26 <= xy[0] < 150 and 40 <= xy[1] < 64
        }

    assert chip(rh) != chip(rl)  # dashboard hero chip breathes with frame


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
