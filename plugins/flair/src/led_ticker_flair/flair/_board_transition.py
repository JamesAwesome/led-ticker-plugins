"""The ONE firing loop for board-style flair transitions.

A board transition snapshots both widgets once per firing (through
``DeckSnapshotMixin``), pairs their cells into a ``Board`` of flaps with
pre-slotted step sequences (``build_board``), and renders every frame as a pure
function of ``s = min(t / SNAP_THRESHOLD / LAND, 1)``. ``splitflap`` and
``slots`` subclass ``BoardTransition`` and supply ``_paint`` (and optionally
``_schedule``); they may also override ``__init__`` to coerce their knobs and
set a per-instance ``min_frames``.

Specs: docs/superpowers/specs/2026-11-10-flair-splitflap-transition-design.md
and docs/superpowers/specs/2026-11-24-flair-slots-transition-design.md
"""

import random
from typing import Any

from led_ticker.plugin import (
    SNAP_THRESHOLD,
    Canvas,
    is_scaled,
    snap_reset,
    unwrap_to_real,
)

from ._deck_snapshot import DeckSnapshotMixin
from ._raster import Pixel
from .splitflap_board import Board, build_board

ORDERS = ("forward", "reverse", "random")
LAND = 0.9  # every flap has landed by this share of the pre-snap timeline
MAX_STAGGER = 0.9


def coerce_steps(value: Any, name: str, cap: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= cap:
        raise ValueError(f"{name} must be an int in [0, {cap}]; got {value!r}")
    return value


def coerce_stagger(stagger: Any) -> float:
    if isinstance(stagger, bool) or not isinstance(stagger, int | float):
        raise ValueError(f"stagger must be a number in [0, 0.9]; got {stagger!r}")
    if not 0.0 <= stagger <= MAX_STAGGER:
        raise ValueError(f"stagger must be in [0, 0.9]; got {stagger!r}")
    return float(stagger)


def flap_start(
    order: str, centre_x: int, x_min: int, x_max: int, stagger: float, rand: float
) -> float:
    """Timeline position at which a flap starts flipping."""
    if order == "random":
        return stagger * rand
    frac = (centre_x - x_min) / max(x_max - x_min, 1)
    return stagger * (frac if order == "forward" else 1.0 - frac)


def paint_pixels(set_px: Any, pixels: tuple[Pixel, ...]) -> None:
    for x, y, (r, g, b) in pixels:
        set_px(x, y, r, g, b)


class BoardTransition(DeckSnapshotMixin):
    """Base for board-style transitions; subclasses implement ``_paint``.

    ``scale_switch_at = 1.0``: both widgets share the panel for the whole
    transition, so the runner keeps the outgoing bg + scale until the snap
    (a cross-scale incoming renders at the outgoing scale until then; a bg
    change lands at the snap) — the blinds / laser limitation.
    """

    min_frames = 36
    scale_switch_at = 1.0
    _order = "forward"

    def __init__(self, steps: int, stagger: float) -> None:
        self.steps = steps
        self.stagger = stagger
        self._init_deck_snapshot(False)
        self._board: Board | None = None
        self._times: list[float] = []
        self._last_t = 1.0
        self._rng = random.Random()

    def frame_at(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        if t == 0.0 or t < self._last_t:  # new firing -> fresh snapshots
            self._board = None
        self._last_t = t

        if t >= SNAP_THRESHOLD:
            snap_reset(canvas, kwargs.get("incoming_bg_color"))
            incoming.draw(canvas, cursor_pos=0)
            return canvas

        if self._board is None:
            pos = kwargs.get("outgoing_scroll_pos", 0)
            out_plan = self._plan(canvas, outgoing, pos, 0)
            in_plan = self._plan(canvas, incoming, 0, 1)
            self._board = build_board(out_plan, in_plan, self.steps, self._rng)
            self._times = self._schedule(self._board)
        # `real` is re-derived EVERY call, never cached (constraint #1).
        real = unwrap_to_real(canvas) if is_scaled(canvas) else canvas
        s = min(t / SNAP_THRESHOLD / LAND, 1.0)
        self._paint(real, self._board, s)
        return canvas

    def _schedule(self, board: Board) -> list[float]:
        xs = [f.centre_x for f in board.flaps]
        if not xs:
            return []
        lo, hi = min(xs), max(xs)
        return [
            flap_start(self._order, x, lo, hi, self.stagger, self._rng.random())
            for x in xs
        ]

    def _paint(self, real: Any, board: Board, s: float) -> None:
        raise NotImplementedError
