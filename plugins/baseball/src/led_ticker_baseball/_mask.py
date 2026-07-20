"""Masked text blits + clipped scroll — port of design `hiresMask`/`blit`/
`maskScroll` (`design/Baseball LED Widgets.dc.html` lines ~520-526).

The prototype builds an offscreen alpha mask for a string ONCE (cached), then
`blit`s it at an arbitrary x with a hard column clip `{x0,x1}` — the seam
that lets `promoLongScroll` scroll a too-wide promo name within a fixed band
without ever touching the info block to its right. We port the same shape:
rasterize Inter text onto an OFFSCREEN `HeadlessBackend` canvas through the
PUBLIC surface (`_paint.hires`, itself built on `led_ticker.plugin.draw_text`),
read the lit pixels back via `HeadlessCanvas.get_pixel` (the one documented
supported read — see `led_ticker/backends/headless.py`), and cache the result
as a `TextMask`. Because `text_mask` is `functools.lru_cache`'d, the
width*height `get_pixel` scan pays its cost once per distinct (text, size,
bold) — a promo-name-length string at px22 scans ~30k cells in ~2ms
(measured), well within budget for a value that's then reused every frame.

Origin convention (read this before touching the module): `TextMask.pixels`
stores `(dx, dy)` offsets already in CAP-TOP coordinate space — the SAME
space every dc.html-derived call site's `y` argument uses (i.e. what
`_paint.cap_top` treats as its `y_target`). Concretely: the mask is
rasterized internally with the ascent-box top pinned at row 0 (`hires()`'s
own `y_top=0`), then every row index is shifted by `-(size -
js_round(size * 0.72))` — the exact delta `_paint.cap_top` applies in the
other direction. The net effect: `blit_mask`/`mask_scroll` take a bare
cap-top `y` from the caller and add `TextMask` offsets directly — no
`cap_top()` call anywhere in this module. `text_mask` itself never sees a
`y`; the CAP_ADJUST shift is baked into the offsets it returns.
"""

import functools

import attrs
from led_ticker.plugin import Color, HeadlessBackend, make_color

from led_ticker_baseball._paint import hires, js_round, phys_wrap, px, text_width
from led_ticker_baseball._palette import dim

# Height of the offscreen mask-build canvas. 64 comfortably covers every
# size this package uses (crawl's largest is px30) with headroom for a
# descender-less font's ascent box to sit fully on-canvas from row 0.
_MASK_CANVAS_H = 64

# Safety margin (physical px) added past the measured advance width when
# sizing the offscreen mask canvas, in case a glyph's rendered extent
# slightly overshoots its own advance (e.g. italic-ish overhang in Inter
# Bold). Purely a canvas-sizing guard — `TextMask.w` itself is always the
# exact advance from `_paint.text_width`, never the padded canvas width.
_MASK_MARGIN = 4


@attrs.frozen
class TextMask:
    """Cached rasterization of one (text, size, bold) combo.

    `w` is the ADVANCE width in physical px (`_paint.text_width`'s return —
    what a caller sizes a scroll band or centers against). `pixels` is every
    lit offset `(dx, dy)` relative to the CAP-TOP origin (see module
    docstring) — `blit_mask` does nothing more than `real.SetPixel(x + dx,
    y + dy, ...)` for each, clipped to the caller's `[x0, x1)` window.
    """

    w: int
    pixels: tuple[tuple[int, int], ...]


@functools.lru_cache(maxsize=64)
def text_mask(text: str, size: int, *, bold: bool = True) -> TextMask:
    """Rasterize `text` at `size`/`bold` into a cached `TextMask`.

    Renders white (`255,255,255`) onto a throwaway offscreen
    `HeadlessBackend` canvas — color is applied later, at blit time, via
    `_palette.dim`. `functools.lru_cache` keys on the exact (text, size,
    bold) triple, so repeated calls (every frame, for a scrolling promo
    name) return the SAME `TextMask` object — no repeat rasterization or
    readback.
    """
    w = text_width(size, text, bold=bold)
    canvas_w = max(w + _MASK_MARGIN, 1)
    real = HeadlessBackend(canvas_w, _MASK_CANVAS_H).create_canvas()
    shim, unwrapped = phys_wrap(real)
    white = make_color(255, 255, 255)
    hires(shim, text, 0, 0, white, size, bold=bold)
    # Ascent-box top (row 0 of this render) -> CAP-TOP origin: the same
    # delta `_paint.cap_top(y_target, size)` subtracts from y_target to
    # reach the ascent-box top, applied here in reverse to pixel offsets
    # instead of to a y coordinate.
    cap_adjust = size - js_round(size * 0.72)
    pixels = tuple(
        (x, y - cap_adjust)
        for y in range(_MASK_CANVAS_H)
        for x in range(canvas_w)
        if unwrapped.get_pixel(x, y) != (0, 0, 0)
    )
    return TextMask(w=w, pixels=pixels)


def blit_mask(
    real,
    mask: TextMask,
    x: int,
    y: int,
    color: Color,
    *,
    x0: int,
    x1: int,
    brightness: float = 1.0,
) -> None:
    """Paint `mask` at physical `(x, y)` (y = CAP-TOP, see module docstring),
    hard-clipped to the physical column window `[x0, x1)`.

    Every lit `(dx, dy)` offset is checked against the window BEFORE
    `_paint.px` (which only bounds-checks the canvas edges, not this
    caller-supplied band) — the clip is what lets a scrolling promo name
    never bleed a pixel into an adjacent info block.
    """
    c = dim(color, brightness)
    for dx, dy in mask.pixels:
        px_x = x + dx
        if x0 <= px_x < x1:
            px(real, px_x, y + dy, c)


def mask_scroll(
    real,
    text: str,
    x0: int,
    x1: int,
    y: int,
    color: Color,
    size: int,
    clock_ms: float,
    *,
    bold: bool = True,
    speed: float = 38.0,
) -> None:
    """Port of `maskScroll` (dc.html ~520-526): draw `text` held at `x0` if
    it fits the `[x0, x1)` band, else scroll it leftward, wrapping smoothly.

    Fitting text (`mask.w <= x1 - x0`) is static — one blit at `x0`, every
    call with any `clock_ms` produces the identical frame. Overflowing text
    scrolls at `speed` physical px/sec: `period = mask.w + 44` (mask width
    plus a fixed 44px gap before the string repeats) and `off` is the
    px-distance traveled this clock, wrapped into `[0, period)`. Two blits
    (`x0 - off` and `x0 - off + period`) cover the seam so the repeat is
    seamless — at most one of the two is ever visible at once for a mask
    narrower than the band, but both are always issued (cheap: `blit_mask`
    is itself window-clipped, so the off-window one is a no-op scan).
    """
    mask = text_mask(text, size, bold=bold)
    region = x1 - x0
    if mask.w <= region:
        blit_mask(real, mask, x0, y, color, x0=x0, x1=x1)
        return
    period = mask.w + 44
    off = (clock_ms / 1000 * speed) % period
    blit_mask(real, mask, js_round(x0 - off), y, color, x0=x0, x1=x1)
    blit_mask(real, mask, js_round(x0 - off + period), y, color, x0=x0, x1=x1)
