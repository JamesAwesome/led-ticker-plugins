"""Physical-pixel hi-res paint helpers (ported from stocks `_paint.py` /
flight `paint.py` — the proven scale-1 ScaledCanvas shim pattern).

`phys_wrap` wraps the REAL canvas at scale=1 so `draw_text` places hi-res
glyphs at exact physical coordinates (logical == physical). All handoff
geometry was authored against JS Math.round — use `js_round`, never round().
"""

import math
import re

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


# Codepoint ranges pragmatically treated as "not safely hi-res
# measurable" — the astral emoji/pictograph blocks plus the BMP
# symbol/dingbat/misc-symbols-and-arrows span, mirroring (not reusing —
# core exposes no public string sanitizer, see phase3-final-review.md F1)
# the block list `led_ticker.pixel_emoji` itself treats as emoji-shaped.
# VS-16 (emoji presentation) and ZWJ are included so a stripped sequence
# doesn't leave an orphaned selector/joiner behind.
_HIRES_UNSAFE_RE = re.compile(
    "["
    "\U0001f000-\U0001faff"  # emoji & pictograph blocks (flags, emoticons,
    # transport, misc symbols/pictographs, supplemental symbols/pictographs,
    # symbols & pictographs extended-A)
    "\U00002600-\U000027bf"  # misc symbols + dingbats (☀ ❤ ✨ ✉ …)
    "\U00002b00-\U00002bff"  # misc symbols and arrows (⭐ etc.)
    "\U0000fe0f"  # variation selector-16
    "\U0000200d"  # zero-width joiner
    "]+"
)


def _hires_safe(text: str) -> str:
    """Strip emoji/pictograph codepoints from free-form promo text before
    hi-res measure/paint (final-review finding F1).

    `hires()` (core `draw_text`/`draw_with_emoji`) renders a Unicode emoji
    MAPPED to a sprite slug as a hi-res sprite because its shim IS a real
    `ScaledCanvas` — but `text_width()` (core `measure_width`) measures the
    SAME string through `_PROBE`, which is deliberately NOT a `ScaledCanvas`
    (see its own docstring), so `measure_width` can't take the hi-res
    branch and instead counts the mapped emoji at its low-res-sprite width.
    The two disagree on width for the exact same string — a caller that
    measures with `text_width`/`fit_text` and separately paints with
    `hires`/`_mask.mask_scroll` (this package's whole layout shape) needs
    the two calls to agree, so free-form promo text (name/offer_type/
    presented_by) is sanitized through this ONE function before EITHER call
    — never inside `PromoInfo` itself, which would perturb the legacy
    scale-1 path's byte-identity contract (that path's own emoji handling
    is already width-correct; only this package's hi-res measure/paint
    split needs the belt).

    Pragmatic, not exhaustive: strips emoji/pictograph/dingbat/misc-symbol
    codepoint ranges plus VS-16/ZWJ, then collapses the run(s) of spaces
    left behind (e.g. "NIGHT ⭐" -> "NIGHT") and trims the ends. Accented
    Latin and other charset-covered glyphs are untouched — those already
    measure/paint in agreement.
    """
    stripped = _HIRES_UNSAFE_RE.sub("", text)
    return re.sub(r" {2,}", " ", stripped).strip()


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


def fit_text(text: str, max_w: int, size: int, *, bold: bool = True) -> str:
    """Port of dc.html `fitText` (~514-518): ellipsize `text` down to fit
    `max_w` physical px at `size`/`bold`, else return it unchanged.

    Truncates one character at a time (not a binary search — matches the
    prototype exactly, and every caller's strings are short promo/sub-line
    text) and appends U+2026 HORIZONTAL ELLIPSIS, which IS present in Inter
    (verified: `getbbox` returns a non-degenerate box, no tofu). Never
    raises: an empty `text` or a non-positive `max_w` both degrade to a
    short/empty result rather than an index error or infinite loop (the
    `len(s) > 1` guard is the same floor the prototype's `while` uses).
    """
    if text_width(size, text, bold=bold) <= max_w:
        return text
    s = text
    while len(s) > 1 and text_width(size, s.rstrip() + "…", bold=bold) > max_w:
        s = s[:-1]
    return s.rstrip() + "…"


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
