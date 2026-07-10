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
from typing import Any

from led_ticker.plugin import SNAP_THRESHOLD, snap_reset, unwrap_to_real

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


# ---------------------------------------------------------------------------
# Fireworks transition (Task 2)
# ---------------------------------------------------------------------------

# ``bursts=`` ctor override bound (spec, verbatim): "bursts override valid
# 2-8". Deliberately tighter than `plan_bursts`'s own 3-6 auto-pick clamp —
# an explicit override is allowed a wider manual range; `plan_bursts` itself
# does not enforce this (it accepts any `count >= 1`), so the ctor is the
# sole enforcement point.
_MIN_BURSTS_OVERRIDE = 2
_MAX_BURSTS_OVERRIDE = 8

# Launch-streak tail length, in rows, behind the traveling head (spec:
# "bright head + fading tail").
_LAUNCH_TAIL_LEN = 6


class Fireworks:
    """The outgoing widget holds while staggered firework bursts launch,
    open, and fade over it (``t < 0.5``); every burst's radius then blooms
    in lockstep toward full-panel coverage (``t >= 0.5``), painting a
    complement-blackout around each expanding circle so the incoming
    widget is revealed exactly inside the union of all burst circles —
    guaranteeing complete coverage by ``t == 1.0`` regardless of any
    individual burst's stagger. See ``plan_bursts``/``burst_state`` above
    for the pure geometry this class renders; this class owns only the
    canvas-painting and per-firing lifecycle (lazy plan, re-fire, snap).

    All burst geometry (``Burst.cx``/``cy``/``radius_max``) is in REAL
    (physical) pixel space — bursts paint directly onto
    ``unwrap_to_real(canvas)``, bypassing any ``ScaledCanvas`` block
    expansion (the same hi-res-paint design as inline hi-res emoji /
    ``flair.lottery``'s ball faces), so a burst renders at full panel
    grain on a scaled (bigsign) canvas rather than a blocky
    scale-sized-square approximation.
    """

    min_frames = 24

    def __init__(
        self,
        bursts: int | None = None,
        colors: Any = None,
        seed: int | None = None,
    ) -> None:
        """``seed``: explicit seed = reproducible across fresh instances; a
        re-fire of the SAME instance continues the rng (bursts vary per
        firing). Two fresh instances constructed with the same explicit
        ``seed`` plan an IDENTICAL first firing (the rng starts from the
        same state); firing either instance a second time draws further
        from that same rng stream, so the second firing's plan differs from
        the first even though the seed never changes -- reproducibility is
        per-instance-per-firing, not "this seed always plans this exact
        sequence forever". ``seed=None`` (default) seeds from OS entropy
        per instance AND reseeds on every re-fire (see the re-fire branch in
        ``frame_at``), so repeated firings vary at runtime either way.
        """
        if bursts is not None:
            bad_bursts = not isinstance(bursts, int) or isinstance(bursts, bool)
            if bad_bursts or not (
                _MIN_BURSTS_OVERRIDE <= bursts <= _MAX_BURSTS_OVERRIDE
            ):
                raise ValueError(
                    "bursts must be an int in "
                    f"[{_MIN_BURSTS_OVERRIDE}, {_MAX_BURSTS_OVERRIDE}] or None; "
                    f"got {bursts!r}"
                )

        resolved_colors: list[tuple[int, int, int]] | None = None
        if colors is not None:
            if not isinstance(colors, list) or not colors:
                raise ValueError(
                    "colors must be a non-empty list of [r, g, b] triples; "
                    f"got {colors!r}"
                )
            resolved_colors = []
            for entry in colors:
                if not (
                    isinstance(entry, list | tuple)
                    and len(entry) == 3
                    and all(
                        isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 255
                        for v in entry
                    )
                ):
                    raise ValueError(
                        f"colors entry {entry!r} must be an [r, g, b] triple "
                        "of ints 0-255"
                    )
                resolved_colors.append((entry[0], entry[1], entry[2]))

        self.bursts = bursts
        self.colors = resolved_colors
        self.seed = seed
        # `seed is None` -> a fresh `random.Random()` per instance/re-fire
        # (OS-entropy seeded, so repeated firings vary at runtime); an
        # explicit `seed` is fixed for the lifetime of the instance (tests
        # only reseed the entropy case on re-fire, see `frame_at`).
        self._rng = random.Random(seed) if seed is not None else random.Random()
        self._plan: list[Burst] | None = None
        self._plan_dims: tuple[int, int] | None = None
        self._last_t = 1.0  # re-fire detection (Spinout precedent)

    def frame_at(
        self, t: float, canvas: Any, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Any:
        if t <= 0.0:
            outgoing.draw(canvas, cursor_pos=kwargs.get("outgoing_scroll_pos", 0))
            return canvas

        if t >= SNAP_THRESHOLD:
            snap_reset(canvas, kwargs.get("incoming_bg_color"))
            incoming.draw(canvas, cursor_pos=0)
            self._last_t = 1.0
            return canvas

        # Re-fire: a new sweep started (t dropped below the previous call's
        # t) -> drop the stale plan so it gets rebuilt below, and (only
        # when the caller didn't pin a seed) reseed from fresh entropy so
        # each firing looks different. `_last_t` starts at 1.0 so the
        # FIRST ever call (any t < 1.0) also takes this branch — harmless,
        # since `_plan` is already `None` at that point.
        if t < self._last_t:
            self._plan = None
            if self.seed is None:
                self._rng = random.Random()
        self._last_t = t

        real = unwrap_to_real(canvas)
        dims = (real.width, real.height)
        if self._plan is None or self._plan_dims != dims:
            self._plan = plan_bursts(
                dims[0], dims[1], self._rng, count=self.bursts, colors=self.colors
            )
            self._plan_dims = dims

        w, h = dims
        if t < _BLOOM_AT:
            outgoing.draw(canvas, cursor_pos=kwargs.get("outgoing_scroll_pos", 0))
            for b in self._plan:
                p = self._progress(b, t)
                if p is None:
                    continue  # "waiting" -- burst hasn't started yet
                if p < _LAUNCH_OPEN_BOUNDARY:
                    self._draw_launch_streak(real, b, p, w, h)
                else:
                    radius, _phase = burst_state(b, t, w, h)
                    self._fill_burst_black(real, b, radius, w, h)
                    self._draw_rim(real, b, radius, max(0.0, 1.0 - p), w, h)
        else:
            incoming.draw(canvas, cursor_pos=0)
            self._blackout_complement(real, w, h, t)
            brightness = min(1.0, max(0.0, (1.0 - t) * 2.0))
            for b in self._plan:
                radius, _phase = burst_state(b, t, w, h)
                self._draw_rim(real, b, radius, brightness, w, h)

        return canvas

    @staticmethod
    def _progress(b: Burst, t: float) -> float | None:
        """Local progress ``p`` within burst ``b``'s own launch+open
        window, or ``None`` if ``t`` is still before ``b.t_start``
        ("waiting" -- not yet fired). Mirrors `burst_state`'s internal
        formula; kept separate because `burst_state` only reports
        ``(radius, phase)`` and the launch-streak render needs the raw
        ``p`` (to place the traveling head) that "launch" phase collapses
        away.
        """
        if t < b.t_start:
            return None
        return (t - b.t_start) / b.t_burst_dur

    @staticmethod
    def _draw_launch_streak(real: Any, b: Burst, p: float, w: int, h: int) -> None:
        """A 2px-wide column rising from the bottom edge toward
        ``(b.cx, b.cy)`` as ``p`` runs ``0 -> 0.3`` (the launch window) --
        bright head at the leading (topmost) edge, a fading tail trailing
        below it toward the bottom the streak launched from.
        """
        frac = min(1.0, max(0.0, p / _LAUNCH_OPEN_BOUNDARY))
        head_y = (h - 1) - frac * ((h - 1) - b.cy)
        x0 = int(b.cx)
        r0, g0, bl0 = b.color
        for dy in range(_LAUNCH_TAIL_LEN):
            y = round(head_y) + dy
            if y < 0 or y >= h:
                continue
            fade = max(0.0, 1.0 - dy / _LAUNCH_TAIL_LEN)
            r, g, bl = int(r0 * fade), int(g0 * fade), int(bl0 * fade)
            for x in (x0, x0 + 1):
                if 0 <= x < w:
                    real.SetPixel(x, y, r, g, bl)

    @staticmethod
    def _fill_burst_black(real: Any, b: Burst, radius: float, w: int, h: int) -> None:
        """Black out ``b``'s interior circle (its "burn-through" hole),
        bounding-box-looped -- ``dx**2 + dy**2 <= r**2`` per candidate
        pixel, never the full panel.
        """
        if radius <= 0:
            return
        cx, cy = b.cx, b.cy
        r2 = radius * radius
        x0 = max(0, math.floor(cx - radius))
        x1 = min(w - 1, math.ceil(cx + radius))
        y0 = max(0, math.floor(cy - radius))
        y1 = min(h - 1, math.ceil(cy + radius))
        for y in range(y0, y1 + 1):
            dy2 = (y - cy) ** 2
            for x in range(x0, x1 + 1):
                dx2 = (x - cx) ** 2
                if dx2 + dy2 <= r2:
                    real.SetPixel(x, y, 0, 0, 0)

    @staticmethod
    def _draw_rim(
        real: Any, b: Burst, radius: float, brightness: float, w: int, h: int
    ) -> None:
        """Paint ``b``'s spark rim: one pixel per ``(angle_deg,
        jitter_deg)`` pair in ``b.spark_angles``, positioned at the
        burst's current ``radius`` with the seeded per-spark jitter
        applied as an angular offset (the rim geometry `plan_bursts`
        already seeded -- see `Burst.spark_angles`), color scaled by
        ``brightness`` (the caller picks the phase-appropriate formula:
        ``1 - p`` while opening, ``(1 - t) * 2`` clamped during bloom).
        """
        if brightness <= 0.0 or radius <= 0.0:
            return
        r0, g0, bl0 = b.color
        r, g, bl = int(r0 * brightness), int(g0 * brightness), int(bl0 * brightness)
        for angle_deg, jitter_deg in b.spark_angles:
            theta = math.radians(angle_deg + jitter_deg)
            x = round(b.cx + radius * math.cos(theta))
            y = round(b.cy + radius * math.sin(theta))
            if 0 <= x < w and 0 <= y < h:
                real.SetPixel(x, y, r, g, bl)

    def _blackout_complement(self, real: Any, w: int, h: int, t: float) -> None:
        """Blacken every pixel OUTSIDE the union of all bursts' current
        circles (the "not yet burned through" area), leaving the incoming
        widget's own already-drawn pixels showing wherever a burst has
        opened. Builds one per-frame ``bytearray(w*h)`` union mask by
        stamping each burst's bounding box (cheap membership math, not a
        per-pixel-per-circle test), then does a SINGLE full-panel pass
        painting black where the mask is unset -- O(sum of bounding boxes
        + w*h), not O(bursts * w*h).

        Late-bloom perf short-circuit: deep in the "bloom" phase every
        burst's radius grows toward ``hypot(w, h)`` (see ``burst_state``),
        so late frames commonly have EVERY burst's clamped bbox spanning
        the whole panel -- the naive stamp-then-scan degrades to
        O(bursts * w * h) precisely when it matters most (measured ~9.7ms
        dev / ~68ms projected Pi-5 at 512x64, blowing the ~50ms/20fps
        frame budget). Before stamping a burst, check whether its radius
        alone already proves TOTAL coverage: a circle covers a whole
        rectangle iff its radius reaches the rectangle's farthest corner
        from the circle's center (the max-distance point from any fixed
        center to a convex rectangle is always a corner). When that holds,
        the union of ALL bursts (this one plus any others) is provably
        total -- every pixel is revealed -- so we skip the mask (and any
        remaining bursts) entirely and paint no complement black this
        frame, rather than building a full-panel mask just to discover
        every pixel is set.
        """
        mask: bytearray | None = None
        for b in self._plan or ():
            radius, _phase = burst_state(b, t, w, h)
            if radius <= 0:
                continue
            cx, cy = b.cx, b.cy
            r2 = radius * radius
            x0 = max(0, math.floor(cx - radius))
            x1 = min(w - 1, math.ceil(cx + radius))
            y0 = max(0, math.floor(cy - radius))
            y1 = min(h - 1, math.ceil(cy + radius))

            if x0 == 0 and y0 == 0 and x1 == w - 1 and y1 == h - 1:
                dx = max(cx, (w - 1) - cx)
                dy = max(cy, (h - 1) - cy)
                if r2 >= dx * dx + dy * dy:
                    # This single burst's circle already covers the entire
                    # panel -- the union is total. Nothing to blacken, and
                    # no point examining the remaining bursts.
                    return

            if mask is None:
                mask = bytearray(w * h)
            for y in range(y0, y1 + 1):
                dy2 = (y - cy) ** 2
                row = y * w
                for x in range(x0, x1 + 1):
                    dx2 = (x - cx) ** 2
                    if dx2 + dy2 <= r2:
                        mask[row + x] = 1

        if mask is None:
            # No burst has opened at all this frame -- the complement is
            # the whole panel (same result the all-zero mask below would
            # have produced; skips allocating it).
            mask = bytearray(w * h)

        for y in range(h):
            row = y * w
            for x in range(w):
                if mask[row + x] == 0:
                    real.SetPixel(x, y, 0, 0, 0)
