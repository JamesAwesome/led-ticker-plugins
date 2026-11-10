"""flair.snow — a ragged front of snow sweeps down the panel, swapping the
outgoing content for the incoming one behind a flurry of flakes
(``mode = "flurry"``).

Design in one breath: both widgets are snapshotted ONCE per firing into
plugin-local physical-resolution rasters (the laser pattern), and each
column's lit pixels are kept as a sorted ``(y, rgb)`` list. The front is
per-column: ``front(x, t) = (t / SNAP_THRESHOLD) * (h + J) - J + jit(x)``
with ``J = max(2, h // 4)`` and ``jit(x)`` a hash in ``[0, J]``. Incoming
lit pixels with ``y < front(x)`` and outgoing lit pixels with
``y >= front(x)`` are painted; flakes (the shared ``_snow`` model, scaled by
``sin(pi * t)`` so they build up and die away) paint on top, never black.
Flakes are driven by a pseudo-frame ``int(t * FRAMES_PER_T)`` at
``FLAKE_SPEED`` so they fall ~1.5x faster than the front and lead it.

Known limit: with ``scale_switch_at = 1.0`` the runner fills
``outgoing_bg_color`` until the snap, so sections with different
``bg_color`` pop at the snap rather than following the front (same accepted
limitation as laser/fairy).
"""

import math
import random
from typing import Any

from led_ticker.plugin import (
    SNAP_THRESHOLD,
    Canvas,
    is_scaled,
    snap_reset,
    unwrap_to_real,
)

from ._raster import Raster, is_lit, snapshot_into
from ._snow import (
    flake_count,
    flake_height,
    flake_pixels,
    flake_position,
    validate_color,
    validate_flake,
)
from ._twinkle import hash32

SALT_JITTER = 9
# t in [0, 1] -> pseudo-frame fed to flake_position; with FLAKE_SPEED the
# flakes cover ~1.5x the front's per-t distance (front ~ 1.3 * h / 0.95-ish).
FRAMES_PER_T = 100
FLAKE_SPEED = 2.0
FLAKE_SPEED_VARIATION = 0.4

_Column = list[tuple[int, tuple[int, int, int]]]


def _num(name: str, v: object, ok: bool, rng: str) -> None:
    if isinstance(v, bool) or not isinstance(v, int | float) or math.isnan(v) or not ok:
        raise ValueError(f"{name} must be a number {rng}; got {v!r}")


class Snow:
    min_frames = 24
    scale_switch_at = 1.0

    def __init__(
        self,
        flake: str = "dot",
        density: float = 6.0,
        drift: float = 0.3,
        wind: float = 0.0,
        color: Any = (230, 240, 255),
        seed: int | None = None,
        mode: str = "flurry",
    ) -> None:
        if mode == "build":
            raise ValueError('mode "build" is planned, not yet available')
        if mode != "flurry":
            raise ValueError(f'mode must be "flurry"; got {mode!r}')
        validate_flake(flake)
        _num(
            "density", density, isinstance(density, int | float) and density > 0, "> 0"
        )
        _num("drift", drift, isinstance(drift, int | float) and drift >= 0, ">= 0")
        _num("wind", wind, True, "")
        validate_color(color)
        if seed is not None and (not isinstance(seed, int) or isinstance(seed, bool)):
            raise ValueError(f"seed must be an int or None; got {seed!r}")
        self.flake = flake
        self.density = float(density)
        self.drift = float(drift)
        self.wind = float(wind)
        self.color = (color[0], color[1], color[2])
        self.mode = mode
        self.seed = seed
        self._seed = seed if seed is not None else random.SystemRandom().getrandbits(62)
        self._is_emoji = flake not in ("dot", "plus")
        self._sprite_h = flake_height(flake)
        self._pixels = tuple(flake_pixels(flake, self.color).items())
        self._shaded: dict[int, tuple[tuple[int, int, int, int, int], ...]] = {}
        self._cols: tuple[list[_Column], list[_Column]] | None = None
        self._jit: list[int] = []
        self._last_t = 1.0
        self._rasters: list[Raster | None] = [None, None]
        self._raster_key: tuple[int, int, int, int | None] | None = None

    # --- snapshot -------------------------------------------------------------

    def _snapshot(self, canvas: Any, widget: Any, pos: int, slot: int) -> Raster:
        scaled = is_scaled(canvas)
        real = unwrap_to_real(canvas) if scaled else canvas
        key = (
            real.width,
            real.height,
            canvas.scale if scaled else 1,
            canvas.content_height if scaled else None,
        )
        if self._raster_key != key:
            self._rasters = [None, None]
            self._raster_key = key
        raster = self._rasters[slot]
        if raster is None:
            raster = Raster(real.width, real.height)
            self._rasters[slot] = raster
        snapshot_into(raster, canvas, widget, pos)
        return raster

    @staticmethod
    def _columns(raster: Raster) -> list[_Column]:
        w, h = raster.width, raster.height
        get = raster.get
        cols: list[_Column] = [[] for _ in range(w)]
        for x in range(w):
            col = cols[x]
            for y in range(h):
                px = get(x, y)
                if is_lit(px):
                    col.append((y, px))  # type: ignore[arg-type]
        return cols

    def _ensure_plan(self, canvas: Any, outgoing: Any, incoming: Any, pos: int) -> None:
        if self._cols is not None:
            return
        out_r = self._snapshot(canvas, outgoing, pos, 0)
        in_r = self._snapshot(canvas, incoming, 0, 1)
        w, h = out_r.width, out_r.height
        j = max(2, h // 4)
        self._jit = [hash32(x, 0, self._seed, SALT_JITTER) % (j + 1) for x in range(w)]
        self._cols = (self._columns(out_r), self._columns(in_r))

    # --- flakes ---------------------------------------------------------------

    def _shade(self, q: int) -> tuple[tuple[int, int, int, int, int], ...]:
        cached = self._shaded.get(q)
        if cached is None:
            k = q / 16
            out = []
            for (dx, dy), (r, g, b) in self._pixels:
                r, g, b = round(r * k), round(g * k), round(b * k)
                if r or g or b:
                    out.append((dx, dy, r, g, b))
            cached = self._shaded[q] = tuple(out)
        return cached

    def _paint_flakes(self, real: Any, t: float) -> None:
        w, h = real.width, real.height
        n = int(flake_count(w, h, self.density) * math.sin(math.pi * t))
        if n <= 0:
            return
        frame = int(t * FRAMES_PER_T)
        set_px = real.SetPixel
        emoji = self._is_emoji
        full: tuple[tuple[int, int, int, int, int], ...] = ()
        if emoji:
            full = tuple(
                (dx, dy, r, g, b) for (dx, dy), (r, g, b) in self._pixels if r or g or b
            )
        for i in range(n):
            x, y, inten = flake_position(
                i,
                frame,
                w,
                h,
                self._seed,
                FLAKE_SPEED,
                FLAKE_SPEED_VARIATION,
                self.drift,
                self.wind,
                self._sprite_h,
            )
            pix = full if emoji else self._shade(max(1, round(inten * 16)))
            for dx, dy, r, g, b in pix:
                px, py = x + dx, y + dy
                if 0 <= px < w and 0 <= py < h:
                    set_px(px, py, r, g, b)

    # --- frame ----------------------------------------------------------------

    def frame_at(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        if t == 0.0 or t < self._last_t:  # new firing -> fresh snapshots
            self._cols = None
        self._last_t = t

        if t >= SNAP_THRESHOLD:
            snap_reset(canvas, kwargs.get("incoming_bg_color"))
            incoming.draw(canvas, cursor_pos=0)
            return canvas

        self._ensure_plan(
            canvas, outgoing, incoming, kwargs.get("outgoing_scroll_pos", 0)
        )
        assert self._cols is not None
        out_cols, in_cols = self._cols
        # `real` is re-derived EVERY call, never cached (constraint #1).
        real = unwrap_to_real(canvas) if is_scaled(canvas) else canvas
        h = real.height
        set_px = real.SetPixel
        j = max(2, h // 4)
        base = (t / SNAP_THRESHOLD) * (h + j) - j
        jit = self._jit
        for x in range(len(out_cols)):
            front = base + jit[x]
            for y, (r, g, b) in in_cols[x]:
                if y >= front:
                    break
                set_px(x, y, r, g, b)
            for y, (r, g, b) in reversed(out_cols[x]):
                if y < front:
                    break
                set_px(x, y, r, g, b)
        self._paint_flakes(real, t)
        return canvas
