"""flair.splitflap — the Solari split-flap departure board, in place: every
character of the outgoing message is a flap hinged across its middle; it
clatters through a few in-between characters and lands on the incoming
character, with a ripple so characters settle one after another.

Spec: docs/superpowers/specs/2026-11-10-flair-splitflap-transition-design.md

Design in one breath: both widgets are snapshotted ONCE per firing through
accordion's deck segmentation (``DeckSnapshotMixin``; both are on screen
together, so ``scale_switch_at = 1.0``); ``build_board`` pairs their cells
into flaps with pre-slotted flip sequences; every frame is a pure function
of ``s = min(t / SNAP_THRESHOLD / LAND, 1)`` — each flap starts at its
ripple position and flips ``len(seq) - 1`` times at a fixed flap length.
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
from ._variants import Cycling
from .splitflap_board import Board, build_board
from .splitflap_paint import paint_cell, paint_flap

ORDERS = ("forward", "reverse", "random")
LAND = 0.9  # every flap has landed by this share of the pre-snap timeline
MAX_STAGGER = 0.9
# Past ~9 in-between flips each flap is shorter than a frame at the 36-frame
# floor; the cap keeps a config typo from blocking the loop at board build.
MAX_FLIPS = 12


def _coerce_flips(flips: Any) -> int:
    if (
        isinstance(flips, bool)
        or not isinstance(flips, int)
        or not 0 <= flips <= MAX_FLIPS
    ):
        raise ValueError(f"flips must be an int in [0, {MAX_FLIPS}]; got {flips!r}")
    return flips


def _coerce_stagger(stagger: Any) -> float:
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


def _paint_pixels(set_px: Any, pixels: tuple[Pixel, ...]) -> None:
    for x, y, (r, g, b) in pixels:
        set_px(x, y, r, g, b)


class SplitFlap(DeckSnapshotMixin):
    """Ripple left -> right.

    ``scale_switch_at = 1.0``: both widgets share the panel for the whole
    transition, so the runner keeps the outgoing bg + scale until the snap
    (a cross-scale incoming renders at the outgoing scale until then; a bg
    change lands at the snap) — the blinds / laser limitation.
    """

    min_frames = 36
    scale_switch_at = 1.0
    _order = "forward"

    def __init__(self, flips: Any = 3, stagger: Any = 0.5) -> None:
        self.flips: int = _coerce_flips(flips)
        self.stagger: float = _coerce_stagger(stagger)
        self._init_deck_snapshot(False)
        self._board: Board | None = None
        self._starts: list[float] = []
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
            self._board = build_board(out_plan, in_plan, self.flips, self._rng)
            self._starts = self._ripple(self._board)
        # `real` is re-derived EVERY call, never cached (constraint #1).
        real = unwrap_to_real(canvas) if is_scaled(canvas) else canvas
        s = min(t / SNAP_THRESHOLD / LAND, 1.0)
        self._paint(real, self._board, s)
        return canvas

    def _ripple(self, board: Board) -> list[float]:
        xs = [f.centre_x for f in board.flaps]
        if not xs:
            return []
        lo, hi = min(xs), max(xs)
        return [
            flap_start(self._order, x, lo, hi, self.stagger, self._rng.random())
            for x in xs
        ]

    def _paint(self, real: Any, board: Board, s: float) -> None:
        w, h = real.width, real.height
        set_px = real.SetPixel
        first_half = s < 0.5
        _paint_pixels(set_px, board.under_out if first_half else board.under_in)
        f = (1.0 - self.stagger) / (self.flips + 1)
        for flap, start in zip(board.flaps, self._starts, strict=True):
            seq = flap.seq
            if flap.static:
                paint_cell(set_px, seq[0], w, h)
                continue
            steps = len(seq) - 1
            u = (s - start) / f
            if u <= 0.0:
                paint_cell(set_px, seq[0], w, h)
            elif u >= steps:
                paint_cell(set_px, seq[-1], w, h)
            else:
                k = int(u)
                paint_flap(
                    set_px, seq[k], seq[k + 1], board.bands[flap.band], u - k, w, h
                )
        _paint_pixels(set_px, board.ring_out if first_half else board.ring_in)


class SplitFlapReverse(SplitFlap):
    """Ripple right -> left."""

    _order = "reverse"


class SplitFlapRandom(SplitFlap):
    """Characters settle in a random order, fresh each firing."""

    _order = "random"


class SplitFlapAlternating(Cycling):
    """Cycles forward -> reverse, one per firing."""

    def __init__(self, flips: Any = 3, stagger: Any = 0.5) -> None:
        super().__init__([SplitFlap(flips, stagger), SplitFlapReverse(flips, stagger)])
