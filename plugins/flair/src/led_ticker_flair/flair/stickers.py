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

# Random mode is "gone wild" ACROSS firings (a fresh replan re-samples) but
# capped to a coherent handful of distinct slugs WITHIN one firing -- with
# the standard-emoji pack (led-ticker core, ~1,400 drawable slugs) an
# uncapped per-sticker rng.choice would make every single sticker a
# different, unrelated emoji. A constant, not a knob (emoji-pack spec,
# Task 7). `emoji=[...]` is an explicit themed wall and bypasses this.
_RANDOM_VARIETY_CAP = 12


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


def compose_sticker(sprite, footprint=None, backing="card"):
    """Compose a sticker from sprite ink per the ``backing`` mode.

    ``backing="card"`` (default): sprite over a black backing + white rim
    (OUTLINE_PAD ring). Coverage comes from the backing+rim footprint.
    ``backing="shadow"``: sprite over a black silhouette halo
    (``BACKING_PAD`` dilation) — no rim, no squaring; ``footprint`` is
    ignored. ``backing="none"``: the bare sprite. Only "card" can honor
    the transition's full-cover-at-t=0.5 guarantee — the other two are
    the deliberate "swarm, not wall" looks (outgoing content stays
    visible through sprite gaps).

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
    # An empty sprite has no ink to back or center — a hires-only emoji drawn
    # at scale 1 (nothing to rasterize) is the way this happens. Return an
    # empty sticker rather than crashing on the bbox-center `min()` below; the
    # random-mode pool filters these out at the source (see `_firing_pool`),
    # so this only guards an explicit `emoji=[...]` list with an
    # unrenderable-at-this-scale slug.
    if not sprite:
        return {}
    if backing == "none":
        return dict(sprite)
    mask = set(sprite)
    if backing == "shadow":
        out = {p: (0, 0, 0) for p in dilate(mask, BACKING_PAD)}
        out.update(sprite)
        return out
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
    (slug, whole-degree angle, scale, content_height, footprint, backing)."""

    def __init__(self):
        self._cache = {}

    def get(
        self, slug, angle_deg, scale, content_height, footprint=None, backing="card"
    ):
        key = (slug, round(angle_deg), scale, content_height, footprint, backing)
        hit = self._cache.get(key)
        if hit is None:
            sprite = capture_sprite(slug, scale, content_height)
            composed = compose_sticker(sprite, footprint, backing)
            hit = rotate_pixels(composed, round(angle_deg))
            self._cache[key] = hit
        return hit


class Stickers:
    """Sticker-bomb: emoji pop on over the outgoing widget until full cover
    at t=0.5, then pop off in an independent random order revealing the
    incoming widget. `emoji=[...]` restricts the slug pool (one slug = a
    themed wall); omitted = a random assortment, capped to at most
    `_RANDOM_VARIETY_CAP` distinct slugs per firing (see `_firing_pool`) so
    one firing reads as a coherent handful rather than every drawable slug
    flashing past once -- a fresh replan (each re-fire) samples anew.
    ``backing`` picks the sticker body: "card" (default — tilted black card
    with a white rim; the only mode that fully covers the panel at the
    midpoint), "shadow" (black silhouette halo, no card), or "none" (bare
    sprites) — the latter two read as an emoji SWARM over the content
    rather than a wall (gaps between sprites never cover)."""

    _BACKINGS = ("card", "shadow", "none")

    min_frames = 24

    def __init__(
        self, emoji: Any = None, seed: int | None = None, backing: str = "card"
    ) -> None:
        if backing not in self._BACKINGS:
            raise ValueError(
                f"backing must be one of {list(self._BACKINGS)!r}; got {backing!r}"
            )
        self.backing = backing
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

    def _firing_pool(self, scale: int, content_height) -> list[str]:
        """The slug pool `plan_stickers` draws from for this firing.

        An explicit `emoji=[...]` list is used verbatim -- uncapped, since a
        themed wall of repeated slugs is the whole point. Random mode
        samples at most `_RANDOM_VARIETY_CAP` DISTINCT slugs from the
        drawable set via `self._rng`, so a seeded run stays deterministic
        and a seedless refire (which replaces `self._rng` -- see
        `frame_at`) draws a fresh subset. Called fresh on every (re)plan in
        `_ensure_plan`, never cached across plans.

        `emoji_slugs()` grew to include the standard-emoji pack (core >=4.21):
        ~1,360 HIRES-ONLY slugs that rasterize to NOTHING at scale 1. At
        scale 1 (smallsign) the pool is filtered to slugs that actually draw
        here -- the curated low-res set -- so a firing never composes an empty
        sprite (which crashed `compose_sticker`'s bbox-center math) and full
        coverage stays achievable. The filter is cheap: an empty capture
        returns immediately, so screening all slugs is ~1ms. At scale > 1
        every slug has a hires form, so no filtering is needed.
        """
        if self.emoji:
            return self.emoji
        pool = list(emoji_slugs())
        if scale == 1:
            pool = [s for s in pool if capture_sprite(s, scale, content_height)]
        if len(pool) > _RANDOM_VARIETY_CAP:
            pool = self._rng.sample(pool, _RANDOM_VARIETY_CAP)
        return pool

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
            pool = self._firing_pool(scale, content_height)
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
                self._raster.get(
                    s.slug,
                    s.angle_deg,
                    scale,
                    content_height,
                    footprint,
                    self.backing,
                )
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
            px = self._raster.get(
                s.slug, s.angle_deg, scale, content_height, footprint, self.backing
            )
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
