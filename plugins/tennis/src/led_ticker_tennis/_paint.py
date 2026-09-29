"""Physical-pixel hi-res paint helpers for the scale>1 renderers — the
baseball/stocks/flight `_paint` pattern: wrap the REAL canvas at scale=1
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

# Inter-Bold needs the normal threshold to separate small adjacent glyphs.
_HIRES_THRESHOLD = 128
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


def phys_wrap(canvas):
    real = unwrap_to_real(canvas)
    return ScaledCanvas(real, scale=1, content_height=real.height), real


def hires(shim, text: str, x: int, y_top: int, color: Color, size: int) -> int:
    """Paint Inter-Bold text at physical (x, y_top); return ADVANCE width in
    physical px (call sites do `x += hires(...) + gap`)."""
    font = resolve_font(_FONT, size, _HIRES_THRESHOLD)
    return draw_text(shim, font, text, x, y_top + font.ascent, color) - x


def text_width(size: int, text: str) -> int:
    """Physical advance width of `text` at `size` — core's measurement."""
    return hires_text_width(text, size, font=_FONT, threshold=_HIRES_THRESHOLD)


def fit_size(text: str, sizes: tuple[int, ...], max_w: int) -> int:
    """Largest ladder size at which `text` fits `max_w` (the floor when
    nothing fits) — core's `fit_text_size` with this pack's font."""
    return fit_text_size(text, sizes, max_w, font=_FONT, threshold=_HIRES_THRESHOLD)


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
