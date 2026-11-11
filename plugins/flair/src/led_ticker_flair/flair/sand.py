"""flair.sand — the outgoing content crumbles into sand that falls off the
bottom of the panel, then the incoming content pours in from the top, grain
by grain, and stacks into place.

Spec: docs/superpowers/specs/2026-11-10-flair-sand-transition-design.md

Design in one breath:
- **Snapshots.** Each widget is snapshotted into a plugin-local
  physical-resolution raster: the outgoing widget on the first crumble
  frame, the incoming widget LAZILY on the first ``t >= 0.5`` frame, after
  the runner's ``scale_switch_at`` re-wrap.
- **Grains.** Every lit real pixel becomes one grain (``_sand``), so on
  the bigsign the 16 LEDs of a logical pixel fall independently.
- **Timeline.** ``t ∈ [0, 0.5)`` crumbles; ``t ∈ [0.5, SNAP_THRESHOLD)``
  pours; the snap draws the incoming widget live.
- **Painting.** The per-frame loops inline the ``_sand`` position math, so
  a fully lit bigsign frame (about 16k grains) stays inside the tick
  budget.
"""

import random
from typing import Any

from led_ticker.plugin import (
    SNAP_THRESHOLD,
    Canvas,
    is_scaled,
    snap_reset,
    unwrap_to_real,
)

from ._sand import (
    CrumbleGrain,
    PourGrain,
    crumble_grains,
    crumble_gravity,
    pour_grains,
    pour_gravity,
)
from ._snapshot import SnapshotCache

CRUMBLE_END = 0.5


class Sand:
    """``transition = "flair.sand"``; the only knob is ``seed``."""

    min_frames = 30
    scale_switch_at = 0.5

    def __init__(self, seed: int | None = None) -> None:
        if seed is not None and (not isinstance(seed, int) or isinstance(seed, bool)):
            raise ValueError(f"seed must be an int or None; got {seed!r}")
        self.seed = seed
        self._seed = seed if seed is not None else random.SystemRandom().getrandbits(62)
        self._rng = random.Random(self._seed)
        self._crumble: list[CrumbleGrain] | None = None
        self._pour: list[PourGrain] | None = None
        self._last_t = 1.0
        self._cache = SnapshotCache()

    def _new_firing(self) -> None:
        if self.seed is None:
            self._seed = random.SystemRandom().getrandbits(62)
        self._rng = random.Random(self._seed)
        self._crumble = None
        self._pour = None

    def frame_at(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        if t == 0.0 or t < self._last_t:
            self._new_firing()
        self._last_t = t

        if t >= SNAP_THRESHOLD:
            snap_reset(canvas, kwargs.get("incoming_bg_color"))
            incoming.draw(canvas, cursor_pos=0)
            return canvas

        # `real` is re-derived EVERY call, never cached (constraint #1).
        real = unwrap_to_real(canvas) if is_scaled(canvas) else canvas
        if t < CRUMBLE_END:
            if self._crumble is None:
                pos = kwargs.get("outgoing_scroll_pos", 0)
                raster = self._cache.take(canvas, outgoing, pos, 0)
                self._crumble = crumble_grains(raster, self._rng)
            self._paint_crumble(real, self._crumble, t / CRUMBLE_END)
        else:
            if self._pour is None:
                raster = self._cache.take(canvas, incoming, 0, 1)
                self._pour = pour_grains(raster, self._rng)
            q = (t - CRUMBLE_END) / (SNAP_THRESHOLD - CRUMBLE_END)
            self._paint_pour(real, self._pour, q)
        return canvas

    @staticmethod
    def _paint_crumble(real: Any, grains: list[CrumbleGrain], p: float) -> None:
        w, h = real.width, real.height
        half_g = 0.5 * crumble_gravity(h)
        set_px = real.SetPixel
        for x0, y0, r, g, b, release, vx in grains:
            dt = p - release
            if dt <= 0:
                set_px(x0, y0, r, g, b)
                continue
            y = round(y0 + half_g * dt * dt)
            if y >= h:
                continue
            x = round(x0 + vx * dt)
            if 0 <= x < w:
                set_px(x, y, r, g, b)

    @staticmethod
    def _paint_pour(real: Any, grains: list[PourGrain], q: float) -> None:
        half_g = 0.5 * pour_gravity(real.height)
        set_px = real.SetPixel
        for x, y, r, g, b, start, dist in grains:
            dt = q - start
            if dt < 0:
                continue
            yy = (y - dist) + half_g * dt * dt
            if yy >= y:
                set_px(x, y, r, g, b)
                continue
            yi = round(yy)
            if yi >= 0:
                set_px(x, min(yi, y), r, g, b)
