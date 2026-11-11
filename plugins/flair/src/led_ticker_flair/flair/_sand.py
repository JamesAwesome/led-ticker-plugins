"""Grain math for flair.sand — pure functions, no canvas.

Design in one breath:
- **Crumble.** Every lit snapshot pixel becomes one grain with a random
  release time in ``[0, RELEASE_MAX)`` of the crumble phase. After release
  it falls under a gravity sized so the last-released top-row grain has
  left the panel by ``CRUMBLE_CLEAR`` (before the last sampled frame),
  drifting sideways by at most ``DRIFT_FRAC`` of the panel width.
- **Pour.** Every lit pixel of the incoming snapshot becomes one grain
  dropped at rest from ``H0`` pixels above the top edge, straight down its
  own column, stopping dead on its target row. Lower rows start earlier,
  ranked within the content's own rows (``(y_hi-y)/span · POUR_ROW_SPAN``),
  plus up to ``POUR_JITTER`` of jitter.
  Start times are clamped so every grain lands by ``POUR_LAND_BY``, before
  the last sampled pour frame.

Spec: docs/superpowers/specs/2026-11-10-flair-sand-transition-design.md
"""

import math
import random

from ._raster import Raster, is_lit

RELEASE_MAX = 0.35
POUR_ROW_SPAN = 0.55
POUR_JITTER = 0.25
POUR_FALL_MAX = 0.45
DRIFT_FRAC = 0.02
# Crumble progress by which every grain must be off the panel. The runner
# never samples p = 1: at min_frames = 30 the last crumble frame is p ~ 0.93
# (linear) or ~0.87 (ease_in_out).
CRUMBLE_CLEAR = 0.85
# Pour progress by which every grain must have landed. The last sampled pour
# frame is q ~ 0.963 (30 frames, linear) and can be ~0.944 elsewhere.
POUR_LAND_BY = 0.92

# (x0, y0, r, g, b, release, vx)
CrumbleGrain = tuple[int, int, int, int, int, float, float]
# (x, y, r, g, b, start, dist)
PourGrain = tuple[int, int, int, int, int, float, int]


def crumble_gravity(h: int) -> float:
    return 2.1 * h / (CRUMBLE_CLEAR - RELEASE_MAX) ** 2


def drop_height(h: int) -> int:
    return max(1, round(h / 16))


def pour_gravity(h: int) -> float:
    return 2 * (h + drop_height(h)) / POUR_FALL_MAX**2


def _lit_pixels(raster: Raster):
    get = raster.get
    for y in range(raster.height):
        for x in range(raster.width):
            px = get(x, y)
            if is_lit(px):
                yield x, y, px


def crumble_grains(raster: Raster, rng: random.Random) -> list[CrumbleGrain]:
    vmax = DRIFT_FRAC * raster.width / (1 - RELEASE_MAX)
    uni = rng.random
    out: list[CrumbleGrain] = []
    for x, y, (r, g, b) in _lit_pixels(raster):  # type: ignore[misc]
        release = uni() * RELEASE_MAX
        vx = (uni() * 2 - 1) * vmax
        out.append((x, y, r, g, b, release, vx))
    return out


def pour_grains(raster: Raster, rng: random.Random) -> list[PourGrain]:
    h = raster.height
    h0 = drop_height(h)
    gp = pour_gravity(h)
    uni = rng.random
    lit = list(_lit_pixels(raster))
    if not lit:
        return []
    # Rows are ranked within the CONTENT, not the panel, so letterboxed or
    # short content starts landing at once instead of waiting on empty rows.
    y_lo = lit[0][1]
    y_hi = lit[-1][1]
    span = y_hi - y_lo + 1
    out: list[PourGrain] = []
    for x, y, (r, g, b) in lit:  # type: ignore[misc]
        dist = y + h0
        fall = math.sqrt(2 * dist / gp)
        start = (y_hi - y) / span * POUR_ROW_SPAN + uni() * POUR_JITTER
        start = max(0.0, min(start, POUR_LAND_BY - fall - 1e-6))
        out.append((x, y, r, g, b, start, dist))
    return out


def crumble_pos(
    grain: CrumbleGrain, p: float, w: int, h: int
) -> tuple[int, int] | None:
    x0, y0, _r, _g, _b, release, vx = grain
    dt = p - release
    if dt <= 0:
        return x0, y0
    x = round(x0 + vx * dt)
    y = round(y0 + 0.5 * crumble_gravity(h) * dt * dt)
    if 0 <= x < w and 0 <= y < h:
        return x, y
    return None


def pour_pos(grain: PourGrain, q: float, h: int) -> int | None:
    _x, y, _r, _g, _b, start, dist = grain
    dt = q - start
    if dt < 0:
        return None
    yy = min(float(y), (y - dist) + 0.5 * pour_gravity(h) * dt * dt)
    yi = round(yy)
    return yi if yi >= 0 else None
