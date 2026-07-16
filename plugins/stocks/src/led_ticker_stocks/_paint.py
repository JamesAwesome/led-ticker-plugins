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
    hires_text_width,
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


# Inter (the hi-res font used by the card/dashboard layouts) has no glyph for
# U+2212 MINUS SIGN — `model.format_change`/`format_pct` emit U+2212 because
# it's the correct glyph for the BDF crawl font (which DOES have it), but
# Inter's fallback for an unmapped codepoint renders pixel-for-pixel identical
# to "?" (tofu). Substitute the ASCII hyphen-minus here, in the hi-res paint
# path only, so the crawl (BDF, draw_text directly, unaffected) keeps U+2212
# and the hi-res layouts get a real minus glyph instead of a "?" box.
# U+2014 EM DASH (the no-data placeholder, `model._DASH`) IS present in Inter
# and renders as its own distinct glyph — verified pixel-for-pixel different
# from both U+2212-as-tofu and "?"; no substitution needed for it.
_HIRES_GLYPH_SUBSTITUTIONS = {
    "−": "-",  # MINUS SIGN -> HYPHEN-MINUS
}


def _subst(text: str) -> str:
    """Apply `_HIRES_GLYPH_SUBSTITUTIONS` to `text`.

    Shared by `hires()` (which draws the substituted text) and
    `right_align_x()` (which measures it) so the two always agree on what
    string is actually being rendered — otherwise `right_align_x` measures
    the UN-substituted glyph width (e.g. U+2212's tofu-box advance, which
    differs from the real hyphen-minus glyph it's about to draw) and
    right-aligned negatives drift a couple px off the margin.
    """
    for missing, safe in _HIRES_GLYPH_SUBSTITUTIONS.items():
        text = text.replace(missing, safe)
    return text


# Inter's default rasterization threshold (128 = 50% coverage) drops thin
# glyph strokes at small pixel sizes — the "1" digit loses its stem and "0"s
# break up on the change line / watch column / PREV. A lower threshold keeps
# sub-50%-coverage edge pixels so small glyphs render whole. 80 is the
# documented value for thin fonts (core CLAUDE.md `font_threshold`).
_HIRES_THRESHOLD = 80


def hires(
    shim, text: str, x: int, y_top: int, color: Color, size: int, *, bold: bool = True
) -> int:
    """Paint Inter `text` at physical (x, y_top); return the ADVANCE width in
    physical px (NOT end-x — call sites do `x += hires(...) + gap`)."""
    text = _subst(text)
    font = resolve_font(
        "Inter-Bold" if bold else "Inter-Regular", size, _HIRES_THRESHOLD
    )
    return draw_text(shim, font, text, x, y_top + font.ascent, color) - x


def right_align_x(
    size: int, text: str, real_width: int, margin: int, *, bold: bool = True
) -> int:
    font = resolve_font(
        "Inter-Bold" if bold else "Inter-Regular", size, _HIRES_THRESHOLD
    )
    return real_width - measure_width(font, _subst(text), _PROBE) - margin


def text_width(size: int, text: str, *, bold: bool = True) -> int:
    """Physical advance width of `text` at `size` — the same measurement
    `hires()` will draw and `right_align_x()` aligns with (glyph substitutions
    included), so collision math never drifts from the paint.

    Delegates to core's `hires_text_width` (led-ticker-core>=4.16), which
    measures with the SAME glyph resolution `hires()` draws with — the
    plugin-local measurement this used to hand-roll via `resolve_font` +
    `measure_width` is now core's public surface (promoted from this exact
    pattern, stocks #54)."""
    return hires_text_width(
        _subst(text),
        size,
        font="Inter-Bold" if bold else "Inter-Regular",
        threshold=_HIRES_THRESHOLD,
    )


def px(real, x: int, y: int, color: Color) -> None:
    if 0 <= x < real.width and 0 <= y < real.height:
        real.SetPixel(x, y, color.red, color.green, color.blue)


def paging_dots(
    real,
    n: int,
    cur: int,
    x: int,
    y: int,
    *,
    scale: int,
    dim_color: Color,
    active_color: Color,
) -> None:
    """Draw n paging dots, each a scale×scale block spaced 2·scale apart —
    the same size/shape as the flight tracker's dots (flight paint.paging_dots).
    Current dot = active_color, the rest dim_color."""
    step = 2 * scale
    for i in range(n):
        c = active_color if i == cur else dim_color
        for dy in range(scale):
            for dx in range(scale):
                px(real, x + i * step + dx, y + dy, c)
