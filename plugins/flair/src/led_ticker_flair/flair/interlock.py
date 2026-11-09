"""flair.interlock — the BetaBrite / Alpha "Interlock" special mode: the
outgoing content is cut into strands (bands of rows, or columns for the
vertical variant) and alternate strands slide off toward opposite edges;
then the incoming strands race in from opposite edges and mesh together.

Spec: docs/superpowers/specs/2026-11-09-flair-interlock-blinds-transitions-design.md

Design in one breath: each widget is snapshotted ONCE per firing into a
readable raster (the incoming LAZILY, on the first ``t >= 0.5`` frame, so a
cross-scale incoming meshes in at its native size); its lit pixels are
grouped by strand parity; every frame shifts each parity group along the
travel axis by a pure function of ``t``. Travel is CONTENT-sized per parity
group, so the outgoing has just cleared at ``t = 0.5`` and the incoming
appears right after — the cut-over frame is the only empty one.
"""

import math
from dataclasses import dataclass

from led_ticker.plugin import SNAP_THRESHOLD

from ._raster import Pixel, Raster, is_lit
from ._snapshot import Geometry

AXES = ("horizontal", "vertical")
_HALF = 0.5


def strand_index(coord: int, anchor: int, strand_px: int, n_strands: int) -> int:
    """Strand of a real-pixel ``coord``; letterbox coords clamp into the
    first / last strand."""
    return max(0, min(n_strands - 1, (coord - anchor) // strand_px))


def clear_distance(lo: int, hi: int, size: int, toward_positive: bool) -> int:
    """Shift that just moves the inclusive lit extent ``[lo, hi]`` off the
    panel edge it travels toward (``size`` = panel extent on that axis)."""
    return size - lo if toward_positive else hi + 1


def _clamp01(v: float) -> float:
    return 0.0 if v < 0.0 else 1.0 if v > 1.0 else v


def split_offset(t: float, d: int) -> int:
    """Outgoing shift magnitude: 0 at t=0, the full ``d`` at t=0.5."""
    return round(d * _clamp01(t / _HALF))


def mesh_offset(t: float, d: int) -> int:
    """Incoming shift magnitude: the full ``d`` at t=0.5, 0 at the snap."""
    return round(d * (1.0 - _clamp01((t - _HALF) / (SNAP_THRESHOLD - _HALF))))


@dataclass(frozen=True)
class InterlockPlan:
    """Lit pixels of one snapshot split by strand parity, plus each
    parity's inclusive lit extent along the TRAVEL axis (``-1`` when that
    parity has no lit pixels). ``size`` is the real panel extent along the
    travel axis."""

    axis: str
    even: list[Pixel]
    odd: list[Pixel]
    even_lo: int
    even_hi: int
    odd_lo: int
    odd_hi: int
    size: int


def build_plan(raster: Raster, axis: str, geo: Geometry, strand: int) -> InterlockPlan:
    if axis not in AXES:
        raise ValueError(f"axis must be one of {AXES}; got {axis!r}")
    horizontal = axis == "horizontal"
    strand_px = strand * geo.scale
    if horizontal:
        anchor, n = geo.y_offset_real, math.ceil(geo.content_h_real / strand_px)
        size = geo.width
    else:
        anchor, n = 0, math.ceil(geo.width / strand_px)
        size = geo.height
    groups: tuple[list[Pixel], list[Pixel]] = ([], [])
    ext = [[-1, -1], [-1, -1]]
    get = raster.get
    for y in range(raster.height):
        for x in range(raster.width):
            px = get(x, y)
            if not is_lit(px):
                continue
            parity = strand_index(y if horizontal else x, anchor, strand_px, n) % 2
            groups[parity].append((x, y, px))  # type: ignore[arg-type]
            k = x if horizontal else y
            e = ext[parity]
            if e[0] < 0 or k < e[0]:
                e[0] = k
            if k > e[1]:
                e[1] = k
    return InterlockPlan(
        axis, groups[0], groups[1], ext[0][0], ext[0][1], ext[1][0], ext[1][1], size
    )
