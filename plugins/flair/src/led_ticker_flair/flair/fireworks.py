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
# burst's own [t_start, t_start + t_burst_dur) window. Widened from the
# original 0.3 to 0.35 (visual-punch fix, see CLAUDE.md) -- at ~5-7fps
# render-demo capture cadence a 0.3-wide launch window landed between
# rendered frames often enough that the traveling streak was invisible in
# spot-checked gifs; 0.35 gives the streak more wall-clock window to land
# on a captured tick without materially changing burst choreography (no
# open/bloom hole-radius test pins the exact boundary value).
_LAUNCH_OPEN_BOUNDARY = 0.35

# Spokes-per-burst range (spec, verbatim, asterisk rework): "10-14 spokes at
# seeded angles". Narrower and sparser than the old 16-32 rim-spark count --
# fewer, longer, individually-visible radial trails read as an exploding
# point; a denser count of 1-2px specks read as a ring/haze instead.
_MIN_SPOKES = 10
_MAX_SPOKES = 14


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

    ``color``: this burst's spoke/fill color, an ``(r, g, b)`` triple.

    ``spoke_angles``: seeded asterisk geometry — a tuple of
    ``(angle_deg, jitter_deg)`` pairs, one per spoke, evenly spaced around
    the circle (``360 / n``) with a per-spoke random jitter so the star
    doesn't look mechanically uniform. Count is seeded in ``[10, 14]``.
    Renders as radial trails (``_draw_spokes``), not a rim/ring — the field
    name predates that rework (was ``spark_angles``, one point per rim
    spark) but the seeded-angle geometry itself is unchanged and directly
    reused as spoke direction.
    """

    cx: float
    cy: float
    radius_max: float
    t_start: float
    t_burst_dur: float
    color: tuple[int, int, int]
    spoke_angles: tuple[tuple[float, float], ...]


def _spoke_angles(rng: random.Random) -> tuple[tuple[float, float], ...]:
    n = rng.randint(_MIN_SPOKES, _MAX_SPOKES)
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
    burst: x-jitter, y, radius_max, t_start, spoke count, then one jitter
    per spoke) — the same ``random.Random`` seed reproduces an identical
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
                spoke_angles=_spoke_angles(rng),
            )
        )
    return bursts


def burst_state(b: Burst, t: float, w: int, h: int) -> tuple[float, str]:
    """Live ``(radius, phase)`` for burst ``b`` at transition-wide ``t``.

    Phases, in order:

    - ``"waiting"``: ``t < b.t_start`` — burst hasn't started; radius 0.
    - ``"launch"``: local progress ``p = (t - b.t_start) / b.t_burst_dur``
      is in ``[0, _LAUNCH_OPEN_BOUNDARY)`` (0.35) — a streak travels but
      hasn't opened; radius 0.
    - ``"open"``: ``p`` in ``[_LAUNCH_OPEN_BOUNDARY, 1]`` — radius eases
      ``0 -> radius_max`` via ``1 - (1 - q) ** 2`` (ease-out), where ``q``
      re-normalizes ``p``'s ``[_LAUNCH_OPEN_BOUNDARY, 1]`` range to
      ``[0, 1]``.
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

# Launch-streak geometry (spec: "head pixel white-hot 2x2, tail 3-4px
# fading in the burst color"). Head rows render `_WHITE_HOT` at full
# brightness (no fade); tail rows below it fade the burst's own color to
# black. Total streak length (6) is unchanged from the pre-fix single
# fading-tail version -- only the head's color/brightness changed.
_LAUNCH_HEAD_LEN = 2
_LAUNCH_TAIL_LEN = 4

# --- Asterisk-burst tuning (spoke geometry / brightness) -------------------
# Design (James's PR #39 feedback): the expanding-ring-outline decoration
# read as a ripple, not an explosion. Replaced entirely with radial spoke
# trails flying outward from each burst's center -- a line of pixels per
# seeded angle, running from a tail (near the center) out to a head that
# rides just ahead of the black hole's current edge. `_draw_ring` and
# `_draw_sparks` (and their brightness-curve helper `_ease_brightness`) are
# gone; `_draw_spokes` is the sole decoration painter for the open/bloom
# phases now. Hole/complement mechanics (`_fill_burst_black`,
# `_blackout_complement`, `burst_state`'s radius formulas) are untouched --
# this is purely the decorative layer painted on top of them.

# Head offset ahead of the current hole radius, in px (spec: "r_head =
# current hole radius + 1..2px" -- heads ride just ahead of the black
# edge). The per-spoke value within this band is derived from that spoke's
# own already-seeded `jitter_deg` (see `_draw_spokes`), not a fresh rng
# draw, so the whole decoration stays a pure function of the plan.
_SPOKE_HEAD_OFFSET_MIN = 1.0
_SPOKE_HEAD_OFFSET_MAX = 2.0

# Trail length as a fraction of the spoke's own head radius (spec: "trail_len
# ~= 0.45 x r_head" -- short dense star early when r_head is small, long
# trails late as r_head grows with the hole).
_TRAIL_LEN_FRAC = 0.45

# Per-spoke trail-length variance, +/-15% (spec, verbatim) so the star
# isn't perfectly geometric. Derived from the same seeded `jitter_deg` as
# the head offset above (no new rng draws).
_TRAIL_LEN_VARIANCE = 0.15

# Outermost span of a spoke that renders white-hot regardless of the
# burst's own color (spec: "head = white-hot for the outermost 1-2px").
_SPOKE_WHITE_HOT_PX = 1.5
_WHITE_HOT = (255, 255, 255)

# Along-spoke brightness floor at the tail end (spec: "dimming linearly to
# ~25% at the tail").
_TAIL_BRIGHTNESS_FLOOR = 0.25

# Bloom-phase global dimming floor (spec, verbatim): "scale everything
# additionally by max(0.25, 1 - (t - 0.5) x 2)" -- applied on top of the
# along-spoke gradient above, not in place of it.
_BLOOM_FADE_FLOOR = 0.25


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
                    # No bloom-fade multiplier yet (t < 0.5) -- the
                    # along-spoke gradient alone carries the open phase.
                    self._draw_spokes(real, b, radius, 1.0, w, h)
        else:
            incoming.draw(canvas, cursor_pos=0)
            self._blackout_complement(real, w, h, t)
            bloom_mult = self._bloom_multiplier(t)
            for b in self._plan:
                radius, _phase = burst_state(b, t, w, h)
                self._draw_spokes(real, b, radius, bloom_mult, w, h)

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
        ``(b.cx, b.cy)`` as ``p`` runs ``0 -> _LAUNCH_OPEN_BOUNDARY`` (the
        launch window) -- a white-hot ``_LAUNCH_HEAD_LEN``-row head at the
        leading (topmost) edge, full brightness/no fade (the "this is the
        hot tip of a rocket" read), followed by a ``_LAUNCH_TAIL_LEN``-row
        tail in the burst's own color fading toward black, trailing below
        it toward the bottom the streak launched from.
        """
        frac = min(1.0, max(0.0, p / _LAUNCH_OPEN_BOUNDARY))
        head_y = (h - 1) - frac * ((h - 1) - b.cy)
        x0 = int(b.cx)
        r0, g0, bl0 = b.color
        total_len = _LAUNCH_HEAD_LEN + _LAUNCH_TAIL_LEN
        for dy in range(total_len):
            y = round(head_y) + dy
            if y < 0 or y >= h:
                continue
            if dy < _LAUNCH_HEAD_LEN:
                r, g, bl = _WHITE_HOT
            else:
                tail_idx = dy - _LAUNCH_HEAD_LEN
                fade = max(0.0, 1.0 - tail_idx / _LAUNCH_TAIL_LEN)
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
    def _bloom_multiplier(t: float) -> float:
        """Global bloom-phase dimming multiplier (spec, verbatim):
        ``max(0.25, 1 - (t - 0.5) * 2)``. ``1.0`` for any ``t`` before the
        bloom handoff (``_BLOOM_AT``) -- the open phase carries its own
        brightness entirely via the along-spoke gradient in
        ``_draw_spokes``, with no additional time-based dimming. Once
        bloom starts this multiplier is applied ON TOP of that gradient
        (scaling the whole spoke, head included) so spokes fade out
        together as the bloom races toward full-panel coverage, floored at
        ``_BLOOM_FADE_FLOOR`` rather than fading to black before the snap.
        """
        if t < _BLOOM_AT:
            return 1.0
        return max(_BLOOM_FADE_FLOOR, 1.0 - (t - _BLOOM_AT) * 2.0)

    @staticmethod
    def _draw_spokes(
        real: Any, b: Burst, radius: float, brightness_mult: float, w: int, h: int
    ) -> None:
        """Paint ``b``'s asterisk: one radial trail per seeded
        ``(angle_deg, jitter_deg)`` pair in ``b.spoke_angles``, each a line
        of pixels from a tail near the center out to a head riding just
        ahead of the current hole edge -- the "point exploding outward"
        read (PR #39 feedback replaced the old expanding-ring-outline
        decoration, which read as a ripple, with this).

        Per spoke: ``r_head = radius + head_offset`` (``head_offset`` in
        ``[_SPOKE_HEAD_OFFSET_MIN, _SPOKE_HEAD_OFFSET_MAX]``, i.e. 1-2px
        ahead of the black hole's own edge) and
        ``r_tail = max(0, r_head - trail_len)`` where
        ``trail_len = _TRAIL_LEN_FRAC * r_head * variance`` (``variance``
        in ``[1 - _TRAIL_LEN_VARIANCE, 1 + _TRAIL_LEN_VARIANCE]``) -- since
        ``trail_len`` scales with ``r_head``, spokes are short near the
        center early (small hole -> short trail -> reads as a dense little
        star) and long once the hole has grown (large hole -> long trail).
        Both ``head_offset`` and ``variance`` are derived from that
        spoke's own already-seeded ``jitter_deg`` (normalized against its
        angular slice, same trick ``_draw_sparks`` used to use for its
        radius jitter) -- no fresh rng draws, so the whole decoration stays
        a pure function of the already-committed plan and same-seed
        determinism is unaffected.

        Iteration is radial, 1px steps, angle computed once per spoke
        (``cos``/``sin``) then just stepping the radius -- cost is
        ``O(spokes * trail_len)`` per burst, trivially cheap at panel
        scale; off-panel pixels are skipped, never specially computed
        around.

        Brightness: the outermost ``_SPOKE_WHITE_HOT_PX`` px of a spoke
        render ``_WHITE_HOT`` regardless of ``b.color`` (the bright
        particle head); every pixel below that fades LINEARLY in the
        burst's own color from full brightness (just inside the white-hot
        span) down to ``_TAIL_BRIGHTNESS_FLOOR`` (25%) at the tail. The
        caller-supplied ``brightness_mult`` (1.0 during the open phase,
        ``_bloom_multiplier(t)`` during bloom) scales the WHOLE spoke,
        head included, on top of that gradient.
        """
        if radius <= 0.0 or brightness_mult <= 0.0:
            return
        n = len(b.spoke_angles)
        if n == 0:
            return
        step = 360.0 / n
        cx, cy = b.cx, b.cy
        r0, g0, bl0 = b.color

        for angle_deg, jitter_deg in b.spoke_angles:
            # jitter_deg in [-step/4, step/4] (see `_spoke_angles`) ->
            # normalize to [0, 1] to derive this spoke's deterministic
            # head-offset/trail-variance (no new rng draws).
            frac = min(1.0, max(0.0, (jitter_deg + step / 4.0) / (step / 2.0)))

            head_offset = _SPOKE_HEAD_OFFSET_MIN + frac * (
                _SPOKE_HEAD_OFFSET_MAX - _SPOKE_HEAD_OFFSET_MIN
            )
            r_head = radius + head_offset
            variance = 1.0 + (frac * 2.0 - 1.0) * _TRAIL_LEN_VARIANCE
            trail_len = max(0.5, _TRAIL_LEN_FRAC * r_head * variance)
            r_tail = max(0.0, r_head - trail_len)
            span = r_head - r_tail

            theta = math.radians(angle_deg + jitter_deg)
            cos_t, sin_t = math.cos(theta), math.sin(theta)

            steps = max(1, math.ceil(span))
            for i in range(steps + 1):
                r = min(r_head, r_tail + i)
                x = round(cx + r * cos_t)
                y = round(cy + r * sin_t)
                if not (0 <= x < w and 0 <= y < h):
                    continue

                if r_head - r <= _SPOKE_WHITE_HOT_PX:
                    base = _WHITE_HOT
                else:
                    along = (r - r_tail) / span if span > 0 else 1.0
                    fade = (
                        _TAIL_BRIGHTNESS_FLOOR + (1.0 - _TAIL_BRIGHTNESS_FLOOR) * along
                    )
                    base = (r0 * fade, g0 * fade, bl0 * fade)

                mult = brightness_mult
                real.SetPixel(
                    x, y, int(base[0] * mult), int(base[1] * mult), int(base[2] * mult)
                )

    def _blackout_complement(self, real: Any, w: int, h: int, t: float) -> None:
        """Blacken every pixel OUTSIDE the union of all bursts' current
        circles (the "not yet burned through" area), leaving the incoming
        widget's own already-drawn pixels showing wherever a burst has
        opened.

        Per-row interval-union algorithm: a circle intersects any given
        row ``y`` in AT MOST ONE contiguous x-interval --
        ``half = sqrt(r**2 - (y - cy)**2)`` when ``|y - cy| <= r``, giving
        ``[cx - half, cx + half]`` (clamped to ``[0, w)``). For each row,
        every currently-open burst contributes at most one such interval;
        sort them by start, merge overlaps, then ``SetPixel``-black only
        the GAPS (before the first merged interval, between merged
        intervals, after the last) -- ``O(h * n log n + black_pixels)``,
        i.e. cost scales with the ACTUAL black area rather than with
        bounding-box size. That area shrinks toward zero as bloom
        completes, so the old bytearray-mask "does a single burst's
        radius alone already cover the panel" short-circuit is no longer
        a special case: a row whose merged interval already spans the
        whole panel yields zero gap pixels for free out of the same loop
        that handles every other row, at the same ``O(n log n)`` cost.
        This also fixes the mask version's residual worst case -- several
        bursts jointly (but not individually) covering the panel used to
        still pay the full stamp-then-scan mask cost even though the
        final result was zero or near-zero black pixels (measured ~8ms
        dev / ~56ms projected Pi-5 at 512x64, mid-bloom, over the
        50ms/20fps budget); the per-row scan never builds a mask at all,
        so that case is now cheap too (measured ~1-2ms dev across the
        full sweep at 512x64 -- see ``CLAUDE.md``).
        """
        circles: list[tuple[float, float, float]] = []
        for b in self._plan or ():
            radius, _phase = burst_state(b, t, w, h)
            if radius > 0:
                circles.append((b.cx, b.cy, radius))

        for y in range(h):
            intervals: list[tuple[float, float]] = []
            for cx, cy, radius in circles:
                dy = y - cy
                if abs(dy) > radius:
                    continue
                half = math.sqrt(radius * radius - dy * dy)
                start = max(0.0, cx - half)
                end = min(float(w), cx + half)
                if start <= end:
                    intervals.append((start, end))

            if not intervals:
                # No open burst reaches this row at all -- the complement
                # is the whole row.
                for x in range(w):
                    real.SetPixel(x, y, 0, 0, 0)
                continue

            intervals.sort()
            merged: list[list[float]] = [list(intervals[0])]
            for start, end in intervals[1:]:
                if start <= merged[-1][1]:
                    merged[-1][1] = max(merged[-1][1], end)
                else:
                    merged.append([start, end])

            cursor = 0  # next pixel index that might still be a gap
            for start, end in merged:
                gap_hi = math.ceil(start) - 1
                if gap_hi >= cursor:
                    for x in range(cursor, min(gap_hi, w - 1) + 1):
                        real.SetPixel(x, y, 0, 0, 0)
                cursor = max(cursor, math.floor(end) + 1)
            if cursor <= w - 1:
                for x in range(cursor, w):
                    real.SetPixel(x, y, 0, 0, 0)
