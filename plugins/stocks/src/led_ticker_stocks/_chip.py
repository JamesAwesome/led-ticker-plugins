"""Trademark-safe brand chip: abstract two-tone diagonal mark (colors, never a logo)."""

import hashlib

from led_ticker.plugin import Color, make_color, unwrap_to_real

from led_ticker_stocks import _palette as pal
from led_ticker_stocks._paint import px


def _hash_hue_pair(sym: str) -> tuple[Color, Color]:
    h = hashlib.md5(sym.encode(), usedforsecurity=False).digest()
    # two distinct saturated-ish tones from the digest bytes
    c1 = make_color(64 + h[0] % 192, 64 + h[1] % 192, 64 + h[2] % 192)
    c2 = make_color(64 + h[3] % 192, 64 + h[4] % 192, 64 + h[5] % 192)
    return c1, c2


def chip_colors_for(
    sym: str, override: tuple[Color, Color] | None
) -> tuple[Color, Color]:
    if override:
        return override
    return _hash_hue_pair(sym)


def _knocked(col: int, row: int, size: int) -> bool:
    r = 2 if size >= 10 else (1 if size >= 6 else 0)
    if r == 0:
        return False
    for cx, cy in ((0, 0), (size - 1, 0), (0, size - 1), (size - 1, size - 1)):
        if abs(col - cx) + abs(row - cy) < r:
            return True
    return False


def draw_chip(canvas, x: int, y: int, size: int, quote, *, dim: float) -> None:
    real = unwrap_to_real(canvas) if hasattr(canvas, "scale") else canvas
    c1, c2 = chip_colors_for(quote.sym, quote.chip_colors)
    for row in range(size):
        for col in range(size):
            if _knocked(col, row, size):
                continue
            tone = c2 if (col - row) > 0 else c1
            px(real, x + col, y + row, pal.dim(tone, dim))
