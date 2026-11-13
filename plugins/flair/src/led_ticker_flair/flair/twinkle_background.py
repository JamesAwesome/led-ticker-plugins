"""flair.twinkle BACKGROUND effect — a twinkling starfield painted BEHIND a
widget's content (``background = "flair.twinkle"``).

Stars are the pixels of the real panel that ``is_twinkler`` selects at
``density``; each paints ``color * level * brightness`` at physical
resolution. Pure function of ``(frame_count, real dims)`` per instance
(``seed=None`` draws one OS-entropy seed at construction). Never paints
black, so it can't erase a host's ``bg_color`` or image.

``color`` is an ``[r, g, b]`` triple or any ``font_color``-style color
provider (``"rainbow"``, ``{style = "gradient", ...}``, ...). A provider is
sampled by POSITION: the panel is cut into ``_CELL_LOGICAL_PX``-wide columns
("cells", about one BDF character each) and every star takes its cell's
``color_for(frame, cell, n_cells)``, so a gradient runs left to right and a
rainbow sweeps across the panel like rainbow text.
"""

import math
import random
from typing import Any

from led_ticker.plugin import (
    BackgroundEffectBase,
    ColorProvider,
    coerce_color_provider,
    unwrap_to_real,
)

from led_ticker_flair.flair._twinkle import hash32, is_twinkler
from led_ticker_flair.flair.twinkle import validate_common

# Width of one provider "cell" in LOGICAL pixels (x scale on a scaled sign):
# roughly one BDF character, so a rainbow background's hue steps match
# rainbow text drawn over it.
_CELL_LOGICAL_PX = 6


def _logical_scale(canvas: Any) -> int:
    """Logical-to-real scale for sizing provider cells.

    Core guarantees (core >= 4.34, led-ticker#535) that the canvas handed to
    a background's ``paint`` carries the section's logical scale on EVERY
    host: text hosts draw on the ``ScaledCanvas`` from ``_maybe_wrap``, and
    ``paint_background`` re-wraps the raw real canvas image hosts (gif /
    image) paint on at the widget's ``_logical_scale``. A canvas with no
    ``scale`` is therefore genuinely scale 1 — e.g. a ``scale = 1,
    content_height = 64`` section on a 64-row panel, where core doesn't
    wrap at all. Never infer the scale from the panel height: that guess was
    wrong for exactly those sections.
    """
    return max(1, int(getattr(canvas, "scale", 1)))


def _parse_color(color: Any) -> tuple[int, int, int] | ColorProvider:
    """A constant triple stays a tuple (the fast path); anything else must
    coerce to a ColorProvider."""
    if isinstance(color, list | tuple):
        ok = len(color) == 3 and all(
            isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 255
            for v in color
        )
        if not ok:
            raise ValueError(
                f"color must be an [r, g, b] triple of ints 0-255; got {color!r}"
            )
        return (color[0], color[1], color[2])
    try:
        provider = coerce_color_provider(color, "color")
    except (ValueError, TypeError) as exc:
        raise ValueError(
            "color must be an [r, g, b] triple or a color provider "
            f'(e.g. "rainbow", {{style = "gradient", ...}}): {exc}'
        ) from exc
    if provider is None:
        raise ValueError(f"color must not be empty; got {color!r}")
    return provider


class TwinkleBackground(BackgroundEffectBase):
    frame_invariant = False
    restart_on_visit = False

    def __init__(
        self,
        density: float = 0.03,
        speed: float = 1.0,
        color: Any = (255, 230, 180),
        seed: int | None = None,
        brightness: float = 1.0,
    ) -> None:
        validate_common(density, speed, seed)
        if (
            isinstance(brightness, bool)
            or not isinstance(brightness, int | float)
            or math.isnan(brightness)
            or not 0 < brightness <= 1
        ):
            raise ValueError(
                f"brightness must be a number in (0, 1]; got {brightness!r}"
            )
        self.density = float(density)
        self.speed = float(speed)
        self.color = _parse_color(color)
        self.brightness = float(brightness)
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
        k = self.brightness
        cycle = self._cycle
        set_pixel = real.SetPixel
        stars = self._stars_for(w, h)
        if isinstance(self.color, tuple):
            cr, cg, cb = (v * k for v in self.color)
            for x, y, factor, offset in stars:
                p = (frame_count * factor / cycle + offset) % 1
                lvl = 3 * p if p < 1 / 3 else 1.5 * (1 - p)
                r, g, b = round(cr * lvl), round(cg * lvl), round(cb * lvl)
                if r or g or b:
                    set_pixel(x, y, r, g, b)
            return
        # Provider: one color_for per cell per paint, then a table lookup.
        cell = _CELL_LOGICAL_PX * _logical_scale(canvas)
        n = -(-w // cell)
        provider = self.color
        cells = []
        for i in range(n):
            c = provider.color_for(frame_count, i, n)
            cells.append((c.red * k, c.green * k, c.blue * k))
        for x, y, factor, offset in stars:
            p = (frame_count * factor / cycle + offset) % 1
            lvl = 3 * p if p < 1 / 3 else 1.5 * (1 - p)
            cr, cg, cb = cells[x // cell]
            r, g, b = round(cr * lvl), round(cg * lvl), round(cb * lvl)
            if r or g or b:
                set_pixel(x, y, r, g, b)
