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
from typing import Any

from led_ticker.plugin import (
    SNAP_THRESHOLD,
    Canvas,
    is_scaled,
    snap_reset,
    unwrap_to_real,
)

from ._raster import Raster, is_lit
from ._snapshot import Geometry, SnapshotCache, geometry_of
from ._variants import Cycling, RandomNoRepeat

DIRECTIONS = ("down", "up", "right", "left")
DEFAULT_SLATS = {"horizontal": 8, "vertical": 8}

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
    """``bounds`` are the slats (they cover the content band only);
    ``extent`` is the panel span on the slat axis. Letterbox strips outside
    the bounds belong to the first / last slat: the strip on a slat's
    LEADING side opens with its first row, the one on its TRAILING side with
    its last, so every slat opens at the same rate."""

    direction: str
    bounds: list[tuple[int, int]]
    extent: tuple[int, int]
    out_px: list[SlatPixel]
    in_px: list[SlatPixel]


def _tag(
    raster: Raster, direction: str, bounds: list[tuple[int, int]]
) -> list[SlatPixel]:
    rows = orientation(direction) == "horizontal"
    size = raster.height if rows else raster.width
    first, last = bounds[0][0], bounds[-1][1] - 1
    # coord -> (slat, depth from that slat's leading edge). A letterbox
    # coord takes its nearest content row's tag (see BlindsPlan).
    by_coord: dict[int, tuple[int, int]] = {}
    for s, (lo, hi) in enumerate(bounds):
        for c in range(lo, hi):
            depth = c - lo if direction in ("down", "right") else hi - 1 - c
            by_coord[c] = (s, depth)
    lookup = [by_coord[min(last, max(first, c))] for c in range(size)]
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
    if rows:
        # Split the CONTENT band (anchored at y_offset_real, like interlock's
        # strands) so "N slats" means N visible, equal slats on a letterboxed
        # panel; the letterbox strips ride the edge slats (see BlindsPlan).
        y0 = geo.y_offset_real
        bounds = [
            (lo + y0, hi + y0)
            for lo, hi in slat_bounds(geo.content_h_real, slats, geo.scale)
        ]
        extent = (0, geo.height)
    else:
        bounds = slat_bounds(geo.width, slats, geo.scale)
        extent = (0, geo.width)
    return BlindsPlan(
        direction,
        bounds,
        extent,
        _tag(out_r, direction, bounds),
        _tag(in_r, direction, bounds),
    )


def _coerce_slats(slats: Any) -> int:
    if isinstance(slats, bool) or not isinstance(slats, int) or slats < 1:
        raise ValueError(f"slats must be a positive int; got {slats!r}")
    return slats


class Blinds:
    """Horizontal slats, each opening top -> bottom.

    ``scale_switch_at = 1.0``: both widgets share the panel for the whole
    transition, so the runner keeps the outgoing bg + scale throughout and
    the revealed bands get the incoming bg via one ``SubFill`` per slat.
    Cross-scale incoming renders at the outgoing scale until the snap (same
    accepted limitation as laser / fairy / lightning).
    """

    min_frames = 16
    scale_switch_at = 1.0
    _direction = "down"

    def __init__(self, slats: Any = None) -> None:
        if slats is None:
            slats = DEFAULT_SLATS[orientation(self._direction)]
        self.slats: int = _coerce_slats(slats)
        self._plan: BlindsPlan | None = None
        self._last_t = 1.0
        self._cache = SnapshotCache()

    def frame_at(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        if t == 0.0 or t < self._last_t:  # new firing -> fresh snapshots
            self._plan = None
        self._last_t = t

        bg = kwargs.get("incoming_bg_color")
        if t >= SNAP_THRESHOLD:
            snap_reset(canvas, bg)
            incoming.draw(canvas, cursor_pos=0)
            return canvas

        if self._plan is None:
            pos = kwargs.get("outgoing_scroll_pos", 0)
            out_r = self._cache.take(canvas, outgoing, pos, 0)
            in_r = self._cache.take(canvas, incoming, 0, 1)
            self._plan = build_plan(
                out_r, in_r, self._direction, self.slats, geometry_of(canvas)
            )
        # `real` is re-derived EVERY call, never cached (constraint #1).
        real = unwrap_to_real(canvas) if is_scaled(canvas) else canvas
        self._paint(real, self._plan, t / SNAP_THRESHOLD, bg or (0, 0, 0))
        return canvas

    @staticmethod
    def _paint(real: Any, plan: BlindsPlan, p: float, bg: tuple[int, int, int]) -> None:
        d = plan.direction
        open_n = [revealed(p, lo, hi) for lo, hi in plan.bounds]
        w, h = real.width, real.height
        br, bgc, bb = bg
        positive = d in ("down", "right")
        last = len(plan.bounds) - 1
        for s, ((lo, hi), n) in enumerate(zip(plan.bounds, open_n, strict=True)):
            if n <= 0:
                continue
            a, b = (lo, lo + n) if positive else (hi - n, hi)
            if s == 0 and a == lo:  # the leading / fully-open slat edge
                a = plan.extent[0]
            if s == last and b == hi:
                b = plan.extent[1]
            if d in ("down", "up"):
                real.SubFill(0, a, w, b - a, br, bgc, bb)
            else:
                real.SubFill(a, 0, b - a, h, br, bgc, bb)
        set_px = real.SetPixel
        for x, y, r, g, b, s, depth in plan.in_px:
            if depth < open_n[s]:
                set_px(x, y, r, g, b)
        for x, y, r, g, b, s, depth in plan.out_px:
            if depth >= open_n[s]:
                set_px(x, y, r, g, b)


class BlindsUp(Blinds):
    """Horizontal slats, each opening bottom -> top."""

    _direction = "up"


class BlindsRight(Blinds):
    """Vertical slats, each opening left -> right."""

    _direction = "right"


class BlindsLeft(Blinds):
    """Vertical slats, each opening right -> left."""

    _direction = "left"


def _four(slats: Any) -> list[Blinds]:
    return [Blinds(slats), BlindsRight(slats), BlindsUp(slats), BlindsLeft(slats)]


class BlindsAlternating(Cycling):
    """Cycles down -> right -> up -> left (laser order), one per firing. An
    explicit ``slats`` applies to both orientations; omitted, each keeps
    its own default."""

    def __init__(self, slats: Any = None) -> None:
        super().__init__(_four(slats))


class BlindsRandom(RandomNoRepeat):
    """Picks a direction per firing, never the same one back-to-back."""

    def __init__(self, slats: Any = None) -> None:
        super().__init__(_four(slats))
