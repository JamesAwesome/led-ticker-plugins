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
from typing import Any

from led_ticker.plugin import (
    SNAP_THRESHOLD,
    Canvas,
    is_scaled,
    snap_reset,
    unwrap_to_real,
)

from ._raster import Pixel, Raster, is_lit
from ._snapshot import Geometry, SnapshotCache, geometry_of
from ._variants import Cycling, RandomNoRepeat

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


def _coerce_strand(strand: Any) -> int:
    if isinstance(strand, bool) or not isinstance(strand, int) or strand < 1:
        raise ValueError(f"strand must be a positive int; got {strand!r}")
    return strand


class Interlock:
    """Horizontal interlock (the Alpha classic): even row-strands travel
    left -> right, odd ones right -> left, in BOTH phases (conveyor).

    Keeps the runner's default ``scale_switch_at`` (0.5): the split phase
    empties the panel exactly at the cut-over, so the bg / scale switch is
    invisible, and the incoming is snapshotted lazily from the first
    ``t >= 0.5`` frame's (possibly re-wrapped) canvas.
    """

    min_frames = 24
    _axis = "horizontal"
    _even_positive = True

    def __init__(self, strand: Any = 1) -> None:
        self.strand: int = _coerce_strand(strand)
        self._out_plan: InterlockPlan | None = None
        self._in_plan: InterlockPlan | None = None
        self._last_t = 1.0
        self._cache = SnapshotCache()

    def _plan(self, canvas: Any, widget: Any, pos: int, slot: int) -> InterlockPlan:
        raster = self._cache.take(canvas, widget, pos, slot)
        return build_plan(raster, self._axis, geometry_of(canvas), self.strand)

    def frame_at(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        if t == 0.0 or t < self._last_t:  # new firing -> fresh snapshots
            self._out_plan = None
            self._in_plan = None
        self._last_t = t

        if t >= SNAP_THRESHOLD:
            snap_reset(canvas, kwargs.get("incoming_bg_color"))
            incoming.draw(canvas, cursor_pos=0)
            return canvas

        if self._out_plan is None:
            pos = kwargs.get("outgoing_scroll_pos", 0)
            self._out_plan = self._plan(canvas, outgoing, pos, 0)
        # `real` is re-derived EVERY call, never cached (constraint #1).
        real = unwrap_to_real(canvas) if is_scaled(canvas) else canvas

        if t < _HALF:
            self._paint(real, self._out_plan, t, split=True)
        else:
            if self._in_plan is None:  # lazy: this frame's (re-wrapped) canvas
                self._in_plan = self._plan(canvas, incoming, 0, 1)
            self._paint(real, self._in_plan, t, split=False)
        return canvas

    def _paint(self, real: Any, plan: InterlockPlan, t: float, split: bool) -> None:
        horizontal = plan.axis == "horizontal"
        limit = plan.size
        set_px = real.SetPixel
        groups = (
            (0, plan.even, plan.even_lo, plan.even_hi),
            (1, plan.odd, plan.odd_lo, plan.odd_hi),
        )
        for parity, pixels, lo, hi in groups:
            if not pixels:
                continue
            sign = 1 if (parity == 0) == self._even_positive else -1
            if split:
                d = clear_distance(lo, hi, limit, toward_positive=sign > 0)
                shift = sign * split_offset(t, d)
            else:
                d = clear_distance(lo, hi, limit, toward_positive=sign < 0)
                shift = -sign * mesh_offset(t, d)
            for x, y, (r, g, b) in pixels:
                if horizontal:
                    x += shift
                    if 0 <= x < limit:
                        set_px(x, y, r, g, b)
                else:
                    y += shift
                    if 0 <= y < limit:
                        set_px(x, y, r, g, b)


class InterlockFlipped(Interlock):
    """Horizontal, even strands right -> left (used by ``.random``)."""

    _even_positive = False


class InterlockVertical(Interlock):
    """Column strands: even ones travel top -> bottom, odd bottom -> top."""

    _axis = "vertical"


class InterlockVerticalFlipped(InterlockVertical):
    """Vertical, even strands bottom -> top (used by ``.random``)."""

    _even_positive = False


class InterlockAlternating(Cycling):
    """Cycles horizontal -> vertical, one axis per firing."""

    def __init__(self, strand: Any = 1) -> None:
        super().__init__([Interlock(strand), InterlockVertical(strand)])


class InterlockRandom(RandomNoRepeat):
    """Picks per firing from axis x parity-flip (four choices), never the
    same one back-to-back."""

    def __init__(self, strand: Any = 1) -> None:
        super().__init__(
            [
                Interlock(strand),
                InterlockFlipped(strand),
                InterlockVertical(strand),
                InterlockVerticalFlipped(strand),
            ]
        )
