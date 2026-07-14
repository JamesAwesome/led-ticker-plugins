"""Shared render helpers for the held layouts (`card`, `dashboard`).

Both layouts render an identical change-line shape (arrow + signed change +
signed percent, trend-colored); this module is the single definition so the
two layouts can't drift.
"""

from led_ticker_stocks import _palette as pal


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
