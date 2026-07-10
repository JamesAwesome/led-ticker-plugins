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

import math
import types

from led_ticker.plugin import ENGINE_TICK_MS, get_text_width, resolve_font

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
    real_canvas = types.SimpleNamespace(scale=1)
    for size in range(int(diameter_px * _MAX_FONT_FACTOR), _MIN_FONT_SIZE - 1, -1):
        font = resolve_font(font_name, size)
        width = get_text_width(font, word, padding=0, canvas=real_canvas)
        if width <= threshold:
            return size
    return 0
