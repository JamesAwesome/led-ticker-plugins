"""flair.blinds — the venetian-blind ("shutter") reveal of HD/Huidu-class
LED controllers: the panel is cut into N equal slats and every slat wipes
open at the same time, in the same direction, revealing the incoming
content through the outgoing.

Spec: docs/superpowers/specs/2026-11-09-flair-interlock-blinds-transitions-design.md

Design in one breath: both widgets are snapshotted ONCE per firing (both are
on screen together, so ``scale_switch_at = 1.0`` — laser's hard-edged
convention); each lit pixel is tagged with its slat and its depth from that
slat's leading edge; every frame reveals the first ``round(p * slat_size)``
rows/columns of every slat (incoming bg SubFill + incoming pixels) and paints
the outgoing pixels everywhere else.
"""

from dataclasses import dataclass

from ._raster import Raster, is_lit
from ._snapshot import Geometry

DIRECTIONS = ("down", "up", "right", "left")
DEFAULT_SLATS = {"horizontal": 4, "vertical": 8}

# (x, y, r, g, b, slat, depth)
SlatPixel = tuple[int, int, int, int, int, int, int]


def orientation(direction: str) -> str:
    if direction not in DIRECTIONS:
        raise ValueError(f"direction must be one of {DIRECTIONS}; got {direction!r}")
    return "horizontal" if direction in ("down", "up") else "vertical"


def slat_bounds(size: int, slats: int, scale: int) -> list[tuple[int, int]]:
    """Half-open real-px bounds covering ``[0, size)``. Every slat is a
    whole number of logical pixels (``scale`` real px); the count clamps so
    each slat is at least one logical pixel; the last slat takes the
    remainder."""
    logical = max(1, size // scale)
    n = max(1, min(slats, logical))
    base = (logical // n) * scale
    bounds = [(k * base, (k + 1) * base) for k in range(n)]
    bounds[-1] = (bounds[-1][0], size)
    return bounds


def revealed(p: float, lo: int, hi: int) -> int:
    """Rows/columns of a ``[lo, hi)`` slat revealed at progress ``p``."""
    return round(p * (hi - lo))


@dataclass(frozen=True)
class BlindsPlan:
    direction: str
    bounds: list[tuple[int, int]]
    out_px: list[SlatPixel]
    in_px: list[SlatPixel]


def _tag(
    raster: Raster, direction: str, bounds: list[tuple[int, int]]
) -> list[SlatPixel]:
    rows = orientation(direction) == "horizontal"
    size = raster.height if rows else raster.width
    # coord -> (slat, depth from that slat's leading edge)
    lookup: list[tuple[int, int]] = [(0, 0)] * size
    for s, (lo, hi) in enumerate(bounds):
        for c in range(lo, min(hi, size)):
            depth = c - lo if direction in ("down", "right") else hi - 1 - c
            lookup[c] = (s, depth)
    out: list[SlatPixel] = []
    get = raster.get
    for y in range(raster.height):
        for x in range(raster.width):
            px = get(x, y)
            if not is_lit(px):
                continue
            r, g, b = px  # type: ignore[misc]
            s, depth = lookup[y if rows else x]
            out.append((x, y, r, g, b, s, depth))
    return out


def build_plan(
    out_r: Raster, in_r: Raster, direction: str, slats: int, geo: Geometry
) -> BlindsPlan:
    rows = orientation(direction) == "horizontal"
    bounds = slat_bounds(geo.height if rows else geo.width, slats, geo.scale)
    return BlindsPlan(
        direction, bounds, _tag(out_r, direction, bounds), _tag(in_r, direction, bounds)
    )
