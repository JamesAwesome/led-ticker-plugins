"""Sticker-bomb transition: pure math half (grid plan, pacing, dilation, rotation).

Spec: docs/superpowers/specs/2026-07-17-flair-stickers-transition-design.md
"""

import math
from dataclasses import dataclass

from led_ticker.plugin import ScaledCanvas, draw_emoji_at

GRID_OVERLAP = 0.7
JITTER_FRAC = 0.1
TILT_MAX_DEG = 10.0
BACKING_PAD = 1
OUTLINE_PAD = 2


@dataclass(frozen=True)
class Sticker:
    slug: str
    cx: int
    cy: int
    angle_deg: float
    arrive: int
    depart: int


def _smoothstep(p):
    p = min(1.0, max(0.0, p))
    return p * p * (3.0 - 2.0 * p)


def visible_count(t, n):
    """Stickers present during the build phase (t in [0, 0.5])."""
    return round(_smoothstep(t / 0.5) * n)


def departed_count(t, n):
    """Stickers already peeled during the peel phase (t in [0.5, 1])."""
    return round(_smoothstep((t - 0.5) / 0.5) * n)


def plan_stickers(panel_w, panel_h, footprint, slugs, rng):
    cell = max(1, int(footprint * GRID_OVERLAP))
    cols = math.ceil(panel_w / cell)
    rows = math.ceil(panel_h / cell)
    n = cols * rows
    arrive = list(range(n))
    rng.shuffle(arrive)
    depart = list(range(n))
    rng.shuffle(depart)
    out = []
    for i in range(n):
        gx, gy = i % cols, i // cols
        jx = rng.uniform(-JITTER_FRAC, JITTER_FRAC) * cell
        jy = rng.uniform(-JITTER_FRAC, JITTER_FRAC) * cell
        out.append(
            Sticker(
                slug=rng.choice(slugs),
                cx=round(gx * cell + cell / 2 + jx),
                cy=round(gy * cell + cell / 2 + jy),
                angle_deg=rng.uniform(-TILT_MAX_DEG, TILT_MAX_DEG),
                arrive=arrive[i],
                depart=depart[i],
            )
        )
    return out


def dilate(mask, radius):
    out = set()
    for x, y in mask:
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                out.add((x + dx, y + dy))
    return out


def rotate_pixels(pixels, angle_deg):
    """Rotate a {(x, y): (r, g, b)} pixel dict about its bbox center.

    INVERSE mapping (scan the destination, sample the source) — hole-free
    by construction. Plan-time only; per-frame paint iterates the result.
    """
    if not pixels or angle_deg == 0.0:
        return dict(pixels)
    a = math.radians(angle_deg)
    ca, sa = math.cos(a), math.sin(a)
    xs = [p[0] for p in pixels]
    ys = [p[1] for p in pixels]
    cx = (min(xs) + max(xs)) / 2.0
    cy = (min(ys) + max(ys)) / 2.0
    r = (max(xs) - min(xs)) + (max(ys) - min(ys)) + 2  # loose half-diagonal bound
    out = {}
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            sx = round(cx + dx * ca + dy * sa)
            sy = round(cy - dx * sa + dy * ca)
            c = pixels.get((sx, sy))
            if c is not None:
                out[(round(cx) + dx, round(cy) + dy)] = c
    return out


class _CaptureReal:
    """Recording stub real canvas: SetPixel into a dict; records EVERY call
    (a sprite may legitimately ink near-black pixels)."""

    def __init__(self, w, h):
        self.width = w
        self.height = h
        self.pixels = {}

    def SetPixel(self, x, y, r, g, b):
        self.pixels[(int(x), int(y))] = (int(r), int(g), int(b))

    def Clear(self):
        self.pixels.clear()


def _normalize(pixels):
    if not pixels:
        return {}
    minx = min(p[0] for p in pixels)
    miny = min(p[1] for p in pixels)
    return {(x - minx, y - miny): c for (x, y), c in pixels.items()}


def capture_sprite(slug, scale, content_height):
    """Rasterize a slug through the real draw path into a pixel dict.

    scale > 1 wraps the stub in the public ScaledCanvas so draw_emoji_at's
    hires dispatch fires; scale == 1 draws the 8x8 form directly. The result
    is bbox-normalized so placement math is anchor-independent.
    """
    if scale > 1:
        real = _CaptureReal(64 * scale, (content_height or 16) * scale)
        canvas = ScaledCanvas(real, scale=scale, content_height=content_height or 16)
    else:
        real = _CaptureReal(64, 16)
        canvas = real
    draw_emoji_at(canvas, slug, 4, 0)
    return _normalize(real.pixels)


def compose_sticker(sprite):
    """Die-cut: sprite ink over black fill (BACKING_PAD) + white rim
    (OUTLINE_PAD ring). Coverage comes from the fill+rim footprint."""
    mask = set(sprite)
    fill = dilate(mask, BACKING_PAD)
    rim = dilate(mask, OUTLINE_PAD) - fill
    out = {p: (0, 0, 0) for p in fill}
    out.update({p: (255, 255, 255) for p in rim})
    out.update(sprite)
    return out


class StickerRaster:
    """Per-run cache of composed, rotated stickers keyed by
    (slug, whole-degree angle, scale, content_height)."""

    def __init__(self):
        self._cache = {}

    def get(self, slug, angle_deg, scale, content_height):
        key = (slug, round(angle_deg), scale, content_height)
        hit = self._cache.get(key)
        if hit is None:
            sprite = capture_sprite(slug, scale, content_height)
            hit = rotate_pixels(compose_sticker(sprite), round(angle_deg))
            self._cache[key] = hit
        return hit
