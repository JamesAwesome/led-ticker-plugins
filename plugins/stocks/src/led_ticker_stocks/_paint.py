"""Physical-pixel hi-res paint helpers for the held card/dashboard layouts.

The scale-1 ScaledCanvas shim lets `draw_text` place hi-res glyphs at exact
PHYSICAL coordinates (the hires renderer multiplies logical coords by the
wrapper's scale — 1 — and adds its y-offset — 0 — so logical == physical).
Modeled on plugins/flight/src/led_ticker_flight/paint.py.
"""

from led_ticker.plugin import (
    Color,
    ScaledCanvas,
    draw_text,
    measure_width,
    resolve_font,
    unwrap_to_real,
)


def phys_wrap(canvas):
    real = unwrap_to_real(canvas)
    return ScaledCanvas(real, scale=1, content_height=real.height), real


class _ScaleOneProbe:
    """Minimal canvas-like stand-in exposing `scale = 1`.

    `measure_width` → `get_text_width` treats a `canvas=None` argument as
    "no canvas yet exists" and falls back to `SCALE_FALLBACK = 4` (a
    bigsign-only assumption baked into core for pre-canvas callers — see
    CLAUDE.md's "Hi-res fonts" invariant). `right_align_x` runs against the
    physical (scale-1) shim, so passing this probe instead of `None` makes
    `safe_scale` read 1 and keeps the measured width in the same physical-px
    units `hires()` actually paints in — without a real canvas to hand it.
    """

    scale = 1


_PROBE = _ScaleOneProbe()


def hires(
    shim, text: str, x: int, y_top: int, color: Color, size: int, *, bold: bool = True
) -> int:
    """Paint Inter `text` at physical (x, y_top); return the ADVANCE width in
    physical px (NOT end-x — call sites do `x += hires(...) + gap`)."""
    font = resolve_font("Inter-Bold" if bold else "Inter-Regular", size)
    return draw_text(shim, font, text, x, y_top + font.ascent, color) - x


def right_align_x(
    size: int, text: str, real_width: int, margin: int, *, bold: bool = True
) -> int:
    font = resolve_font("Inter-Bold" if bold else "Inter-Regular", size)
    return real_width - measure_width(font, text, _PROBE) - margin


def px(real, x: int, y: int, color: Color) -> None:
    if 0 <= x < real.width and 0 <= y < real.height:
        real.SetPixel(x, y, color.red, color.green, color.blue)


def paging_dots(
    real, n: int, cur: int, x: int, y: int, *, dim_color: Color, active_color: Color
) -> None:
    for i in range(n):
        c = active_color if i == cur else dim_color
        px(real, x + i * 2, y, c)
