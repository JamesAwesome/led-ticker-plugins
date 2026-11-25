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

from typing import Any

from ._board_transition import (  # noqa: F401  (re-exports for existing importers)
    LAND,
    MAX_STAGGER,
    ORDERS,
    BoardTransition,
    coerce_stagger,
    coerce_steps,
    flap_start,
    paint_pixels,
)
from ._variants import Cycling
from .splitflap_board import Board
from .splitflap_paint import paint_cell, paint_flap

# Past ~9 in-between flips each flap is shorter than a frame at the 36-frame
# floor; the cap keeps a config typo from blocking the loop at board build.
MAX_FLIPS = 12


class SplitFlap(BoardTransition):
    """Ripple left -> right (the base's ``_schedule``)."""

    min_frames = 36

    def __init__(self, flips: Any = 3, stagger: Any = 0.5) -> None:
        self.flips: int = coerce_steps(flips, "flips", MAX_FLIPS)
        super().__init__(self.flips, coerce_stagger(stagger))

    def _paint(self, real: Any, board: Board, s: float) -> None:
        w, h = real.width, real.height
        set_px = real.SetPixel
        first_half = s < 0.5
        paint_pixels(set_px, board.under_out if first_half else board.under_in)
        f = (1.0 - self.stagger) / (self.flips + 1)
        for flap, start in zip(board.flaps, self._times, strict=True):
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
        paint_pixels(set_px, board.ring_out if first_half else board.ring_in)


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
