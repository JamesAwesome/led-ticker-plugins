"""Physical-pixel hi-res paint helpers (ported from baseball `_paint.py` /
flight `paint.py` — the proven scale-1 ScaledCanvas shim pattern).

`phys_wrap` wraps the REAL canvas at scale=1 so `draw_text` places hi-res
glyphs at exact physical coordinates (logical == physical). All handoff
geometry was authored against JS Math.round — use `js_round`, never round().

Every handoff hires-text `y` is a VISUAL CAP-TOP y (the design engine crops
its text masks to visible ink — see design/led-engine-bundle.js
`rasterize()`); convert through `cap_top` before calling `hires()`.
"""

import math

from led_ticker.plugin import (
    Color,
    ScaledCanvas,
    draw_text,
    make_color,
    measure_width,
    resolve_font,
    unwrap_to_real,
)

from led_ticker_weather.palette import LABEL, RGB

# Thin Inter strokes drop out at the default 128 threshold on small sizes;
# 80 is the documented thin-font value (core CLAUDE.md `font_threshold`).
_HIRES_THRESHOLD = 80


def js_round(v: float) -> int:
    """JS Math.round semantics: half-up (floor(v + 0.5))."""
    return math.floor(v + 0.5)


def cap_top(y_target: int, size: int) -> int:
    """dc.html visual-cap-top y -> `hires()`'s ascent-box-top y (the
    baseball `_paint.cap_top` formula, hardware-validated there)."""
    return y_target - size + js_round(size * 0.72)


def phys_wrap(canvas):
    real = unwrap_to_real(canvas)
    return ScaledCanvas(real, scale=1, content_height=real.height), real


def dim(rgb: RGB, bright: float = 1.0) -> Color:
    r, g, b = rgb
    return make_color(int(r * bright), int(g * bright), int(b * bright))


def px(real, x: int, y: int, rgb: RGB, bright: float = 1.0) -> None:
    if 0 <= x < real.width and 0 <= y < real.height:
        r, g, b = rgb
        real.SetPixel(x, y, int(r * bright), int(g * bright), int(b * bright))


def hires(
    shim, text: str, x: int, y_top: int, rgb: RGB, size: int, *, bold: bool = True
) -> int:
    """Paint Inter text at physical (x, y_top); return ADVANCE width in
    physical px (call sites do `x += hires(...) + gap`, so returning
    draw_text's absolute end-x would double-count)."""
    font = resolve_font(
        "Inter-Bold" if bold else "Inter-Regular", size, _HIRES_THRESHOLD
    )
    return draw_text(shim, font, text, x, y_top + font.ascent, dim(rgb)) - x


class _ScaleOneProbe:
    """`measure_width(canvas=None)` falls back to SCALE_FALLBACK=4; this
    probe pins the measurement to scale 1 (physical px) instead."""

    scale = 1


_PROBE = _ScaleOneProbe()


def text_width(size: int, text: str, *, bold: bool = True) -> int:
    font = resolve_font(
        "Inter-Bold" if bold else "Inter-Regular", size, _HIRES_THRESHOLD
    )
    return measure_width(font, text, _PROBE)


def fit_text(text: str, max_w: int, size: int, *, bold: bool = True) -> str:
    """Handoff `fitText`: ellipsis-truncate until the text fits `max_w`."""
    if text_width(size, text, bold=bold) <= max_w:
        return text
    s = text
    while len(s) > 1 and text_width(size, s.rstrip() + "…", bold=bold) > max_w:
        s = s[:-1]
    return s.rstrip() + "…"


def vdivider(real, x: int, y0: int, y1: int) -> None:
    """Dotted vertical rule (handoff `vdivider`: LABEL at 0.4, every 3rd row)."""
    for y in range(y0, y1, 3):
        px(real, x, y, LABEL, 0.4)
