"""stocks.trend color provider: tint text by a symbol's day change.

Green (up) / red (down) / neutral (flat or no-data), read from the shared
QuoteCache. Whole-string provider. Requires a stocks.quote source or
stocks.ticker widget in the same config to feed the symbol — this provider
reads the cache but never starts it or performs I/O.
"""

from typing import Any

from led_ticker.plugin import Color, ColorProviderBase, make_color

from led_ticker_stocks import _palette as pal
from led_ticker_stocks._cache import get_cache

_DEFAULT_FLAT: Color = make_color(150, 150, 150)  # neutral gray


def _coerce_rgb(value: Any, field: str) -> Color:
    if not (isinstance(value, (list, tuple)) and len(value) == 3):
        raise ValueError(f"stocks.trend '{field}' must be [r, g, b]; got {value!r}")
    if not all(isinstance(c, int) and not isinstance(c, bool) for c in value):
        raise ValueError(
            f"stocks.trend '{field}' components must be ints; got {list(value)!r}"
        )
    if not all(0 <= c <= 255 for c in value):
        raise ValueError(
            f"stocks.trend '{field}' RGB must be 0-255; got {list(value)!r}"
        )
    return make_color(*value)


class StocksTrendColor(ColorProviderBase):
    """Green up / red down / neutral flat, by a symbol's day change."""

    per_char: bool = False
    frame_invariant: bool = False  # tracks live data — re-evaluate each draw

    def __init__(
        self,
        symbol: Any = None,
        up: Any = None,
        down: Any = None,
        flat: Any = None,
        green_up: bool = True,
    ) -> None:
        if not isinstance(symbol, str) or not symbol.strip():
            raise ValueError(
                "stocks.trend requires a non-empty 'symbol' string: "
                "font_color = {style = 'stocks.trend', symbol = 'AAPL'}"
            )
        if "/" in symbol:
            raise ValueError(
                f"stocks.trend symbol {symbol!r} looks like a forex pair; "
                "Finnhub's free tier is equities-only (forex requires a paid tier)."
            )
        self.symbol = symbol
        self._up = _coerce_rgb(up, "up") if up is not None else pal.UP
        self._down = _coerce_rgb(down, "down") if down is not None else pal.DOWN
        self._flat = _coerce_rgb(flat, "flat") if flat is not None else _DEFAULT_FLAT
        self._green_up = bool(green_up)
        # Join the symbol to the shared cache's union so it rides the poll loop
        # a source/widget starts (Phase-4 late-registrant catch-up covers this).
        # Does NOT start the cache — a provider has no session/async context.
        get_cache().register([symbol])

    def color_for(self, frame: int, char_index: int, total_chars: int) -> Color:
        q = get_cache().get(self.symbol)
        chg = (q.change if q is not None else None) or 0
        up, down = (self._up, self._down) if self._green_up else (self._down, self._up)
        if chg > 0:
            return up
        if chg < 0:
            return down
        return self._flat
