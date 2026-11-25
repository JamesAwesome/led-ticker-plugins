"""flair.slots — each character spins vertically like a slot-machine reel,
decelerates, overshoots about a row and settles on the incoming character.

Design in one breath: every reel starts on the first frame and stops one
after another (``reel_stop`` ripples the stop times); a reel's per-frame
position is a pure function of its local timeline ``u`` in [0, 1] — a
trapezoid speed profile (ramp up, cruise, ramp down) integrated into
``displacement``, then a sine overshoot-and-settle past the landing row.
"""

import math

from ._board_transition import flap_start
from .slots_paint import SPIN_SHADE

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
