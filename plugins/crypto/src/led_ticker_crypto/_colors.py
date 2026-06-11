"""Trend colors for crypto widgets (ported from led-ticker core crypto/_colors.py).

Positive / negative / neutral price movement. Constructed lazily via PEP 562
`__getattr__` (same pattern as core), so importing this module is a no-op
against the rgbmatrix graphics library.
"""

from typing import TYPE_CHECKING

from led_ticker.plugin import colors

if TYPE_CHECKING:
    from led_ticker.plugin import Color


_trend_palette = colors.lazy_palette(
    {
        "UP_TREND_COLOR": (46, 200, 46),
        "DOWN_TREND_COLOR": (194, 24, 7),
        "NEUTRAL_TREND_COLOR": (180, 180, 180),
    }
)


def __getattr__(name: str) -> Color:
    return _trend_palette(name)
