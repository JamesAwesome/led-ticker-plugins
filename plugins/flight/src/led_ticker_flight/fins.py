"""Swept tail-fin silhouette (trademark-safe airline brand cue).

Geometry translated from design/app.js drawTail(); all rounding is
JavaScript Math.round (half-up), NOT Python banker's rounding.
"""

import math

from led_ticker_flight.palette import RGB, Airline


def js_round(v: float) -> int:
    """JavaScript Math.round: half always rounds up (toward +inf)."""
    return math.floor(v + 0.5)


def fin_width(h: int) -> int:
    return max(4, js_round(h * 0.82))


def draw_fin(
    set_px, x: int, y: int, h: int, airline: Airline, bright: float = 1.0
) -> int:
    """Paint the fin with top-left at (x, y); returns the fin width."""
    w = fin_width(h)
    lean = js_round(w * 0.52)
    band_top = js_round(h * 0.5)
    band_h = max(1, js_round(h * 0.16))
    for r in range(h):
        frac = r / (h - 1)
        lx = js_round(lean * (1 - frac))
        col: RGB = airline.c2 if band_top <= r < band_top + band_h else airline.c1
        for xx in range(lx, w):
            set_px(x + xx, y + r, col, bright)
    return w
