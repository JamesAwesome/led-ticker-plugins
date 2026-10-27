"""Physical-pixel hi-res paint helpers for the scale>1 renderers — the
hockey/baseball/stocks `_paint` pattern: wrap the REAL canvas at scale=1
so `draw_text` places Inter glyphs at exact physical coordinates.

Measurement goes through core's `hires_text_width` / `fit_text_size`
(the CONTRIBUTING.md layout invariant, items (a) and (b)): the same glyph
resolution the renderer paints with, so a clearance computed here is a
real on-panel clearance on any platform's freetype metrics.
"""

import math

from led_ticker.plugin import (
    Color,
    ScaledCanvas,
    draw_text,
    fit_text_size,
    hires_text_width,
    resolve_font,
    unwrap_to_real,
)

# No rasterization threshold is passed: core defaults it per font
# (led-ticker-core >= 4.30), and Inter-Bold's default is the 128 this pack
# needs to keep small adjacent glyphs separate.
_FONT = "Inter-Bold"


def js_round(v: float) -> int:
    """JS Math.round semantics: half-up (floor(v + 0.5)) — the convention the
    sibling packs' handoff geometry was authored against."""
    return math.floor(v + 0.5)


def cap_top(y_target: int, size: int) -> int:
    """Visual cap-top y -> `hires()`'s ascent-box-top y (the formula the
    baseball/flight renderers hardware-validated: Inter's ascent is taller
    than its cap height, so a naive 1:1 y renders text low)."""
    return y_target - size + js_round(size * 0.72)


class ShiftedReal:
    """A real canvas translated by `dx` physical px (negative = left).
    Pixels that land outside the panel are dropped, so a board scrolling
    through a `ticker` / `one_at_a_time` section clips at both edges."""

    __slots__ = ("_dx", "_real", "height", "width")

    def __init__(self, real, dx: int) -> None:
        self._real = real
        self._dx = dx
        self.width: int = real.width
        self.height: int = real.height

    def SetPixel(self, x: int, y: int, r: int, g: int, b: int) -> None:  # noqa: N802
        x += self._dx
        if 0 <= x < self.width and 0 <= y < self.height:
            self._real.SetPixel(x, y, r, g, b)

    def Clear(self) -> None:  # noqa: N802
        self._real.Clear()

    def Fill(self, r: int, g: int, b: int) -> None:  # noqa: N802
        self._real.Fill(r, g, b)


def phys_wrap(canvas, x_offset_real: int = 0):
    """(scale-1 shim for hi-res text, real canvas) for physical painting.
    `x_offset_real` translates everything painted through either by that
    many physical px (the scroll position of a card in a scroll section)."""
    real = unwrap_to_real(canvas)
    if x_offset_real:
        real = ShiftedReal(real, x_offset_real)
    return ScaledCanvas(real, scale=1, content_height=real.height), real


def hires(shim, text: str, x: int, y_top: int, color: Color, size: int) -> int:
    """Paint Inter-Bold text at physical (x, y_top); return ADVANCE width in
    physical px (call sites do `x += hires(...) + gap`)."""
    font = resolve_font(_FONT, size)
    return draw_text(shim, font, text, x, y_top + font.ascent, color) - x


def text_width(size: int, text: str) -> int:
    """Physical advance width of `text` at `size` — core's measurement."""
    return hires_text_width(text, size, font=_FONT)


def fit_size(text: str, sizes: tuple[int, ...], max_w: int) -> int:
    """Largest ladder size at which `text` fits `max_w` (the floor when
    nothing fits) — core's `fit_text_size` with this pack's font."""
    return fit_text_size(text, sizes, max_w, font=_FONT)


def fit_text(text: str, max_w: int, size: int) -> str:
    """Ellipsize `text` to fit `max_w` at `size` (one char at a time; the
    strings here are short names/labels). Never raises on empty input."""
    if text_width(size, text) <= max_w:
        return text
    s = text
    while len(s) > 1 and text_width(size, s.rstrip() + "…") > max_w:
        s = s[:-1]
    return s.rstrip() + "…"


def px(real, x: int, y: int, color: Color) -> None:
    if 0 <= x < real.width and 0 <= y < real.height:
        real.SetPixel(x, y, color.red, color.green, color.blue)


def pip(real, cx: int, cy: int, r: int, color: Color) -> None:
    """Filled disc — the serving indicator."""
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if round((dx * dx + dy * dy) ** 0.5) <= r:
                px(real, cx + dx, cy + dy, color)


def rect(real, x0: int, y0: int, x1: int, y1: int, color: Color) -> None:
    """Filled rectangle, INCLUSIVE bounds, clipped to the canvas."""
    for y in range(max(0, y0), min(real.height - 1, y1) + 1):
        for x in range(max(0, x0), min(real.width - 1, x1) + 1):
            real.SetPixel(x, y, color.red, color.green, color.blue)


def triangle(real, x: int, cy: int, h: int, color: Color, *, point_left: bool) -> int:
    """Solid isoceles possession marker, `h` rows tall (odd works best),
    `h // 2 + 1` px wide, tip at column `x` when `point_left` (base to the
    right) or base at `x` with the tip to the right. Returns its width."""
    w = h // 2 + 1
    half = h // 2
    for i in range(w):
        rows = half - (w - 1 - i) if point_left else half - i
        col = x + i
        for dy in range(-rows, rows + 1):
            px(real, col, cy + dy, color)
    return w


def pips(
    real,
    x: int,
    y: int,
    remaining: int | None,
    *,
    size: int,
    gap: int,
    lit: Color,
    spent: Color,
) -> int:
    """Three `size`x`size` timeout pips left to right at (x, y) top-left: the
    first `remaining` in `lit`, the rest in `spent`. Nothing when `remaining`
    is None. Returns the run's total width (0 when nothing drawn)."""
    if remaining is None:
        return 0
    n = max(0, min(3, remaining))
    for i in range(3):
        x0 = x + i * (size + gap)
        rect(real, x0, y, x0 + size - 1, y + size - 1, lit if i < n else spent)
    return 3 * size + 2 * gap
