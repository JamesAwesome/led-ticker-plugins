"""Physical-pixel paint helpers shared by all three layouts.

The scale-1 ScaledCanvas shim from phys_wrap() is the trick that lets
draw_text place hi-res glyphs at exact PHYSICAL coordinates (the hires
renderer multiplies logical coords by the wrapper's scale — 1 — and adds
its y-offset — 0 — so logical == physical through the shim).
"""

import math

from led_ticker.plugin import (
    FONT_SMALL,
    ScaledCanvas,
    compute_baseline,
    draw_text,
    make_color,
    measure_width,
    resolve_font,
    unwrap_to_real,
)

from led_ticker_flight.glyphs import draw_glyph
from led_ticker_flight.palette import IDENT, IDLE, LABEL, RGB

LEVEL_BAR_W = 7
LEVEL_BAR_H = 3

# Fade-through-black between rotating flights on hero/dashboard (hardware
# review: a hard cut between flights read as a glitch on the physical panel).
# See hero_layout.render_hero / dashboard_layout.render_dashboard for the
# brightness formula this feeds.
FADE_MS = 200.0


def phys_wrap(canvas):
    real = unwrap_to_real(canvas)
    return ScaledCanvas(real, scale=1, content_height=real.height), real


def dim(rgb: RGB, bright: float = 1.0):
    r, g, b = rgb
    return make_color(int(r * bright), int(g * bright), int(b * bright))


def px(real, x: int, y: int, rgb: RGB, bright: float = 1.0) -> None:
    if 0 <= x < real.width and 0 <= y < real.height:
        r, g, b = rgb
        real.SetPixel(x, y, int(r * bright), int(g * bright), int(b * bright))


def hires(
    shim,
    text: str,
    x: int,
    y_top: int,
    rgb: RGB,
    size: int,
    bold: bool = True,
    bright: float = 1.0,
) -> int:
    """Draw hi-res text at physical (x, y_top) and return the ADVANCE width in
    physical px (NOT the absolute end-x) — every call site does
    `x += hires(...) + gap` / `nx += hires(...) + N`, so returning core's raw
    `draw_text` end-x would double-count the running x (CRITICAL finding: see
    task-10-adversarial.md)."""
    font = resolve_font("Inter-Bold" if bold else "Inter-Regular", size)
    return draw_text(shim, font, text, x, y_top + font.ascent, dim(rgb, bright)) - x


def paging_dots(
    real, scale: int, n: int, cur: int, x: int, y: int, bright: float = 1.0
) -> None:
    def sink(gx, gy, rgb, b):
        px(real, gx, gy, rgb, b)

    step = 2 * scale
    for i in range(n):
        color = IDENT if i == cur else LABEL
        draw_glyph(sink, "dot", x + i * step, y, color, bright=bright, expand=scale)


def level_bar(real, x: int, y_top: int, rgb: RGB, bright: float = 1.0) -> int:
    """Procedural stand-in for the level (▬) glyph — not in the hires charset."""
    for yy in range(LEVEL_BAR_H):
        for xx in range(LEVEL_BAR_W):
            px(real, x + xx, y_top + yy, rgb, bright)
    return LEVEL_BAR_W


def draw_empty(canvas, clock_ms: float, wide: bool, *, y_offset: int = 0) -> None:
    real = unwrap_to_real(canvas)
    sx = int(((clock_ms % 3200) / 3200) * real.width)
    half = real.height / 2
    for y in range(real.height):
        d = abs(y - half) / half
        px(real, sx, y, IDLE, 0.10 * (1 - d))
    pulse = 0.55 + 0.45 * math.sin(clock_ms / 600)
    label = "NO TRAFFIC OVERHEAD" if wide else "NO TRAFFIC"
    w = measure_width(FONT_SMALL, label, canvas)
    # Design-bundle divergence (deliberate): the prototype picks the long
    # label purely by PHYSICAL width (>= 200), but the text is drawn in
    # LOGICAL cells — on the bigsign (256 phys / 64 logical) the 19-char
    # label measures ~95 logical px and clips off both edges (a latent bug
    # in the prototype's own drawEmpty). Fit-fallback to the short form
    # when the chosen label cannot fit the logical canvas; longboi's 128
    # logical cells still take the long label.
    if w > canvas.width:
        label = "NO TRAFFIC"
        w = measure_width(FONT_SMALL, label, canvas)
    bx = max(0, (canvas.width - w) // 2)
    baseline = compute_baseline(FONT_SMALL, canvas) + y_offset
    draw_text(canvas, FONT_SMALL, label, bx, baseline, dim(IDLE, pulse))
