"""flair.slots — each character spins vertically like a slot-machine reel,
decelerates, overshoots about a row and settles on the incoming character.

Design in one breath: every reel starts on the first frame and stops one
after another (``_schedule`` ripples the stop times); a reel's per-frame
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
DEFAULT_SPINS = 3
DEFAULT_STAGGER = 0.5
MIN_FRAMES = 60  # floor at the default knobs: 3 s at the 20 fps engine tick
U_IN = 0.15  # end of the speed ramp-up
CRUISE_END = 0.45  # end of full-speed cruise
SETTLE_START = 0.9  # reel reaches the landing row; overshoot-settle follows


def rounding_headroom(spins: int) -> float:
    """Worst per-reel speed over nominal, from rounding to whole symbols."""
    return (spins + 2) / (spins + 1.5)


def pace_floor(spins: int, stagger: float) -> int:
    """Smallest frame count at which the reels spin no faster than at the
    default knobs over MIN_FRAMES frames. Cruise speed scales with
    (spins + 1) / (1 - stagger), and rounding each reel's advances to a whole
    symbol adds up to ``rounding_headroom(spins)``; the floor scales by both."""
    scale = (
        (spins + 1)
        / (DEFAULT_SPINS + 1)
        * (1.0 - DEFAULT_STAGGER)
        / (1.0 - stagger)
        * rounding_headroom(spins)
        / rounding_headroom(DEFAULT_SPINS)
    )
    # round first: float noise (150.00000000000003) must not cost a frame
    return max(MIN_FRAMES, math.ceil(round(MIN_FRAMES * scale, 6)))


def reel_advances(spins: int, stop: float, stagger: float) -> int:
    """Symbols the reel advances through before landing (at least one).

    Precondition: ``stagger < 1`` (``coerce_stagger`` caps it at 0.9). The
    ``1 / (1 - stagger)`` factor is what ``pace_floor`` compensates for."""
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


def glide(u: float) -> float:
    """Travel progress in [0, 1]: the fraction of the strip travel covered by
    local time ``u``; 1.0 from SETTLE_START on (the overshoot is vertical only)."""
    return _integral(min(_clamp01(u), SETTLE_START)) / _integral(SETTLE_START)


def reel_window(x0: int, w0: int, x1: int, w1: int, g: float) -> tuple[int, int, float]:
    """``(left, width, centre)`` of the reel window at travel progress ``g``:
    centre and width glide from the outgoing glyph's column to the incoming
    one's. ``centre`` is the unrounded float; symbols are placed from it."""
    c0 = x0 + w0 / 2
    cx = c0 + ((x1 + w1 / 2) - c0) * g
    wf = w0 + (w1 - w0) * g
    # round the two EDGES, not left + width: each edge is then monotone in g
    left = round(cx - wf / 2)
    right = round(cx + wf / 2)
    return left, right - left, cx


@dataclass(frozen=True)
class Reel:
    stop: float
    k: int
    strip: tuple[FlapCell | None, ...]
    x0: int  # column geometry of the strip's first / last symbol
    w0: int
    x1: int
    w1: int


class Slots(BoardTransition):
    """Reels stop left -> right."""

    min_frames = MIN_FRAMES  # base; each instance raises it via pace_floor

    def __init__(
        self, spins: Any = DEFAULT_SPINS, stagger: Any = DEFAULT_STAGGER
    ) -> None:
        self.spins: int = coerce_steps(spins, "spins", MAX_SPINS)
        super().__init__(self.spins, coerce_stagger(stagger))
        self.min_frames: int = pace_floor(self.spins, self.stagger)
        self._reels: list[Reel] = []

    def _schedule(self, board: Board) -> list[float]:
        stops = [1.0 - self.stagger + st for st in super()._schedule(board)]
        reels: list[Reel] = []
        for flap, stop in zip(board.flaps, stops, strict=True):
            if flap.static:
                a = flap.seq[0]  # never painted via the strip
                assert a is not None  # static: an unchanged character
                reels.append(Reel(stop, 1, flap.seq, a.slot, a.width, a.slot, a.width))
                continue
            k = reel_advances(self.spins, stop, self.stagger)
            first, last = flap.seq[0], flap.seq[-1]
            # a blank end is a zero-width slit centred on the other end's column
            if first is not None:
                x0, w0 = first.slot, first.width
            else:
                assert last is not None  # a flap has a real end
                x0, w0 = last.slot + last.width // 2, 0
            if last is not None:
                x1, w1 = last.slot, last.width
            else:
                assert first is not None
                x1, w1 = first.slot + first.width // 2, 0
            reels.append(Reel(stop, k, strip_symbols(flap.seq, k), x0, w0, x1, w1))
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
            window = reel_window(reel.x0, reel.w0, reel.x1, reel.w1, glide(u))
            paint_reel(set_px, reel.strip, band, d, shade_for(u), w, h, window)
        paint_pixels(set_px, board.ring_out if first_half else board.ring_in)


class SlotsReverse(Slots):
    """Reels stop right -> left."""

    _order = "reverse"


class SlotsRandom(Slots):
    """Reels stop in a random order, fresh each firing."""

    _order = "random"


class SlotsAlternating(Cycling):
    """Cycles forward -> reverse, one per firing."""

    def __init__(
        self, spins: Any = DEFAULT_SPINS, stagger: Any = DEFAULT_STAGGER
    ) -> None:
        super().__init__([Slots(spins, stagger), SlotsReverse(spins, stagger)])
