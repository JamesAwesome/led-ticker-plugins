"""flair.twinkle BACKGROUND effect — a twinkling starfield painted BEHIND a
widget's content (``background = "flair.twinkle"``).

Stars are the pixels of the real panel that ``is_twinkler`` selects at
``density``; each paints ``color * level`` at physical resolution. Pure
function of ``(frame_count, real dims)`` per instance (``seed=None`` draws
one OS-entropy seed at construction). Never paints black, so it can't erase
a host's ``bg_color`` or image.
"""

import random
from typing import Any

from led_ticker.plugin import BackgroundEffectBase, unwrap_to_real

from led_ticker_flair.flair._twinkle import hash32, is_twinkler
from led_ticker_flair.flair.twinkle import validate_common


class TwinkleBackground(BackgroundEffectBase):
    frame_invariant = False
    restart_on_visit = False

    def __init__(
        self,
        density: float = 0.03,
        speed: float = 1.0,
        color: Any = (255, 230, 180),
        seed: int | None = None,
    ) -> None:
        validate_common(density, speed, seed)
        ok = (
            isinstance(color, list | tuple)
            and len(color) == 3
            and all(
                isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 255
                for v in color
            )
        )
        if not ok:
            raise ValueError(
                f"color must be an [r, g, b] triple of ints 0-255; got {color!r}"
            )
        self.density = float(density)
        self.speed = float(speed)
        self.color = (color[0], color[1], color[2])
        self.seed = seed
        self._seed = seed if seed is not None else random.SystemRandom().getrandbits(62)
        self._cycle = 24 / self.speed
        # (w, h) -> [(x, y, factor, offset), ...]; derived data, not sim state.
        self._stars: dict[tuple[int, int], list[tuple[int, int, float, float]]] = {}

    def _stars_for(self, w: int, h: int) -> list[tuple[int, int, float, float]]:
        stars = self._stars.get((w, h))
        if stars is None:
            seed, density = self._seed, self.density
            stars = [
                (
                    x,
                    y,
                    1 + (hash32(x, y, seed, 2) % 8) / 8,
                    hash32(x, y, seed, 3) / 2**32,
                )
                for y in range(h)
                for x in range(w)
                if is_twinkler(x, y, seed, density)
            ]
            self._stars.clear()  # only the current geometry is worth keeping
            self._stars[(w, h)] = stars
        return stars

    def paint(self, canvas: Any, frame_count: int) -> None:
        real = unwrap_to_real(canvas)
        w, h = real.width, real.height
        if w <= 0 or h <= 0:
            return
        cr, cg, cb = self.color
        cycle = self._cycle
        set_pixel = real.SetPixel
        for x, y, factor, offset in self._stars_for(w, h):
            p = (frame_count * factor / cycle + offset) % 1
            lvl = 3 * p if p < 1 / 3 else 1.5 * (1 - p)
            r, g, b = round(cr * lvl), round(cg * lvl), round(cb * lvl)
            if r or g or b:
                set_pixel(x, y, r, g, b)
