"""flair.poker suit-ripple transition, pure-math half.

Spec: docs/superpowers/specs/2026-07-10-flair-fireworks-transition-design.md
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
    if r <= 0:
        return False
    nx, ny = x / r, -y / r
    v = (nx * nx + ny * ny - 1) ** 3 - nx * nx * ny * ny * ny
    return v <= 0


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
        self._last_t = 1.0

    def _ring_hue(self, g, r_int):
        return g.hue * 360.0 + r_int * _RING_HUE_STEP

    def _glyph_hue(self, g):
        return g.hue * 360.0

    def _reset_reveal(self):
        w, h = self._dims
        self._revealed = bytearray(w * h)
        self._reveal_r = [-1] * len(self._plan)

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

    def _current_rings(self, t):
        """(x, y, color) shell pixels for each glyph's live pulse wavefront."""
        w, h = self._dims
        out = []
        for g in self._plan:
            pr = pulse_radius(t, g.stagger)
            if pr is None:
                continue
            phase, _wave = pr
            r_int = round(phase * self._max_r)
            if r_int <= 0:
                continue
            for dx, dy, col in self._rings.get(g.suit, r_int, self._ring_hue(g, r_int)):
                x, y = g.cx + dx, g.cy + dy
                if 0 <= x < w and 0 <= y < h:
                    out.append((x, y, col))
        return out

    def _accumulate_reveal(self, t):
        """Union every ring shell up to each glyph's current radius into the
        reveal mask (filled, gap-free). A completed pulse (``wave >= 1``) forces
        the reveal out to the full ``max_radius`` even if no frame sampled the
        outermost radius — the physical pulse did sweep it between frames."""
        w, h = self._dims
        max_ri = int(round(self._max_r))
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
                for dx, dy, _col in self._rings.get(g.suit, rr, self._ring_hue(g, rr)):
                    x, y = g.cx + dx, g.cy + dy
                    if 0 <= x < w and 0 <= y < h:
                        self._revealed[y * w + x] = 1
            self._reveal_r[i] = target

    def _paint_glyphs(self, real, t):
        """Paint each glyph's resting FILLED suit body, scaling in over the
        first ``_GLYPH_SCALE_IN`` of the transition."""
        w, h = self._dims
        scale_in = min(1.0, t / _GLYPH_SCALE_IN)
        gr = int(round(GLYPH_R * scale_in))
        if gr <= 0:
            return
        for g in self._plan:
            for dx, dy, col in self._rings.interior(g.suit, gr, self._glyph_hue(g)):
                x, y = g.cx + dx, g.cy + dy
                if 0 <= x < w and 0 <= y < h:
                    real.SetPixel(x, y, *col)

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
            for x, y, col in self._current_rings(t):
                real.SetPixel(x, y, *col)
        else:
            snap_reset(canvas, kwargs.get("incoming_bg_color"))
            incoming.draw(canvas, cursor_pos=0)
            self._accumulate_reveal(t)
            for y in range(h):
                base = y * w
                for x in range(w):
                    if not self._revealed[base + x]:
                        real.SetPixel(x, y, 0, 0, 0)
            for x, y, col in self._current_rings(t):
                real.SetPixel(x, y, *col)
        return canvas
