"""flair.poker suit-ripple transition, pure-math half.

Spec: docs/superpowers/specs/2026-07-17-flair-poker-transition-design.md
Mask functions for the four card suits (hearts, diamonds, clubs, spades),
ring pixel-lists, and ring-union coverage test. No canvas, no led_ticker imports.
"""

import colorsys
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


class RingCache:
    """Per-run cache of (x, y, color) pixel lists for both ring SHELLS (the
    moving pulse wavefront) and FILLED interiors (the resting suit glyphs).
    Both quantize hue to whole degrees so a continuously-cycling hue still
    hits a bounded key set (pre-warmed once per plan)."""

    def __init__(self):
        self._cache = {}
        self._interior_cache = {}

    @staticmethod
    def _color(hue_deg):
        rr, gg, bb = colorsys.hsv_to_rgb((round(hue_deg) % 360) / 360.0, 1.0, 1.0)
        return (int(rr * 255), int(gg * 255), int(bb * 255))

    def get(self, suit, r_int, hue_deg):
        key = (suit, int(r_int), round(hue_deg))
        hit = self._cache.get(key)
        if hit is None:
            color = self._color(hue_deg)
            hit = [(x, y, color) for (x, y) in ring_pixels(suit, int(r_int))]
            self._cache[key] = hit
        return hit

    def interior(self, suit, r_int, hue_deg):
        """Filled-suit pixel list (the resting glyph body)."""
        key = (suit, int(r_int), round(hue_deg))
        hit = self._interior_cache.get(key)
        if hit is None:
            color = self._color(hue_deg)
            hit = [(x, y, color) for (x, y) in interior_pixels(suit, int(r_int))]
            self._interior_cache[key] = hit
        return hit


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
        self._rings = RingCache()
        self._dims: tuple[int, int] = (0, 0)
        self._max_r: float = 0.0
        self._revealed: bytearray = bytearray()  # (w*h) reveal mask per firing
        self._reveal_r: list[int] = []  # per-glyph max integer radius unioned
        # Peel-phase complement as a SHRINKING set of (x, y) still-black pixels,
        # so the per-frame blackout iterates only what's actually black instead
        # of scanning all w*h pixels (the CPU sink on a Pi). Refilled per firing.
        self._unrevealed: set[tuple[int, int]] = set()
        # Per-firing memo of ABSOLUTE, pre-clipped pixel lists keyed by
        # (glyph_index, integer_radius). Glyph positions are fixed for a
        # firing, so a ring's on-panel (x, y, color) tuples (and its flat reveal
        # indices) are constant — compute the coord-add + bounds-clip ONCE and
        # blit thereafter, instead of re-deriving them every frame. Cleared when
        # the plan rebuilds (new dims / re-fire).
        self._ring_abs: dict[tuple[int, int], list[tuple[int, int, tuple]]] = {}
        self._ring_idx: dict[tuple[int, int], list[int]] = {}
        self._interior_abs: dict[tuple[int, int], list[tuple[int, int, tuple]]] = {}
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

    def _ring_abs_lists(self, gi, r_int):
        """Cached (paint-pixels, reveal-indices) for glyph ``gi``'s ring at
        integer radius ``r_int`` — absolute panel coords, pre-clipped. Computed
        once per (glyph, radius) and reused across frames."""
        key = (gi, r_int)
        px = self._ring_abs.get(key)
        if px is None:
            g = self._plan[gi]
            w, h = self._dims
            px = []
            idx = []
            for dx, dy, col in self._rings.get(g.suit, r_int, self._ring_hue(g, r_int)):
                x, y = g.cx + dx, g.cy + dy
                if 0 <= x < w and 0 <= y < h:
                    px.append((x, y, col))
                    idx.append(y * w + x)
            self._ring_abs[key] = px
            self._ring_idx[key] = idx
        return px, self._ring_idx[key]

    def _interior_abs_list(self, gi, gr):
        """Cached absolute pre-clipped interior pixels for glyph ``gi`` filled
        to radius ``gr``."""
        key = (gi, gr)
        px = self._interior_abs.get(key)
        if px is None:
            g = self._plan[gi]
            w, h = self._dims
            px = [
                (g.cx + dx, g.cy + dy, col)
                for dx, dy, col in self._rings.interior(g.suit, gr, self._glyph_hue(g))
                if 0 <= g.cx + dx < w and 0 <= g.cy + dy < h
            ]
            self._interior_abs[key] = px
        return px

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
            # Absolute-coord memos depend on glyph positions + dims — stale on a
            # rebuild.
            self._ring_abs.clear()
            self._ring_idx.clear()
            self._interior_abs.clear()
            self._reset_reveal()
            # Pre-warm every ring shell and interior the paint/reveal paths can
            # request (every glyph x every integer radius, at the exact hue the
            # paint path derives from that radius) so a warm plan does zero
            # rasterization per frame. See
            # TestPerf.test_no_ring_rasterization_after_first_frame.
            max_ri = int(math.ceil(self._max_r))
            glyph_ri = int(math.ceil(GLYPH_R))
            for g in self._plan:
                for rr in range(0, max_ri + 1):
                    self._rings.get(g.suit, rr, self._ring_hue(g, rr))
                for rr in range(0, glyph_ri + 1):
                    self._rings.interior(g.suit, rr, self._glyph_hue(g))
        return self._plan, real

    def _paint_current_rings(self, real, t):
        """SetPixel each glyph's live pulse-wavefront shell directly (from the
        cached absolute pixel list — no per-frame coord math or list building)."""
        set_pixel = real.SetPixel
        for gi, g in enumerate(self._plan):
            pr = pulse_radius(t, g.stagger)
            if pr is None:
                continue
            phase, _wave = pr
            r_int = round(phase * self._max_r)
            if r_int <= 0:
                continue
            px, _idx = self._ring_abs_lists(gi, r_int)
            for x, y, col in px:
                set_pixel(x, y, *col)

    def _accumulate_reveal(self, t):
        """Union every ring shell up to each glyph's current radius into the
        reveal mask (filled, gap-free) and drop those pixels from the black
        complement. A completed pulse (``wave >= 1``) forces the reveal out to
        the full ``max_radius`` even if no frame sampled the outermost radius —
        the physical pulse did sweep it between frames."""
        w = self._dims[0]
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
            for rr in range(prev + 1, target + 1):
                _px, idx = self._ring_abs_lists(i, rr)
                for flat in idx:
                    if not revealed[flat]:
                        revealed[flat] = 1
                        unrevealed.discard((flat % w, flat // w))
            self._reveal_r[i] = target

    def _paint_glyphs(self, real, t):
        """Paint each glyph's resting FILLED suit body, scaling in over the
        first ``_GLYPH_SCALE_IN`` of the transition."""
        scale_in = min(1.0, t / _GLYPH_SCALE_IN)
        gr = int(round(GLYPH_R * scale_in))
        if gr <= 0:
            return
        set_pixel = real.SetPixel
        for gi in range(len(self._plan)):
            for x, y, col in self._interior_abs_list(gi, gr):
                set_pixel(x, y, *col)

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
        w, h = self._dims

        if t < _CUTOVER:
            outgoing.draw(canvas, cursor_pos=kwargs.get("outgoing_scroll_pos", 0))
            self._paint_glyphs(real, t)
            self._paint_current_rings(real, t)
        else:
            snap_reset(canvas, kwargs.get("incoming_bg_color"))
            incoming.draw(canvas, cursor_pos=0)
            self._accumulate_reveal(t)
            # Black only the still-unrevealed complement (a shrinking set) rather
            # than scanning all w*h pixels every frame.
            set_pixel = real.SetPixel
            for x, y in self._unrevealed:
                set_pixel(x, y, 0, 0, 0)
            self._paint_current_rings(real, t)
        return canvas
