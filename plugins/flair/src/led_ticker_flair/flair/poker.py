"""flair.poker suit-ripple transition, pure-math half.

Spec: docs/superpowers/specs/2026-07-10-flair-fireworks-transition-design.md
Mask functions for the four card suits (hearts, diamonds, clubs, spades),
ring pixel-lists, and ring-union coverage test. No canvas, no led_ticker imports.
"""

import colorsys
import math
from dataclasses import dataclass

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
_MAX_R_FACTOR = 1.2


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
    def __init__(self):
        self._cache = {}

    def get(self, suit, r_int, hue_deg):
        key = (suit, int(r_int), round(hue_deg))
        hit = self._cache.get(key)
        if hit is None:
            rr, gg, bb = colorsys.hsv_to_rgb((round(hue_deg) % 360) / 360.0, 1.0, 1.0)
            color = (int(rr * 255), int(gg * 255), int(bb * 255))
            hit = [(x, y, color) for (x, y) in ring_pixels(suit, int(r_int))]
            self._cache[key] = hit
        return hit
