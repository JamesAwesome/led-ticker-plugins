"""Shared render helpers for the held layouts (`card`, `dashboard`).

Both layouts render an identical change-line shape (arrow + signed change +
signed percent, trend-colored); this module is the single definition so the
two layouts can't drift.
"""

import math

from led_ticker.plugin import Color, make_color

from led_ticker_stocks import _palette as pal

# Bloomberg-style price flash: a fresh tick lifts the price color toward
# white, then decays back to steady dimmed amber over this many seconds.
_FLASH_DECAY_SECONDS = 0.420

# Frame-counter-driven pulses (Phase 3): both periods are tuned in ENGINE
# TICKS (ENGINE_TICK_MS = 50ms per the core held-loop cadence), not
# wall-clock seconds — the `frame` value comes from the held renderer's
# `frame_for("held")` counter, so these stay in lockstep with the render
# loop rather than drifting against it. Full sine cycle = 2*pi*PERIOD*0.05s.
STATE_PULSE_PERIOD = 7  # 2*pi*7*0.05 ~= 2.2s full cycle — LIVE chip "breathing"
ENDPOINT_PULSE_PERIOD = 5  # 2*pi*5*0.05 ~= 1.6s — faster "twinkle" on the sparkline tip


def live_pulse(frame: int) -> float:
    """LIVE-chip brightness multiplier: a slow breathing pulse, range ~[0.10, 1.00]."""
    return 0.55 + 0.45 * math.sin(frame / STATE_PULSE_PERIOD)


def endpoint_pulse(frame: int) -> float:
    """Sparkline endpoint brightness multiplier, range ~[0.35, 1.00]."""
    return 0.35 + 0.65 * (0.5 + 0.5 * math.sin(frame / ENDPOINT_PULSE_PERIOD))


def arrow(chg: float | None) -> str:
    if chg is None or chg == 0:
        return "·"  # middle dot: flat / no-data
    return "▲" if chg > 0 else "▼"  # up / down triangle


def chg_color(quote, dim: float, green_up: bool = True):
    chg = quote.change or 0
    up_color = pal.UP if green_up else pal.DOWN
    down_color = pal.DOWN if green_up else pal.UP
    base = up_color if chg > 0 else down_color if chg < 0 else pal.FLAT
    return pal.dim(base, dim)


def _lerp_color(a: Color, b: Color, t: float) -> Color:
    """Per-channel linear interpolation from `a` to `b` at `t` (0.0-1.0)."""
    return make_color(
        round(a.red + (b.red - a.red) * t),
        round(a.green + (b.green - a.green) * t),
        round(a.blue + (b.blue - a.blue) * t),
    )


def flash_price_color(flash_t: float | None, dim: float, *, now: float) -> Color:
    """Price color for this tick: steady dimmed amber, or a wall-clock decay
    toward white right after a price change (Bloomberg-style flash).

    `flash_t` is a `time.monotonic()` timestamp (or `None` if the price has
    never changed / this is the first tick). `now` is the caller's own
    `time.monotonic()` reading, passed in so this function stays pure and
    testable without mocking the clock.
    """
    k = (
        0.0
        if flash_t is None
        else max(0.0, 1.0 - (now - flash_t) / _FLASH_DECAY_SECONDS)
    )
    return _lerp_color(pal.dim(pal.PRICE, dim), pal.dim(pal.WHITE, dim), 0.95 * k)
