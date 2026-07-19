"""Physical-pixel hi-res paint helpers (ported from stocks `_paint.py` /
flight `paint.py` — the proven scale-1 ScaledCanvas shim pattern).

`phys_wrap` wraps the REAL canvas at scale=1 so `draw_text` places hi-res
glyphs at exact physical coordinates (logical == physical). All handoff
geometry was authored against JS Math.round — use `js_round`, never round().
"""

import math

from led_ticker.plugin import (
    Color,
    ScaledCanvas,
    draw_text,
    measure_width,
    resolve_font,
    unwrap_to_real,
)

from led_ticker_baseball._palette import IDENT, LABEL

# Thin Inter strokes drop out at the default 128 threshold on small sizes;
# 80 is the documented thin-font value (core CLAUDE.md `font_threshold`).
_HIRES_THRESHOLD = 80

# Inter has no U+2212 MINUS glyph (tofu). Substitute ASCII hyphen-minus in
# the hires path only (same belt as stocks `_paint._subst`).
_HIRES_GLYPH_SUBSTITUTIONS = {"−": "-"}


def js_round(v: float) -> int:
    """JS Math.round semantics: half-up (floor(v + 0.5))."""
    return math.floor(v + 0.5)


def cap_top(y_target: int, size: int) -> int:
    """dc.html visual-cap-top y -> `hires()`'s ascent-box-top y.

    Every dc.html handoff coordinate is the glyph's VISUAL top (roughly cap
    height) under the prototype's own rasterizer; `hires()` treats its `y`
    argument as the ASCENT-box top (baseline = y + font.ascent). Inter's
    ascent is taller than its cap height, so a naive 1:1 port renders text
    low. This is the ONE conversion formula (originally derived + hardware
    validated in `layouts/standings_board.py`, see that module's docstring
    for the full derivation) — every caller that receives a cap-top target
    from the design handoff routes through this before calling `hires()`
    directly. `layouts/crawl.py`'s `_y_for` is a deliberate exception (see
    its own docstring) and must NOT be migrated to this helper.
    """
    return y_target - size + js_round(size * 0.72)


def _subst(text: str) -> str:
    for missing, safe in _HIRES_GLYPH_SUBSTITUTIONS.items():
        text = text.replace(missing, safe)
    return text


class _ScaleOneProbe:
    """`measure_width(canvas=None)` falls back to SCALE_FALLBACK=4; this
    probe pins the measurement to scale 1 (physical px) instead."""

    scale = 1


_PROBE = _ScaleOneProbe()


def phys_wrap(canvas):
    real = unwrap_to_real(canvas)
    return ScaledCanvas(real, scale=1, content_height=real.height), real


def hires(
    shim, text: str, x: int, y_top: int, color: Color, size: int, *, bold: bool = True
) -> int:
    """Paint Inter text at physical (x, y_top); return ADVANCE width in
    physical px (call sites do `x += hires(...) + gap`)."""
    text = _subst(text)
    font = resolve_font(
        "Inter-Bold" if bold else "Inter-Regular", size, _HIRES_THRESHOLD
    )
    return draw_text(shim, font, text, x, y_top + font.ascent, color) - x


def text_width(size: int, text: str, *, bold: bool = True) -> int:
    font = resolve_font(
        "Inter-Bold" if bold else "Inter-Regular", size, _HIRES_THRESHOLD
    )
    return measure_width(font, _subst(text), _PROBE)


def px(real, x: int, y: int, color: Color) -> None:
    if 0 <= x < real.width and 0 <= y < real.height:
        real.SetPixel(x, y, color.red, color.green, color.blue)


def paging_dots(real, n: int, cur: int, x: int, y: int) -> None:
    """Handoff paging dots: 2x2 physical blocks, 8px pitch. The prototype
    uses 2*scale spacing with scale-sized dots (scale=4 -> dot=4px, step=8);
    a 4px dot reads heavy on our denser P3 panels, so the stocks/flight
    convention of a 2x2 dot on the same 8px pitch is kept here instead —
    the pitch (not the dot size) is what call sites reserve layout space
    against (`n*8+4` px), so step=8 is the load-bearing value."""
    step = 8
    for i in range(n):
        c = IDENT if i == cur else LABEL
        for dy in range(2):
            for dx in range(2):
                px(real, x + i * step + dx, y + dy, c)
