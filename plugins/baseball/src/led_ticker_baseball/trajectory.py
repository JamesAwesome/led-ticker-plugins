"""Batted-ball trajectory geometry for the statcast hero card (longboi).

Replaces the design prototype's `traj()` (dc.html ~257), whose single
symmetric parabola `4u(1-u)` scaled only by launch angle drew the SAME
shape for every ball. Here the curve is a deterministic function of the
ball's real numbers (launch angle, exit velo, distance, bb_type) PLUS a
result-driven landing `act` — so different balls draw genuinely different
arcs while a given ball is always identical (no RNG; testable; frame-
invariant shape). Pure geometry: no canvas, no palette, no frame state.
"""

import math
from dataclasses import dataclass

from led_ticker.plugin import Color

from led_ticker_baseball import _palette as pal
from led_ticker_baseball._paint import px

# Tunables (hardware-adjustable constants, one rationale each):
WARNING_TRACK_FT = 370.0  # an out carrying >= this is "caught at the track"
REF_FT = 470.0  # distance that reaches the wall (landing frac 1.0)
LINER_MAX_LA = 12.0  # <= this launch angle is a flat rope, not an arc
_APEX_BASE = 0.58  # apex fraction at LA 0 (drag: past midpoint)
_APEX_LA_SHIFT = 0.14  # higher LA apexes earlier by up to this
_EV_FLATTEN = 0.12  # high exit velo lowers the apex (line-drive carry)
_EV_REF = 115.0  # exit velo at which _EV_FLATTEN fully applies


def res_color(result: str) -> Color:
    """Map a batted-ball result string to a palette color.

    HR/grand slam -> WIN (green), out/GIDP/double play -> LOSS (red),
    else AMBER (orange).
    """
    r = (result or "").upper()
    if "HOME RUN" in r or "HR" in r or "GRAND" in r:
        return pal.WIN
    if "OUT" in r or "GIDP" in r or "DOUBLE PLAY" in r:
        return pal.LOSS
    return pal.AMBER


@dataclass(frozen=True)
class ArcPlan:
    points: list[tuple[int, int]]
    landing: tuple[int, int]
    act: str
    wall_x: int | None


def _classify(result: str, bb_type: str, distance: float, la: float) -> str:
    r = (result or "").upper()
    if "HOME RUN" in r:
        return "clears"
    is_out = "OUT" in r or "GIDP" in r or "DOUBLE PLAY" in r
    if bb_type == "ground_ball" or la <= 0:
        return "grounder"
    if is_out and distance >= WARNING_TRACK_FT:
        return "track"
    if is_out:
        return "caught"
    return "fair"  # a hit that isn't a HR


def plan_arc(launch_angle, exit_velo, distance, bb_type, result, w, h):
    la = float(launch_angle) if launch_angle is not None else 0.0
    ev = float(exit_velo) if exit_velo is not None else 0.0
    dist = float(distance) if distance is not None else 0.0
    act = _classify(result, bb_type, dist, la)

    ground = h - 1
    liner = 0 < la <= LINER_MAX_LA
    if act == "grounder":
        # low skip along the ground to a short landing
        end_x = max(6, int(round(w * 0.45)))
        pts = [(i, ground - (1 if (i // 3) % 2 == 0 else 0)) for i in range(end_x + 1)]
        return ArcPlan(pts, (end_x, ground), "grounder", None)

    # landing x from distance; HR reaches the wall, liner runs off the edge
    if act == "clears":
        wall_x = w - 4
        end_x = w  # continue a hair past the wall
    elif liner:
        wall_x = None
        end_x = w  # never comes down inside the box
    else:
        wall_x = None
        frac = max(0.30, min(0.98, dist / REF_FT)) if dist > 0 else 0.45
        end_x = int(round(w * frac))
    end_x = max(6, min(w, end_x))

    # apex height from LA, flattened by high EV; liner barely rises
    peak_frac = max(0.0, min(1.0, la / 45.0))
    peak = peak_frac * (h - 2)
    if ev > 0:
        peak *= 1.0 - _EV_FLATTEN * min(1.0, ev / _EV_REF)
    peak = max(2.0, min(float(h - 2), peak))
    if liner:
        peak = min(peak, 4.0)

    # apex position: higher LA apexes earlier; drag => steeper descent
    a = _APEX_BASE - _APEX_LA_SHIFT * peak_frac
    a = max(0.35, min(0.7, a))

    span = max(1, end_x)
    pts: list[tuple[int, int]] = []
    for i in range(end_x + 1):
        u = i / span
        if u <= a:
            f = math.sin((u / a) * (math.pi / 2))  # smooth rise to 1
        else:
            v = (u - a) / (1 - a)
            f = math.cos(v * (math.pi / 2)) ** 1.5  # steeper drag drop
        y = ground - int(round(peak * max(0.0, f)))
        pts.append((i, max(0, min(ground, y))))
    landing = pts[-1]
    return ArcPlan(pts, landing, act, wall_x)


def draw_trajectory(
    real, box: tuple[int, int, int, int], plan: ArcPlan, progress: float
) -> None:
    """Paint `plan`'s arc onto the REAL (physical-px) canvas within `box`.

    `box = (x, y, w, h)` is the panel origin+size in physical px. `progress`
    is the flight fraction, clamped to [0, 1] — 1.0 draws the full path plus
    the result's landing-act marker (wall tick / glove / warning track /
    fair splash); any earlier fraction draws a partial trail with a bright
    2px ball at the leading edge and no act marker yet."""
    x0, y0, w, h = box
    ground = y0 + h - 1
    progress = max(0.0, min(1.0, progress))

    # faint ground line
    for i in range(w):
        px(real, x0 + i, ground, pal.dim(pal.LABEL, 0.45))

    n = len(plan.points)
    if n == 0:
        return
    shown = max(1, int(round(n * progress)))
    trail = pal.dim(pal.MAGENTA, 0.5)
    prev = None
    for idx in range(shown):
        cx, cy = plan.points[idx]
        px(real, x0 + cx, y0 + cy, pal.MAGENTA if idx == shown - 1 else trail)
        if prev is not None and idx != shown - 1:
            plo, phi = sorted((prev[1], cy))
            for yy in range(plo, phi + 1):
                px(real, x0 + cx, y0 + yy, trail)
        prev = (cx, cy)

    # the ball: 2px bright dot at the leading edge, clamped to the box
    # bottom — the parabola's final point always lands at local y=h-1
    # (ground), so the unclamped dy=1 row would bleed 1px below the box
    bx, by = plan.points[shown - 1]
    for dx in range(2):
        for dy in range(2):
            px(real, x0 + bx + dx, min(y0 + by + dy, ground), pal.MAGENTA)

    if progress < 1.0:
        return  # act markers only at rest

    lx, ly = plan.landing
    if plan.act == "clears" and plan.wall_x is not None:
        # intentional 1px over/under-bleed above/below the box (full-bleed
        # look for the wall tick) — do NOT clamp this to [0, h) as a "fix"
        for yy in range(-1, h + 1):
            px(real, x0 + plan.wall_x, y0 + yy, pal.IDENT)
    elif plan.act == "caught":
        for dx in range(-1, 2):  # small glove ring, dim grey
            for dy in range(-1, 2):
                if abs(dx) + abs(dy) == 1:
                    px(real, x0 + lx + dx, y0 + ly + dy, pal.dim(pal.LABEL, 0.9))
    elif plan.act == "track":
        # dotted warning-track line near the wall; row count clamped to the
        # box height so it can't bleed above the box top (was unclamped)
        for i in range(0, min(w // 4, h - 1)):
            px(real, x0 + w - 6 + (i % 2), ground - 1 - i, pal.dim(pal.AMBER, 0.6))
    elif plan.act == "fair":
        px(real, x0 + lx, ground, pal.MAGENTA)
