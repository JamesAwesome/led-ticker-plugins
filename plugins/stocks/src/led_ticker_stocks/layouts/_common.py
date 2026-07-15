"""Shared render helpers for the held layouts (`card`, `dashboard`).

Both layouts render an identical change-line shape (arrow + signed change +
signed percent, trend-colored); this module is the single definition so the
two layouts can't drift.
"""

from led_ticker.plugin import Color, make_color

from led_ticker_stocks import _palette as pal

# Bloomberg-style price flash: a fresh tick lifts the price color toward
# white, then decays back to steady dimmed amber over this many seconds.
_FLASH_DECAY_SECONDS = 0.420


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
