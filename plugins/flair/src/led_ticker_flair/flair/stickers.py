"""Sticker-bomb transition: pure math half (grid plan, pacing, dilation,
rotation; Tasks 1-2) and the ``Stickers`` transition class (Task 3).

Spec: docs/superpowers/specs/2026-07-17-flair-stickers-transition-design.md
"""

import math
import random
from dataclasses import dataclass
from typing import Any

from led_ticker.plugin import (
    SNAP_THRESHOLD,
    ScaledCanvas,
    draw_emoji_at,
    emoji_slugs,
    is_scaled,
    snap_reset,
    unwrap_to_real,
)

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


def compose_sticker(sprite, footprint=None):
    """Die-cut: sprite ink over a black backing + white rim (OUTLINE_PAD
    ring). Coverage comes from the backing+rim footprint.

    ``footprint=None`` (default): the backing follows the sprite's own
    silhouette, dilated by ``BACKING_PAD`` — a tight die-cut look. This is
    the shape used by callers that don't care about grid coverage (e.g. a
    standalone preview).

    ``footprint=<int>``: the backing is a solid SQUARE of that side length,
    centered on the sprite's own bbox center, rather than silhouette-shaped.
    ``plan_stickers``'s coverage guarantee is proved (see
    ``test_flair_stickers_plan.py::TestCoverage``) against an idealized
    inscribed-footprint-square model — a silhouette-following backing only
    matches that model for near-solid/near-square sprites. Concave shapes
    (a crescent moon) or markedly non-square bboxes (a wide-short taco)
    leave real gaps between grid cells that a 1-2px silhouette dilation
    can't close. Squaring the backing to the SAME ``footprint`` value the
    grid was sized from makes every composed sticker match the geometric
    model exactly, regardless of sprite shape — verified to reach exactly
    zero uncovered real pixels across 30 seeds, every core slug, and the
    full random-assortment pool, on both panel geometries (see the
    ``Stickers`` transition's ``TestEndpoints.test_full_cover_at_half``).
    """
    mask = set(sprite)
    if footprint is None:
        fill = dilate(mask, BACKING_PAD)
        rim = dilate(mask, OUTLINE_PAD) - fill
    else:
        xs = [p[0] for p in mask]
        ys = [p[1] for p in mask]
        cx = (min(xs) + max(xs)) / 2.0
        cy = (min(ys) + max(ys)) / 2.0
        half = footprint / 2.0
        lo_x, hi_x = round(cx - half), round(cx + half)
        lo_y, hi_y = round(cy - half), round(cy + half)
        fill = {(x, y) for x in range(lo_x, hi_x + 1) for y in range(lo_y, hi_y + 1)}
        rim = dilate(fill, OUTLINE_PAD) - fill
    out = {p: (0, 0, 0) for p in fill}
    out.update({p: (255, 255, 255) for p in rim})
    out.update(sprite)
    return out


class StickerRaster:
    """Per-run cache of composed, rotated stickers keyed by
    (slug, whole-degree angle, scale, content_height, footprint)."""

    def __init__(self):
        self._cache = {}

    def get(self, slug, angle_deg, scale, content_height, footprint=None):
        key = (slug, round(angle_deg), scale, content_height, footprint)
        hit = self._cache.get(key)
        if hit is None:
            sprite = capture_sprite(slug, scale, content_height)
            composed = compose_sticker(sprite, footprint)
            hit = rotate_pixels(composed, round(angle_deg))
            self._cache[key] = hit
        return hit


class Stickers:
    """Sticker-bomb: emoji pop on over the outgoing widget until full cover
    at t=0.5, then pop off in an independent random order revealing the
    incoming widget. `emoji=[...]` restricts the slug pool (one slug = a
    themed wall); omitted = random assortment across every drawable slug."""

    min_frames = 24

    def __init__(self, emoji: Any = None, seed: int | None = None) -> None:
        if emoji is not None:
            if (
                not isinstance(emoji, list)
                or not emoji
                or not all(isinstance(s, str) and s for s in emoji)
            ):
                raise ValueError(
                    f"emoji must be a non-empty list of slug strings; got {emoji!r}"
                )
            unknown = sorted(set(emoji) - set(emoji_slugs()))
            if unknown:
                raise ValueError(
                    f"unknown emoji slug(s) {unknown!r} — not in the drawable set. "
                    "Known slugs include taco, sun, moon, star, heart, pride, …"
                )
        self.emoji = list(emoji) if emoji else None
        self.seed = seed
        self._rng = random.Random(seed) if seed is not None else random.Random()
        self._plan = None
        self._plan_key = None
        self._raster = StickerRaster()
        self._last_t = 1.0

    def _ensure_plan(self, canvas):
        # `real`/`scale`/`content_height` are cheap attribute lookups and are
        # recomputed on EVERY call (mirroring Fireworks' `frame_at`, which
        # re-derives `real = unwrap_to_real(canvas)` fresh every frame): the
        # `canvas` object handed in on any given tick is very likely a
        # DIFFERENT back-buffer than the one the plan was built against
        # (constraint #1 — `frame.swap()` returns a different canvas each
        # call). Caching these alongside the plan (keyed only on dims/scale)
        # would silently keep painting onto a stale, no-longer-displayed
        # canvas on every tick after the first once the plan is reused.
        scale = canvas.scale if is_scaled(canvas) else 1
        content_height = canvas.content_height if is_scaled(canvas) else None
        real = unwrap_to_real(canvas) if is_scaled(canvas) else canvas
        key = (real.width, real.height, scale)
        if self._plan is None or self._plan_key != key:
            # Footprint from an actual capture (max bbox side + rim), not a
            # guess. Only done when (re)building the plan -- NOT on every
            # call -- so a warm plan costs zero rasterization per frame.
            pool = self.emoji if self.emoji else list(emoji_slugs())
            probe = capture_sprite(pool[0], scale, content_height)
            side = (
                1 + max(max(p[0] for p in probe), max(p[1] for p in probe))
                if probe
                else 8
            )
            footprint = side + 2 * OUTLINE_PAD
            self._plan = plan_stickers(
                real.width, real.height, footprint, pool, self._rng
            )
            self._plan_key = key
            self._footprint = footprint
            # Pre-warm the raster cache for every planned sticker (not just
            # the currently-visible subset) so the FIRST frame_at call after
            # a (re)plan does all rasterization/rotation work up front — a
            # per-tick loop that lazily rasterizes newly-ARRIVING stickers
            # during the build phase would blow the 50ms tick budget on
            # later frames too (each new arrival is a fresh, uncached
            # (slug, angle) combo). See
            # TestPerf.test_no_rasterization_after_first_frame.
            for s in self._plan:
                self._raster.get(s.slug, s.angle_deg, scale, content_height, footprint)
        return self._plan, scale, content_height, real

    def frame_at(self, t, canvas, outgoing, incoming, **kwargs):
        if t <= 0.0:
            outgoing.draw(canvas, cursor_pos=kwargs.get("outgoing_scroll_pos", 0))
            return canvas
        if t >= SNAP_THRESHOLD:
            snap_reset(canvas, kwargs.get("incoming_bg_color"))
            incoming.draw(canvas, cursor_pos=0)
            self._last_t = 1.0
            return canvas
        if t < self._last_t and self.seed is None:
            self._plan = None  # re-fire: replan from fresh entropy
            self._rng = random.Random()
        self._last_t = t

        plan, scale, content_height, real = self._ensure_plan(canvas)
        footprint = self._footprint
        n = len(plan)
        if t < 0.5:
            outgoing.draw(canvas, cursor_pos=kwargs.get("outgoing_scroll_pos", 0))
            shown = {s.arrive for s in plan if s.arrive < visible_count(t, n)}
            visible = [s for s in plan if s.arrive in shown]
        else:
            snap_reset(canvas, kwargs.get("incoming_bg_color"))
            incoming.draw(canvas, cursor_pos=0)
            gone = departed_count(t, n)
            visible = [s for s in plan if s.depart >= gone]

        for s in sorted(visible, key=lambda s: s.arrive):  # later arrivals on top
            px = self._raster.get(s.slug, s.angle_deg, scale, content_height, footprint)
            if not px:
                continue
            w = max(p[0] for p in px)
            h = max(p[1] for p in px)
            ox, oy = s.cx - w // 2, s.cy - h // 2
            for (x, y), (r, g, b) in px.items():
                tx, ty = ox + x, oy + y
                if 0 <= tx < real.width and 0 <= ty < real.height:
                    real.SetPixel(tx, ty, r, g, b)
        return canvas
