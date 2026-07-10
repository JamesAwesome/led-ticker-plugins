"""flair.lottery — lottery-ball roll animation: pure geometry + timeline.

N labeled balls roll in from off-canvas left in a staggered relay (one ball
after another, each on its own ``ticks_per_ball``-tick window) and settle
flat into evenly spaced slots across the panel. The eventual widget (a
later task) follows the same two-surface blit design as ``flair.propeller``
/ ``flair.fisheye``: each ball is painted once onto a real-canvas surface
and re-blitted every tick at the angle this module computes, until it
settles exactly flat at 0 degrees — this module supplies ONLY that pure
geometry/timeline math (layout, roll phase, font sizing); no painting, no
widget class, no core imports beyond the public ``led_ticker.plugin``
surface.
"""

import logging
import math
import types

from led_ticker.plugin import (
    ENGINE_TICK_MS,
    compute_baseline_for_band,
    draw_with_emoji,
    get_text_width,
    make_color,
    paint_hires,
    resolve_font,
)

logger = logging.getLogger("led_ticker_flair")

# The 8 spec auto-palette colors, in spec order (red, green, amber, blue,
# magenta, cyan, orange, violet) — assigned to balls in order when
# ``ball_style == "solid"`` (widget concern; this module just ships the
# constant tuple future tasks index into).
PALETTE: tuple[tuple[int, int, int], ...] = (
    (255, 60, 60),  # red
    (60, 220, 60),  # green
    (255, 180, 0),  # amber
    (80, 140, 255),  # blue
    (255, 80, 255),  # magenta
    (0, 220, 220),  # cyan
    (255, 120, 40),  # orange
    (170, 90, 255),  # violet
)

# Physical-pixel gap between adjacent ball slots (spec constant, verbatim).
_GAP_PX = 4

# Text chord factor: usable text width as a fraction of ball diameter.
_CHORD_FACTOR = 0.72

# Largest candidate font size is this fraction of the ball diameter.
_MAX_FONT_FACTOR = 0.45

# Floor below which glyphs are unreadable (also the HiresFont size floor
# enforced by ``resolve_font``).
_MIN_FONT_SIZE = 8

# Style constants (spec, verbatim) — classic face is white with a dark
# label; solid face is color-filled with a white label.
_CLASSIC_FACE_RGB = (255, 255, 255)
_CLASSIC_TEXT_RGB = (10, 10, 10)
_SOLID_TEXT_RGB = (255, 255, 255)

# `get_text_width`'s scale divisor only matters for its logical-width
# conversion; a scale=1 stub makes it return the raw real-pixel width
# (see `auto_font_size`'s docstring for why that's what we need here).
# Shared by `auto_font_size` and `paint_face` so both measure the same way.
_REAL_SCALE1_STUB = types.SimpleNamespace(scale=1)


def layout(n: int, panel_w: int, panel_h: int, inset: int) -> tuple[int, list[int]]:
    """Compute ball diameter + slot center-x positions for ``n`` balls.

    All units are REAL (physical) pixels — the balls paint directly to the
    real canvas (bypassing the ``ScaledCanvas`` scale wrapper, same as
    hi-res emoji), so their geometry must be computed in the same space
    the panel itself is measured in.

    ``diameter = min(panel_h - 2*inset, panel_w // n - GAP)`` — the ball
    must fit the inset vertical band AND its even share of the horizontal
    width (minus the inter-slot gap). Slots are evenly spaced with
    ``_GAP_PX`` between them and centered as a group within ``panel_w``.
    """
    diameter = min(panel_h - 2 * inset, panel_w // n - _GAP_PX)
    total_width = n * diameter + (n - 1) * _GAP_PX
    start_x = (panel_w - total_width) // 2
    stride = diameter + _GAP_PX
    slot_centers = [start_x + i * stride + diameter // 2 for i in range(n)]
    return diameter, slot_centers


def ticks_per_ball(roll_ms: int) -> int:
    """Engine ticks a single ball's roll-in takes, at least 1.

    ``ENGINE_TICK_MS`` (50ms, imported from the public core surface rather
    than hardcoded) is the held-text tick cadence every frame-aware widget
    animates on.
    """
    return max(1, roll_ms // ENGINE_TICK_MS)


def ball_phase(
    frame: int, index: int, ticks_per_ball: int, diameter: int, slot_cx: int
) -> tuple[float, float, bool]:
    """Roll-timeline state for ball ``index`` at engine tick ``frame``.

    Balls roll in a staggered relay: ball ``index`` owns the tick window
    ``[index * ticks_per_ball, (index + 1) * ticks_per_ball)``.

    - Before its window: parked off-canvas left at ``cx = -diameter``,
      angle ``0.0``, not settled.
    - During its window: eased travel (cubic ease-out,
      ``t_eased = 1 - (1 - t) ** 3``) from the launch position
      ``-diameter / 2`` to ``slot_cx``. The face angle is the remaining
      travel distance (in ball-radii) converted to degrees and negated —
      a leftward-entry roll spins the face so it continuously unwinds
      toward, and lands at EXACTLY, 0 degrees when ``cx`` reaches
      ``slot_cx`` (remaining == 0).
    - After its window: settled — ``(slot_cx, 0.0, True)``.

    Returns ``(cx_px, angle_deg, settled)``.
    """
    start = index * ticks_per_ball
    end = start + ticks_per_ball

    if frame < start:
        return -float(diameter), 0.0, False
    if frame >= end:
        return float(slot_cx), 0.0, True

    t = (frame - start) / ticks_per_ball
    t_eased = 1.0 - (1.0 - t) ** 3

    launch_cx = -diameter / 2
    cx = launch_cx + t_eased * (slot_cx - launch_cx)

    radius = diameter / 2
    remaining = slot_cx - cx
    angle = -math.degrees(remaining / radius) if radius else 0.0
    return cx, angle, False


def auto_font_size(word: str, diameter_px: int, font_name: str, scale: int) -> int:
    """Largest hi-res font size whose rendered ``word`` fits the ball face.

    Searches ``size`` from ``int(diameter_px * 0.45)`` down to
    ``_MIN_FONT_SIZE`` (8, the ``resolve_font`` legibility floor) and
    returns the first (largest) size whose rendered width fits
    ``diameter_px * _CHORD_FACTOR`` (0.72 — the usable text-width chord of
    a circle). Returns 0 if not even the floor size fits (caller treats
    that as "doesn't fit — fall back / truncate / error", widget concern).

    Unit note on ``get_text_width`` and the ``scale`` argument: for a
    HiresFont, ``get_text_width`` sums REAL-pixel glyph advances (font
    ``size`` is always a real-pixel target — see ``resolve_font``) and
    then divides by ``canvas.scale`` to convert to LOGICAL pixels for
    layout math elsewhere in core (``canvas=None`` falls back to
    ``SCALE_FALLBACK=4``). Here ``diameter_px`` is a REAL-pixel
    measurement (balls paint directly to the real canvas), so we need the
    RAW real-pixel width, not a scale-divided logical approximation —
    dividing by the widget's real scale before comparing to a REAL
    diameter would let the search accept oversized fonts (verified: at
    diameter=56/scale=4 the naive "forward the real scale" approach picks
    size=25, whose ACTUAL real-pixel width is 77px — comfortably wider
    than the 56px ball). We deliberately pass a ``canvas`` stub with
    ``scale=1`` (a no-op divisor) so ``get_text_width`` returns the true
    real-pixel width, matching the size=13 fit that visually fits the
    chord. ``scale`` is still accepted (part of the locked public
    interface a future widget task calls with its real canvas scale) and
    is validated defensively even though it doesn't feed the fit
    computation.
    """
    if not isinstance(scale, int) or isinstance(scale, bool) or scale < 1:
        raise ValueError(f"scale must be an int >= 1; got {scale!r}")

    threshold = diameter_px * _CHORD_FACTOR
    for size in range(int(diameter_px * _MAX_FONT_FACTOR), _MIN_FONT_SIZE - 1, -1):
        font = resolve_font(font_name, size)
        width = get_text_width(font, word, padding=0, canvas=_REAL_SCALE1_STUB)
        if width <= threshold:
            return size
    return 0


def paint_face(
    target,
    *,
    cx_logical: float,
    cy_logical: float,
    r_px: int,
    style: str,
    color: tuple[int, int, int],
    word: str,
    font_name: str,
    scale: int,
) -> None:
    """Paint one lottery-ball face onto ``target``.

    ``target`` is a rotation-surface's ``.target`` (a full-canvas
    ``ScaledCanvas``, per ``led_ticker.rotate.RotationSurface`` — draw
    into it in logical coordinates, then ``snapshot()`` + ``blit()`` it)
    or any other canvas-alike; ``paint_hires``/``draw_with_emoji`` work
    on either.

    MIXED UNITS, deliberately (the same split hi-res emoji/fonts already
    straddle): ``cx_logical``/``cy_logical`` are LOGICAL coordinates —
    the widget's own drawing space. ``r_px`` is the ball radius in REAL
    (physical) pixels — the circle paints directly to the real canvas
    via ``paint_hires`` (bypassing the ``ScaledCanvas`` block expansion,
    same as hi-res emoji/fonts), so its geometry must be in real-pixel
    units to render a crisp circle rather than a blocky
    ``scale``-sized-square approximation. ``scale`` is the canvas's
    real/logical ratio, needed to convert the real-pixel measurements
    (radius, text width) back to the logical coordinates ``target``
    draws in.

    Style ``"classic"``: white ``(255,255,255)`` face, a ``color``
    ring band ``max(1, r_px // 8)`` px wide at the rim, dark
    ``(10,10,10)`` text. Style ``"solid"``: ``color``-filled face,
    white ``(255,255,255)`` text. Any other ``style`` raises
    ``ValueError``.

    The word is centered on the face: horizontally by measuring its
    REAL-pixel width (the same scale=1 measurement ``auto_font_size``
    uses — see its docstring) and centering that on ``cx_logical``;
    vertically via ``compute_baseline_for_band``, treating the ball's
    real diameter (converted to a logical band height) as the text
    band — this accounts for the resolved font's actual ascent/descent
    rather than a hardcoded midpoint guess.

    If ``auto_font_size`` reports the word doesn't fit (returns 0 — the
    widget's config validation should already have caught this at
    preflight), the circle is still painted but the word is skipped;
    logs one WARNING via the ``"led_ticker_flair"`` logger as a
    belt-and-braces render-time guard.
    """
    if style not in ("classic", "solid"):
        raise ValueError(
            f"paint_face: style must be 'classic' or 'solid'; got {style!r}"
        )

    is_classic = style == "classic"
    ring_w = max(1, r_px // 8)
    face_rgb = _CLASSIC_FACE_RGB if is_classic else color
    text_rgb = _CLASSIC_TEXT_RGB if is_classic else _SOLID_TEXT_RGB

    def _paint_circle(real, real_scale, y_offset_real):
        cx_p = cx_logical * real_scale
        cy_p = cy_logical * real_scale + y_offset_real
        r2 = r_px * r_px
        ring_r2 = max(0, r_px - ring_w) ** 2

        x0 = max(0, math.floor(cx_p - r_px))
        x1 = min(real.width - 1, math.ceil(cx_p + r_px))
        y0 = max(0, math.floor(cy_p - r_px))
        y1 = min(real.height - 1, math.ceil(cy_p + r_px))

        for py in range(y0, y1 + 1):
            dy2 = (py - cy_p) ** 2
            for px in range(x0, x1 + 1):
                d2 = (px - cx_p) ** 2 + dy2
                if d2 > r2:
                    continue
                if is_classic and d2 >= ring_r2:
                    r, g, b = color
                else:
                    r, g, b = face_rgb
                real.SetPixel(px, py, r, g, b)

    paint_hires(target, _paint_circle)

    diameter_px = 2 * r_px
    size = auto_font_size(word, diameter_px, font_name, scale)
    if size == 0:
        logger.warning(
            "flair.lottery: word %r does not fit a %dpx ball face (font=%s) "
            "— painting the ball without a label",
            word,
            diameter_px,
            font_name,
        )
        return

    font = resolve_font(font_name, size)
    real_width = get_text_width(font, word, padding=0, canvas=_REAL_SCALE1_STUB)
    x_logical = round(cx_logical - real_width / (2 * scale))

    diameter_logical = round(diameter_px / scale)
    band_top_logical = cy_logical - diameter_logical / 2
    baseline_offset = compute_baseline_for_band(font, diameter_logical, scale, "center")
    baseline_logical = round(band_top_logical + baseline_offset)

    draw_with_emoji(
        target, font, x_logical, baseline_logical, make_color(*text_rgb), word
    )
