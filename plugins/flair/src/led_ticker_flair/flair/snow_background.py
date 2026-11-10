"""flair.snow BACKGROUND effect — falling snow painted BEHIND a widget's
content (``background = "flair.snow"``).

Flakes are ``"dot"``, ``"plus"``, or an emoji slug's 8x8 low-res sprite,
painted 1:1 at physical resolution (never block-expanded). Pure function of
``(frame_count, real dims)`` per instance (``seed=None`` draws one
OS-entropy seed at construction). Never paints black.
"""

import random
from typing import Any

from led_ticker.plugin import BackgroundEffectBase, unwrap_to_real

from led_ticker_flair.flair._snow import (
    flake_count,
    flake_height,
    flake_pixels,
    flake_position,
    validate_color,
    validate_flake,
    validate_number,
)


class SnowBackground(BackgroundEffectBase):
    frame_invariant = False
    restart_on_visit = False

    def __init__(
        self,
        flake: str = "dot",
        density: float = 3.0,
        speed: float = 1.0,
        speed_variation: float = 0.4,
        drift: float = 0.3,
        wind: float = 0.0,
        color: Any = (200, 220, 255),
        seed: int | None = None,
    ) -> None:
        validate_flake(flake)
        validate_number(
            "density", density, isinstance(density, int | float) and density > 0, "> 0"
        )
        validate_number(
            "speed",
            speed,
            isinstance(speed, int | float) and 0 < speed <= 5,
            "in (0, 5]",
        )
        validate_number(
            "speed_variation",
            speed_variation,
            isinstance(speed_variation, int | float) and 0 <= speed_variation < 1,
            "in [0, 1)",
        )
        validate_number(
            "drift", drift, isinstance(drift, int | float) and drift >= 0, ">= 0"
        )
        validate_number("wind", wind, True, "")
        validate_color(color)
        if seed is not None and (not isinstance(seed, int) or isinstance(seed, bool)):
            raise ValueError(f"seed must be an int or None; got {seed!r}")
        self.flake = flake
        self.density = float(density)
        self.speed = float(speed)
        self.speed_variation = float(speed_variation)
        self.drift = float(drift)
        self.wind = float(wind)
        self.color = (color[0], color[1], color[2])
        self.seed = seed
        self._seed = seed if seed is not None else random.SystemRandom().getrandbits(62)
        self._is_emoji = flake not in ("dot", "plus")
        self._sprite_h = flake_height(flake)
        self._pixels = tuple(flake_pixels(flake, self.color).items())
        # Per-intensity shaded pixel lists (dot/plus only), quantized to 16 steps.
        self._shaded: dict[int, tuple[tuple[int, int, int, int, int], ...]] = {}

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

    def paint(self, canvas: Any, frame_count: int) -> None:
        real = unwrap_to_real(canvas)
        w, h = real.width, real.height
        if w <= 0 or h <= 0:
            return
        set_pixel = real.SetPixel
        emoji = self._is_emoji
        full: tuple[tuple[int, int, int, int, int], ...] = ()
        if emoji:
            full = tuple(
                (dx, dy, r, g, b) for (dx, dy), (r, g, b) in self._pixels if r or g or b
            )
        for i in range(flake_count(w, h, self.density)):
            x, y, inten = flake_position(
                i,
                frame_count,
                w,
                h,
                self._seed,
                self.speed,
                self.speed_variation,
                self.drift,
                self.wind,
                self._sprite_h,
            )
            pix = full if emoji else self._shade(max(1, round(inten * 16)))
            for dx, dy, r, g, b in pix:
                px, py = x + dx, y + dy
                if 0 <= px < w and 0 <= py < h:
                    set_pixel(px, py, r, g, b)
