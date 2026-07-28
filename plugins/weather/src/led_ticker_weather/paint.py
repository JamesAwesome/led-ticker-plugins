"""Physical-pixel hi-res paint helpers (ported from baseball `_paint.py` /
flight `paint.py` — the proven scale-1 ScaledCanvas shim pattern).

`phys_wrap` wraps the REAL canvas at scale=1 so `draw_text` places hi-res
glyphs at exact physical coordinates (logical == physical). All handoff
geometry was authored against JS Math.round — use `js_round`, never round().

Every handoff hires-text `y` is a VISUAL CAP-TOP y (the design engine crops
its text masks to visible ink — see design/led-engine-bundle.js
`rasterize()`); convert through `cap_top` before calling `hires()`.
"""

import functools
import math

from led_ticker.plugin import (
    Color,
    HeadlessBackend,
    ScaledCanvas,
    draw_emoji_at,
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


def center_group_x(x0: float, x1: float, n: int, pitch: float) -> list[int]:
    """Left-edge x of each of `n` cells of width `pitch`, the whole block
    centered within [x0, x1). n == full-slot count fills from x0; fewer
    cells center with equal margins (the forecast short-feed fill rule)."""
    start = x0 + ((x1 - x0) - n * pitch) / 2
    return [js_round(start + i * pitch) for i in range(n)]


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


# Spleen pixel font: crisp at native 12px, monospace 6px advance. Measured:
# Digits, uppercase, %, and ° (the forecast's content) rasterize with
# ink-top at the passed y_top — no cap_top conversion. / and lowercase sit
# ±1px per the font's native per-glyph bbox; the forecast draws neither at
# a clipping y. Small forecast text (day labels, hi/lo, FEELS, precip) uses this.
_SPLEEN = resolve_font("spleen-6x12", 12, _HIRES_THRESHOLD)
_SPLEEN_ADVANCE = 6


def spleen_width(text: str) -> int:
    return _SPLEEN_ADVANCE * len(text)


def spleen(shim, text: str, x: int, y_top: int, rgb: RGB) -> int:
    """Paint spleen text; digits/uppercase/percent/degree ink-top sits AT y_top.
    Returns 6*len advance."""
    draw_text(shim, _SPLEEN, text, x, y_top + _SPLEEN.ascent - 1, dim(rgb))
    return spleen_width(text)


def spleen_center(shim, text: str, cx: float, y_top: int, rgb: RGB) -> None:
    spleen(shim, text, js_round(cx - spleen_width(text) / 2), y_top, rgb)


def spleen_segs(shim, segs: list[tuple[str, tuple]], cx: float, y_top: int) -> None:
    """Center multi-color segments as one monospace run."""
    total = sum(spleen_width(t) for t, _ in segs)
    x = js_round(cx - total / 2)
    for t, rgb in segs:
        x += spleen(shim, t, x, y_top, rgb)


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


# 8x8 lowres sprite box (curated weather emoji are all 8x8).
_SPRITE_BOX = 8


@functools.lru_cache(maxsize=32)
def _emoji_pixels(slug: str) -> tuple[tuple[int, int, int, int, int], ...]:
    """Lit (dx, dy, r, g, b) offsets of a curated lowres sprite.

    Offscreen-rasterize the 8x8 through the PUBLIC surface (`draw_emoji_at`
    on a throwaway `HeadlessBackend` canvas) and read back via `get_pixel`
    — the one documented supported readback (baseball `_mask.py`
    precedent). Cached: the scan runs once per slug per process.
    """
    real = HeadlessBackend(_SPRITE_BOX * 2, _SPRITE_BOX).create_canvas()
    draw_emoji_at(real, slug, 0, 0)
    out = []
    for dy in range(_SPRITE_BOX):
        for dx in range(_SPRITE_BOX):
            r, g, b = real.get_pixel(dx, dy)
            if (r, g, b) != (0, 0, 0):
                out.append((dx, dy, r, g, b))
    return tuple(out)


def blit_emoji_scaled(real, slug: str, x: int, y: int, k: int) -> None:
    """Stamp the curated lowres sprite at physical (x, y), each sprite
    pixel expanded to a k x k block (the strip-icon sizes: k=2 bigsign,
    k=3 longboi). Bounds-clipped per pixel."""
    for dx, dy, r, g, b in _emoji_pixels(slug):
        bx, by = x + dx * k, y + dy * k
        for j in range(k):
            for i in range(k):
                xx, yy = bx + i, by + j
                if 0 <= xx < real.width and 0 <= yy < real.height:
                    real.SetPixel(xx, yy, r, g, b)


@functools.lru_cache(maxsize=32)
def _hires_pixels(slug: str) -> tuple[tuple[int, int, int, int, int], ...]:
    """Lit (dx, dy, r, g, b) offsets of a 32x32 HIRES sprite.

    Rasterize the hires variant through the public surface: `draw_emoji_at`
    fires hires on a `ScaledCanvas` (any scale), so wrap a throwaway 32x32
    `HeadlessBackend` at scale=1 and read back the 32x32 physical grid via
    `get_pixel` (the one documented supported readback — baseball `_mask.py`
    precedent). Cached: runs once per slug per process.
    """
    real = HeadlessBackend(32, 32).create_canvas()
    sc = ScaledCanvas(real, scale=1, content_height=32)
    draw_emoji_at(sc, slug, 0, 0)
    out = []
    for dy in range(32):
        for dx in range(32):
            r, g, b = real.get_pixel(dx, dy)
            if (r, g, b) != (0, 0, 0):
                out.append((dx, dy, r, g, b))
    return tuple(out)


def blit_hires_downscaled(real, slug: str, x: int, y: int, target: int) -> None:
    """Stamp the 32x32 hires sprite at physical (x, y), box-area-downscaled
    to `target` x `target` (strip icon sizes: 16 bigsign, 24 longboi).

    Each target pixel is the mean of the 32-space source pixels it covers;
    a fully-black target pixel is skipped (transparent). Per-pixel
    bounds-clipped, like `blit_emoji_scaled`.
    """
    S = 32
    # Accumulate source lit pixels into target buckets (sum + count of the
    # FULL footprint incl. black, so edges anti-alias down rather than
    # staying full-bright).
    sums: dict[tuple[int, int], list[int]] = {}
    lit = {(dx, dy): (r, g, b) for dx, dy, r, g, b in _hires_pixels(slug)}
    for sy in range(S):
        ty = sy * target // S
        for sx in range(S):
            tx = sx * target // S
            r, g, b = lit.get((sx, sy), (0, 0, 0))
            acc = sums.setdefault((tx, ty), [0, 0, 0, 0])
            acc[0] += r
            acc[1] += g
            acc[2] += b
            acc[3] += 1
    for (tx, ty), (rs, gs, bs, n) in sums.items():
        r, g, b = rs // n, gs // n, bs // n
        if (r, g, b) == (0, 0, 0):
            continue
        px_, py_ = x + tx, y + ty
        if 0 <= px_ < real.width and 0 <= py_ < real.height:
            real.SetPixel(px_, py_, r, g, b)
