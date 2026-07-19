"""flair.poker suit-ripple transition, pure-math half.

Spec: docs/superpowers/specs/2026-07-17-flair-poker-transition-design.md
Mask functions for the four card suits (hearts, diamonds, clubs, spades),
ring pixel-lists, and ring-union coverage test. No canvas, no led_ticker imports.
"""

import colorsys
import functools
import math
import random
from dataclasses import dataclass
from typing import Any

from led_ticker.plugin import SNAP_THRESHOLD, is_scaled, snap_reset, unwrap_to_real

SUITS = ("hearts", "diamonds", "clubs", "spades")

GRID = 32
GLYPH_R = 7.0
RING_W = 3.5
PULSES = 2.5


def _in_heart(x, y, r):
    # Two lobe circles + a wedge tapering to the bottom point (y down, so the
    # top of the heart is negative y). The classic implicit heart curve
    # ((x²+y²−1)³ ≤ x²y³) was replaced 2026-07-17: at LED sizes it rendered
    # near-rectangular with vertical sides and only a 1px top notch, reading
    # as a SHIELD rather than a heart (James's review of the poker GIF). This
    # form has rounded, clearly-separated lobes and curved sides at every
    # radius, and fits within `r` by construction (lobe tops reach 0.8r).
    if r <= 0:
        return False
    lr = 0.5 * r
    for cx in (-0.4 * r, 0.4 * r):
        if (x - cx) ** 2 + (y - (-0.3 * r)) ** 2 <= lr * lr:
            return True
    top_y, bot_y, top_hw = -0.3 * r, r, 0.9 * r
    if top_y <= y <= bot_y:
        return abs(x) <= top_hw * (bot_y - y) / (bot_y - top_y)
    return False


def _in_diamond(x, y, r):
    return r > 0 and abs(x) + abs(y) <= r


def _in_club(x, y, r):
    if r <= 0:
        return False
    lr = 0.45 * r
    for ang in (90, 210, 330):
        a = math.radians(ang)
        cx, cy = 0.5 * r * math.cos(a), -0.5 * r * math.sin(a)
        if (x - cx) ** 2 + (y - cy) ** 2 <= lr * lr:
            return True
    return abs(x) <= 0.16 * r and 0 <= y <= r


def _in_spade(x, y, r):
    if r <= 0:
        return False
    if _in_heart(x, -y * 0.95, r * 0.92):
        return True
    return abs(x) <= 0.16 * r and 0 <= y <= r


_MASKS = {
    "hearts": _in_heart,
    "diamonds": _in_diamond,
    "clubs": _in_club,
    "spades": _in_spade,
}


def inside(suit, dx, dy, r):
    return _MASKS[suit](dx, dy, r)


def interior_pixels(suit, r):
    m = _MASKS[suit]
    lim = int(math.ceil(r)) + 1
    return {
        (x, y) for y in range(-lim, lim + 1) for x in range(-lim, lim + 1) if m(x, y, r)
    }


def ring_pixels(suit, r, w=RING_W):
    return interior_pixels(suit, r) - interior_pixels(suit, r - w)


_STAGGER_MAX = 0.25
_INTRO_END = 0.25  # pulses begin after this fraction (+ per-glyph stagger)
_MAX_R_FACTOR = 1.45


@dataclass(frozen=True)
class Glyph:
    suit: str
    cx: int
    cy: int
    hue: float
    stagger: float


def max_radius(cell_w, cell_h):
    return _MAX_R_FACTOR * math.hypot(cell_w, cell_h)


def plan_glyphs(panel_w, panel_h, suits, rng):
    cols = max(1, math.ceil(panel_w / GRID))
    rows = max(1, math.ceil(panel_h / GRID))
    out = []
    for i in range(cols * rows):
        gx, gy = i % cols, i // cols
        out.append(
            Glyph(
                suit=suits[i % len(suits)],
                cx=round(gx * GRID + GRID / 2 + rng.uniform(-3, 3)),
                cy=round(gy * GRID + GRID / 2 + rng.uniform(-2, 2)),
                hue=rng.random(),
                stagger=rng.uniform(0.0, _STAGGER_MAX),
            )
        )
    return out


def pulse_radius(t, stagger):
    """(_radius_, wave_index) for the pulse active at global t, or None
    before this glyph's pulses begin. Radius is a FRACTION of max_r
    (0..1); the caller scales by its own max_radius."""
    start = _INTRO_END + stagger
    if t < start:
        return None
    p = (t - start) / (1.0 - start)  # 0..1 across the pulse window
    scaled = p * PULSES
    wave = int(scaled)
    phase = scaled - wave  # 0..1 within the current wave
    return phase, wave


# ---------------------------------------------------------------------------
# Process-wide suit GEOMETRY cache.
#
# ROOT CAUSE of the on-sign CPU spin (2026-07-18): ring geometry was cached
# per (suit, radius, HUE) — but hue varies per glyph, so 16 glyphs each
# re-rasterized the same suit shapes (~12.6M mask evals per bigsign firing,
# ~3 s dev / ~10 s Pi), and a seed-less transition re-paid the whole stall on
# EVERY firing. Geometry does not depend on hue AT ALL — only the painted
# color does. Rasterize each (suit, radius) ONCE PER PROCESS here; colorize
# cheaply downstream. `functools.cache` keys survive across firings and
# Poker instances, so only the first-ever firing in a process rasterizes.
# ---------------------------------------------------------------------------


@functools.cache
def _interior_geom(suit: str, r: float) -> tuple:
    """Process-wide interior (dx, dy) geometry at radius ``r``."""
    return tuple(interior_pixels(suit, r))


@functools.cache
def _ring_geom(suit: str, r_int: int) -> tuple:
    """Process-wide ring-shell (dx, dy) geometry at integer radius ``r_int``."""
    inner = frozenset(_interior_geom(suit, r_int - RING_W))
    return tuple(p for p in _interior_geom(suit, r_int) if p not in inner)


@functools.cache
def _warm_suit_geometry(suit: str, max_ri: int, glyph_ri: int) -> bool:
    """Rasterize every radius a transition can request for ``suit`` — once
    per process (the @cache makes repeat calls free)."""
    for rr in range(0, max_ri + 1):
        _ring_geom(suit, rr)
    for rr in range(0, glyph_ri + 1):
        _interior_geom(suit, rr)
    return True


@functools.cache
def _hue_color_deg(deg: int) -> tuple[int, int, int]:
    rr, gg, bb = colorsys.hsv_to_rgb((deg % 360) / 360.0, 1.0, 1.0)
    return (int(rr * 255), int(gg * 255), int(bb * 255))


def _hue_color(hue_deg: float) -> tuple[int, int, int]:
    """Hue (degrees, any range) -> RGB tuple, quantized to whole degrees so a
    continuously-cycling hue hits a bounded, process-cached key set. This is
    the ONLY colorize layer left: paint paths take one color per (glyph, ring)
    and iterate the process-cached `_ring_geom`/`_interior_geom` geometry
    directly. (The former ``RingCache`` colorized-pixel-list layer was removed
    with the per-firing absolute-coord memos — building those lists on first
    touch was itself a frame-time spike.)"""
    return _hue_color_deg(round(hue_deg))


_CUTOVER = 0.45  # t at which we cut from outgoing to washing the incoming in
_RING_HUE_STEP = 9.0  # degrees of hue per pixel of ring radius (rainbow ripple)
_GLYPH_SCALE_IN = 0.2  # fraction of t over which resting glyphs scale up


class Poker:
    """Card-suit ripple transition: filled rainbow suit glyphs pattern in over
    the outgoing widget, then emit suit-shaped rainbow ripple pulses that wash
    the incoming widget in against black. ``suits=[...]`` restricts the pool
    (default all four).

    The wash is driven by a reveal mask: once past ``_CUTOVER`` the union of
    every ring shell each glyph's pulse has swept is accumulated (filled, so it
    is gap-free at any frame cadence — a coarse 12-frame reveal phase on real
    hardware would otherwise leave concentric black annuli between sampled
    radii). A glyph that has completed one full pulse (``wave >= 1``) forces its
    reveal out to the full ``max_radius`` even if no frame sampled the outermost
    radius, so by ``SNAP_THRESHOLD`` every panel pixel is revealed."""

    min_frames = 24

    def __init__(self, suits: Any = None, seed: int | None = None) -> None:
        if suits is not None:
            if (
                not isinstance(suits, list)
                or not suits
                or not all(isinstance(s, str) and s for s in suits)
            ):
                raise ValueError(
                    f"suits must be a non-empty list of suit names; got {suits!r}"
                )
            unknown = sorted(set(suits) - set(SUITS))
            if unknown:
                raise ValueError(
                    f"unknown suit(s) {unknown!r}; valid: {list(SUITS)!r} "
                    "(hearts, diamonds, clubs, spades)"
                )
        self.suits = list(suits) if suits else list(SUITS)
        self.seed = seed
        self._rng = random.Random(seed) if seed is not None else random.Random()
        self._plan: list[Glyph] = []  # empty == needs (re)build
        self._plan_key: tuple[int, int, int] | None = None
        self._dims: tuple[int, int] = (0, 0)
        self._max_r: float = 0.0
        self._revealed: bytearray = bytearray()  # (w*h) reveal mask per firing
        self._reveal_r: list[int] = []  # per-glyph max integer radius unioned
        # Peel-phase complement as a SHRINKING set of (x, y) still-black pixels,
        # so the per-frame blackout iterates only what's actually black instead
        # of scanning all w*h pixels (the CPU sink on a Pi). Refilled per firing.
        self._unrevealed: set[tuple[int, int]] = set()
        self._last_t = 1.0

    def _ring_hue(self, g, r_int):
        return g.hue * 360.0 + r_int * _RING_HUE_STEP

    def _glyph_hue(self, g):
        return g.hue * 360.0

    def _reset_reveal(self):
        w, h = self._dims
        self._revealed = bytearray(w * h)
        self._reveal_r = [-1] * len(self._plan)
        # Rebuild the complement set once per firing (cheap vs a per-frame scan).
        self._unrevealed = {(x, y) for y in range(h) for x in range(w)}

    def _ensure_plan(self, canvas):
        # `real` is re-derived from `canvas` on EVERY call and never cached on
        # self: `frame.swap()` hands back a different back-buffer each tick
        # (constraint #1), so a cached real canvas would paint onto a stale,
        # no-longer-displayed buffer. Only geometry-derived data (dims, max_r,
        # the plan, the warmed pixel caches) is retained.
        scale = canvas.scale if is_scaled(canvas) else 1
        real = unwrap_to_real(canvas) if is_scaled(canvas) else canvas
        key = (real.width, real.height, scale)
        if not self._plan or self._plan_key != key:
            self._plan = plan_glyphs(real.width, real.height, self.suits, self._rng)
            self._plan_key = key
            self._dims = (real.width, real.height)
            self._max_r = max_radius(GRID, GRID)
            self._reset_reveal()
            # Warm the process-wide GEOMETRY for the suits in play — a no-op
            # after the first-ever firing in this process (functools.cache).
            # Paint/reveal paths iterate that geometry directly with one
            # hoisted color per (glyph, ring) — no per-firing list builds, so
            # every frame of every firing costs the same (the cutover-frame
            # memo-build spike read as a dropped frame on the Pi). See
            # TestNoPerFiringRasterization + TestNoCutoverBacklogSpike.
            max_ri = int(math.ceil(self._max_r))
            glyph_ri = int(math.ceil(GLYPH_R))
            for suit in {g.suit for g in self._plan}:
                _warm_suit_geometry(suit, max_ri, glyph_ri)
        return self._plan, real

    def _paint_current_rings(self, real, t):
        """SetPixel each glyph's live pulse-wavefront shell straight from the
        process-cached geometry: one color per (glyph, ring), inline coord-add
        + bounds check per pixel. No list building anywhere in the frame."""
        w, h = self._dims
        set_pixel = real.SetPixel
        for g in self._plan:
            pr = pulse_radius(t, g.stagger)
            if pr is None:
                continue
            phase, _wave = pr
            r_int = round(phase * self._max_r)
            if r_int <= 0:
                continue
            cr, cg, cb = _hue_color(self._ring_hue(g, r_int))
            cx, cy = g.cx, g.cy
            for dx, dy in _ring_geom(g.suit, r_int):
                x = cx + dx
                y = cy + dy
                if 0 <= x < w and 0 <= y < h:
                    set_pixel(x, y, cr, cg, cb)

    def _accumulate_reveal(self, t):
        """Union every ring shell up to each glyph's current radius into the
        reveal mask (filled, gap-free) and drop those pixels from the black
        complement. A completed pulse (``wave >= 1``) forces the reveal out to
        the full ``max_radius`` even if no frame sampled the outermost radius —
        the physical pulse did sweep it between frames.

        Called EVERY frame (build phase included), not just past ``_CUTOVER``:
        the mask isn't consumed before the peel, but maintaining it from pulse
        start spreads the union work to a couple of radii per glyph per frame.
        Deferring it all to the first peel frame was the 'explosion start'
        hitch (~40 rings x every glyph in one frame — 34 ms dev, a visibly
        dropped frame on the Pi). Reveal needs no color, so it walks the raw
        geometry."""
        w, h = self._dims
        max_ri = int(round(self._max_r))
        revealed = self._revealed
        unrevealed = self._unrevealed
        for i, g in enumerate(self._plan):
            pr = pulse_radius(t, g.stagger)
            if pr is None:
                continue
            phase, wave = pr
            target = max_ri if wave >= 1 else round(phase * self._max_r)
            prev = self._reveal_r[i]
            if target <= prev:
                continue
            cx, cy = g.cx, g.cy
            for rr in range(prev + 1, target + 1):
                for dx, dy in _ring_geom(g.suit, rr):
                    x = cx + dx
                    y = cy + dy
                    if 0 <= x < w and 0 <= y < h:
                        flat = y * w + x
                        if not revealed[flat]:
                            revealed[flat] = 1
                            unrevealed.discard((x, y))
            self._reveal_r[i] = target

    def _paint_glyphs(self, real, t):
        """Paint each glyph's resting FILLED suit body, scaling in over the
        first ``_GLYPH_SCALE_IN`` of the transition."""
        scale_in = min(1.0, t / _GLYPH_SCALE_IN)
        gr = int(round(GLYPH_R * scale_in))
        if gr <= 0:
            return
        w, h = self._dims
        set_pixel = real.SetPixel
        for g in self._plan:
            cr, cg, cb = _hue_color(self._glyph_hue(g))
            cx, cy = g.cx, g.cy
            for dx, dy in _interior_geom(g.suit, gr):
                x = cx + dx
                y = cy + dy
                if 0 <= x < w and 0 <= y < h:
                    set_pixel(x, y, cr, cg, cb)

    def frame_at(self, t, canvas, outgoing, incoming, **kwargs):
        if t <= 0.0:
            outgoing.draw(canvas, cursor_pos=kwargs.get("outgoing_scroll_pos", 0))
            return canvas
        if t >= SNAP_THRESHOLD:
            snap_reset(canvas, kwargs.get("incoming_bg_color"))
            incoming.draw(canvas, cursor_pos=0)
            self._last_t = 1.0
            return canvas

        refired = t < self._last_t
        if refired and self.seed is None:
            self._plan = []  # re-fire from fresh entropy (empty == rebuild)
            self._plan_key = None
            self._rng = random.Random()
        self._last_t = t

        plan, real = self._ensure_plan(canvas)
        if refired:
            self._reset_reveal()  # each firing washes in from scratch
        # Maintain the reveal mask from pulse start (see _accumulate_reveal) —
        # in the build phase it's bookkeeping only, nothing reads it yet.
        self._accumulate_reveal(t)

        if t < _CUTOVER:
            outgoing.draw(canvas, cursor_pos=kwargs.get("outgoing_scroll_pos", 0))
            self._paint_glyphs(real, t)
            self._paint_current_rings(real, t)
        else:
            snap_reset(canvas, kwargs.get("incoming_bg_color"))
            incoming.draw(canvas, cursor_pos=0)
            # Black only the still-unrevealed complement (a shrinking set) rather
            # than scanning all w*h pixels every frame.
            set_pixel = real.SetPixel
            for x, y in self._unrevealed:
                set_pixel(x, y, 0, 0, 0)
            self._paint_current_rings(real, t)
        return canvas
