"""flair.slots — each character spins vertically like a slot-machine reel,
decelerates, overshoots about a row and settles on the incoming character.

Design in one breath: every reel starts on the first frame and stops one
after another (``reel_stop`` ripples the stop times); a reel's per-frame
position is a pure function of its local timeline ``u`` in [0, 1] — a
trapezoid speed profile (ramp up, cruise, ramp down) integrated into
``displacement``, then a sine overshoot-and-settle past the landing row.
"""

import math
from dataclasses import dataclass
from typing import Any

from ._board_transition import (
    BoardTransition,
    coerce_stagger,
    coerce_steps,
    flap_start,
    paint_pixels,
)
from ._variants import Cycling
from .slots_paint import (
    SPIN_SHADE,
    overshoot_rows,
    paint_reel,
    reel_pitch,
    strip_symbols,
)
from .splitflap_board import Board, FlapCell
from .splitflap_paint import paint_cell

MAX_SPINS = 6
U_IN = 0.15  # end of the speed ramp-up
CRUISE_END = 0.45  # end of full-speed cruise
SETTLE_START = 0.9  # reel reaches the landing row; overshoot-settle follows


def reel_stop(
    order: str, centre_x: int, x_min: int, x_max: int, stagger: float, rand: float
) -> float:
    """Timeline position at which this reel stops."""
    return (1.0 - stagger) + flap_start(order, centre_x, x_min, x_max, stagger, rand)


def reel_advances(spins: int, stop: float, stagger: float) -> int:
    """Symbols the reel advances through before landing (at least one)."""
    return max(1, round((spins + 1) * stop / (1.0 - stagger)))


def _clamp01(u: float) -> float:
    return min(max(u, 0.0), 1.0)


def speed_norm(u: float) -> float:
    """Trapezoid speed profile, peak 1.0, zero once settling starts."""
    u = _clamp01(u)
    if u < U_IN:
        return u / U_IN
    if u < CRUISE_END:
        return 1.0
    if u < SETTLE_START:
        return (SETTLE_START - u) / (SETTLE_START - CRUISE_END)
    return 0.0


def _integral(u: float) -> float:
    """Closed-form integral of ``speed_norm`` over [0, u], u <= SETTLE_START."""
    if u < U_IN:
        return u * u / (2.0 * U_IN)
    if u < CRUISE_END:
        return U_IN / 2.0 + (u - U_IN)
    ramp = SETTLE_START - CRUISE_END
    frac = (SETTLE_START - u) / ramp
    return U_IN / 2.0 + (CRUISE_END - U_IN) + ramp / 2.0 * (1.0 - frac * frac)


def displacement(u: float, travel: float, overshoot: int) -> float:
    """Reel position along its strip: ``travel`` at SETTLE_START, a sine
    overshoot of ``overshoot`` rows after it, back to ``travel`` at u = 1."""
    u = _clamp01(u)
    if u <= SETTLE_START:
        return travel * _integral(u) / _integral(SETTLE_START)
    return travel + overshoot * math.sin(
        math.pi * (u - SETTLE_START) / (1.0 - SETTLE_START)
    )


def shade_for(u: float) -> float:
    """Symbol brightness: dimmed by ``SPIN_SHADE`` at full speed, plain at rest."""
    return 1.0 - (1.0 - SPIN_SHADE) * speed_norm(u)


@dataclass(frozen=True)
class Reel:
    stop: float
    k: int
    strip: tuple[FlapCell | None, ...]


class Slots(BoardTransition):
    """Reels stop left -> right."""

    min_frames = 60

    def __init__(self, spins: Any = 3, stagger: Any = 0.5) -> None:
        self.spins: int = coerce_steps(spins, "spins", MAX_SPINS)
        super().__init__(self.spins, coerce_stagger(stagger))
        self._reels: list[Reel] = []

    def _schedule(self, board: Board) -> list[float]:
        xs = [f.centre_x for f in board.flaps]
        if not xs:
            self._reels = []
            return []
        lo, hi = min(xs), max(xs)
        stops = [
            reel_stop(self._order, x, lo, hi, self.stagger, self._rng.random())
            for x in xs
        ]
        reels: list[Reel] = []
        for flap, stop in zip(board.flaps, stops, strict=True):
            if flap.static:
                reels.append(Reel(stop, 1, flap.seq))  # never painted via the strip
                continue
            k = reel_advances(self.spins, stop, self.stagger)
            reels.append(Reel(stop, k, strip_symbols(flap.seq, k)))
        self._reels = reels
        return stops

    def _paint(self, real: Any, board: Board, s: float) -> None:
        w, h = real.width, real.height
        set_px = real.SetPixel
        first_half = s < 0.5
        paint_pixels(set_px, board.under_out if first_half else board.under_in)
        for flap, reel in zip(board.flaps, self._reels, strict=True):
            if flap.static:
                paint_cell(set_px, flap.seq[0], w, h)
                continue
            u = min(1.0, s / reel.stop)
            band = board.bands[flap.band]
            pitch, gap = reel_pitch(band)
            d = displacement(u, reel.k * pitch, overshoot_rows(pitch, gap))
            paint_reel(set_px, reel.strip, band, d, shade_for(u), w, h)
        paint_pixels(set_px, board.ring_out if first_half else board.ring_in)


class SlotsReverse(Slots):
    """Reels stop right -> left."""

    _order = "reverse"


class SlotsRandom(Slots):
    """Reels stop in a random order, fresh each firing."""

    _order = "random"


class SlotsAlternating(Cycling):
    """Cycles forward -> reverse, one per firing."""

    def __init__(self, spins: Any = 3, stagger: Any = 0.5) -> None:
        super().__init__([Slots(spins, stagger), SlotsReverse(spins, stagger)])
