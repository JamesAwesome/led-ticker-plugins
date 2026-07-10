"""flair.fireworks — pure burst plan + geometry (Task 1, no widget/transition
class yet). The eventual transition (Task 2) is a two-phase design: sparse,
staggered bursts launch and open over the outgoing widget first (so it reads
as fireworks, not a wipe), then every burst's radius blooms in lockstep
toward full-panel coverage in the second half of the transition, painting
the whole canvas through black before the incoming widget snaps in at
``SNAP_THRESHOLD`` — guaranteeing complete coverage regardless of how any
individual burst was staggered. Everything in this module is pure math: no
widget-lifecycle concerns, no canvas access, no core imports (stdlib only).
"""

import math
import random
from dataclasses import dataclass

# The 8 spec auto-palette colors, in spec order (red, green, amber, blue,
# magenta, cyan, orange, violet). Deliberately duplicated from
# ``lottery.PALETTE`` (see that module) rather than imported — each pure
# module in this package owns its own copy of the spec constant so Task 1
# stays a stdlib-only, zero-sibling-import section.
PALETTE: tuple[tuple[int, int, int], ...] = (
    (255, 60, 60),  # red
    (60, 220, 60),  # green
    (255, 180, 0),  # amber
    (80, 140, 255),  # blue
    (255, 80, 255),  # magenta
    (0, 220, 220),  # cyan
    (255, 120, 40),  # orange
    (170, 90, 255),  # violet
)

# Burst count clamp bounds (spec, verbatim).
_MIN_BURSTS = 3
_MAX_BURSTS = 6

# Per-burst radius_max band, as a fraction of panel height (spec, verbatim).
_RADIUS_MIN_FRAC = 0.55
_RADIUS_MAX_FRAC = 0.85

# Stagger window for a burst's t_start, in overall transition-t units (spec,
# verbatim).
_STAGGER_MIN = 0.05
_STAGGER_MAX = 0.45

# Global t at which every burst enters the "bloom" phase, regardless of its
# own t_start/local progress (spec, verbatim).
_BLOOM_AT = 0.5

# Local-progress (p) boundary between "launch" (radius pinned at 0, a
# traveling streak) and "open" (radius eases 0 -> radius_max) within a
# burst's own [t_start, t_start + t_burst_dur) window (spec, verbatim).
_LAUNCH_OPEN_BOUNDARY = 0.3

# Sparks-per-rim range (spec, verbatim): "rims 16-32 sparks, seeded jitter".
_MIN_SPARKS = 16
_MAX_SPARKS = 32


def burst_count(w: int, h: int) -> int:
    """Spec rule: ``clamp(round(w / max(h, 32)), 3, 6)``.

    Pinned: smallsign (160x16) -> 5, bigsign (256x64) -> 4, longboi
    (512x64) -> 6.
    """
    raw = round(w / max(h, 32))
    return max(_MIN_BURSTS, min(_MAX_BURSTS, raw))


@dataclass(frozen=True, slots=True)
class Burst:
    """One firework burst's fixed plan (everything decided up front at
    ``plan_bursts`` time; ``burst_state`` reads these fields plus a
    transition-wide ``t`` to compute the burst's live radius/phase — no
    mutation, no per-tick state).

    ``cx``/``cy``: burst center, LOGICAL panel coordinates (the eventual
    widget draws at whatever resolution the canvas is; this module is
    resolution-agnostic and just works in the same unit space ``w``/``h``
    are given in).

    ``radius_max``: the radius the burst's own "open" phase eases toward,
    seeded in ``[0.55, 0.85] * h`` — the "bloom" phase (see ``burst_state``)
    grows past this toward full coverage.

    ``t_start``: the transition-wide ``t`` this burst's own timeline
    begins at, staggered in ``[0.05, 0.45]``.

    ``t_burst_dur``: length (in transition-``t`` units) of this burst's own
    launch+open window, i.e. its timeline spans
    ``[t_start, t_start + t_burst_dur)``. ``plan_bursts`` sets this to
    ``_BLOOM_AT - t_start`` so every burst finishes its own "open" phase
    (reaching exactly ``radius_max``) right as the global "bloom" phase
    begins at ``t == 0.5`` — the two phases hand off continuously with no
    radius jump.

    ``color``: this burst's spark/fill color, an ``(r, g, b)`` triple.

    ``spark_angles``: seeded rim geometry — a tuple of
    ``(angle_deg, jitter_deg)`` pairs, one per spark, evenly spaced around
    the circle (``360 / n``) with a per-spark random jitter so the rim
    doesn't look mechanically uniform. Count is seeded in ``[16, 32]``.
    """

    cx: float
    cy: float
    radius_max: float
    t_start: float
    t_burst_dur: float
    color: tuple[int, int, int]
    spark_angles: tuple[tuple[float, float], ...]


def _spark_angles(rng: random.Random) -> tuple[tuple[float, float], ...]:
    n = rng.randint(_MIN_SPARKS, _MAX_SPARKS)
    step = 360.0 / n
    return tuple((i * step, rng.uniform(-step / 4.0, step / 4.0)) for i in range(n))


def plan_bursts(
    w: int,
    h: int,
    rng: random.Random,
    count: int | None = None,
    colors: list[tuple[int, int, int]] | None = None,
) -> list[Burst]:
    """Plan ``count`` (default: ``burst_count(w, h)``) bursts.

    Determinism: all randomness is drawn from ``rng`` in a fixed order (per
    burst: x-jitter, y, radius_max, t_start, spark count, then one jitter
    per spark) — the same ``random.Random`` seed reproduces an identical
    plan.

    Centers: the panel width is divided into ``count`` equal horizontal
    bands and burst ``i`` is jittered within band ``i`` (so bursts spread
    across the panel rather than clustering); ``cy`` is seeded in the upper
    two-thirds of the panel (fireworks read top-heavy; the bottom third is
    reserved for the launch streak's travel, a Task 2 rendering concern).

    ``colors``: cycled in order across bursts when given (``colors[i %
    len(colors)]``); defaults to cycling ``PALETTE``.
    """
    if not isinstance(count, int | type(None)) or isinstance(count, bool):
        raise ValueError(f"count must be an int or None; got {count!r}")
    n = burst_count(w, h) if count is None else count
    if n < 1:
        raise ValueError(f"count must be >= 1; got {n!r}")

    palette = colors if colors else list(PALETTE)
    band_w = w / n

    bursts = []
    for i in range(n):
        band_start = i * band_w
        cx = band_start + rng.uniform(0.2, 0.8) * band_w
        cy = rng.uniform(0.05, 2.0 / 3.0) * h
        radius_max = rng.uniform(_RADIUS_MIN_FRAC, _RADIUS_MAX_FRAC) * h
        t_start = rng.uniform(_STAGGER_MIN, _STAGGER_MAX)
        t_burst_dur = _BLOOM_AT - t_start
        raw_color = palette[i % len(palette)]
        color = (raw_color[0], raw_color[1], raw_color[2])
        bursts.append(
            Burst(
                cx=cx,
                cy=cy,
                radius_max=radius_max,
                t_start=t_start,
                t_burst_dur=t_burst_dur,
                color=color,
                spark_angles=_spark_angles(rng),
            )
        )
    return bursts


def burst_state(b: Burst, t: float, w: int, h: int) -> tuple[float, str]:
    """Live ``(radius, phase)`` for burst ``b`` at transition-wide ``t``.

    Phases, in order:

    - ``"waiting"``: ``t < b.t_start`` — burst hasn't started; radius 0.
    - ``"launch"``: local progress ``p = (t - b.t_start) / b.t_burst_dur``
      is in ``[0, 0.3)`` — a streak travels but hasn't opened; radius 0.
    - ``"open"``: ``p`` in ``[0.3, 1]`` — radius eases
      ``0 -> radius_max`` via ``1 - (1 - q) ** 2`` (ease-out), where ``q``
      re-normalizes ``p``'s ``[0.3, 1]`` range to ``[0, 1]``.
    - ``"bloom"``: ``t >= 0.5`` (GLOBAL, overrides the burst's own local
      phase for every burst at once) — radius grows LINEARLY from
      ``radius_max`` (guaranteed by ``t_burst_dur``'s construction: every
      burst's "open" phase completes exactly as bloom begins) toward
      ``hypot(w, h)`` at ``t == 1.0``, guaranteeing full-panel coverage
      regardless of any individual burst's stagger.
    """
    if t >= _BLOOM_AT:
        frac = (t - _BLOOM_AT) / (1.0 - _BLOOM_AT)
        target = math.hypot(w, h)
        radius = b.radius_max + frac * (target - b.radius_max)
        return radius, "bloom"

    if t < b.t_start:
        return 0.0, "waiting"

    p = (t - b.t_start) / b.t_burst_dur
    if p < _LAUNCH_OPEN_BOUNDARY:
        return 0.0, "launch"

    q = min(1.0, (p - _LAUNCH_OPEN_BOUNDARY) / (1.0 - _LAUNCH_OPEN_BOUNDARY))
    radius = b.radius_max * (1.0 - (1.0 - q) ** 2)
    return radius, "open"
