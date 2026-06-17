"""Pokeball emoji (arcade.pokeball) — lowres 8x8 + hi-res 32x32 sprites,
ported from led-ticker core. Self-contained (procedural pixel math)."""

import math

from led_ticker.plugin import HiResEmoji, PixelData

# Color constants shared by lowres and hires generators.
_PB_R = (220, 0, 0)  # classic pokeball red
_PB_W = (245, 245, 245)
_PB_K = (40, 40, 40)  # black band / outline

# 🔴⚪ 8×8 Pokeball — round ball, red top, white bottom, black band
# across the middle with a white button.
POKEBALL: PixelData = [
    # Row 0: top of ball (rounded)
    (1, 0, *_PB_R),
    (2, 0, *_PB_R),
    (3, 0, *_PB_R),
    (4, 0, *_PB_R),
    (5, 0, *_PB_R),
    (6, 0, *_PB_R),
    # Row 1: full red
    *((x, 1, *_PB_R) for x in range(8)),
    # Row 2: full red
    *((x, 2, *_PB_R) for x in range(8)),
    # Row 3: black band (top of band)
    *((x, 3, *_PB_K) for x in range(8)),
    # Row 4: black band with white button at center
    (0, 4, *_PB_K),
    (1, 4, *_PB_K),
    (2, 4, *_PB_K),
    (3, 4, *_PB_W),
    (4, 4, *_PB_W),
    (5, 4, *_PB_K),
    (6, 4, *_PB_K),
    (7, 4, *_PB_K),
    # Row 5: full white
    *((x, 5, *_PB_W) for x in range(8)),
    # Row 6: full white
    *((x, 6, *_PB_W) for x in range(8)),
    # Row 7: bottom (rounded)
    (1, 7, *_PB_W),
    (2, 7, *_PB_W),
    (3, 7, *_PB_W),
    (4, 7, *_PB_W),
    (5, 7, *_PB_W),
    (6, 7, *_PB_W),
]


# 🔴⚪ Hi-res pokeball — round ball with red top, white bottom, black
# band across the middle with a white button. 1-px black outline along
# the silhouette.
def _generate_pokeball_hires(
    size: int = 32,
) -> tuple[tuple[int, int, int, int, int], ...]:
    pixels: dict[tuple[int, int], tuple[int, int, int]] = {}

    cx = cy = (size - 1) / 2.0
    body_r = size / 2 - 0.5
    band_half_h = 1.5  # 3-px-thick band — thinner so the button pops out
    button_outer_r = body_r * 0.30  # outer black ring of the button
    button_inner_r = button_outer_r - 1.5  # white center

    # Step 1: fill the ball — red above the equator, white below.
    for y in range(size):
        for x in range(size):
            dx = x - cx
            dy = y - cy
            d = math.sqrt(dx * dx + dy * dy)
            if d > body_r:
                continue
            pixels[(x, y)] = _PB_R if dy < 0 else _PB_W

    # Step 2: black band across the middle (3 rows)
    for y in range(size):
        for x in range(size):
            dx = x - cx
            dy = y - cy
            d = math.sqrt(dx * dx + dy * dy)
            if d > body_r:
                continue
            if abs(dy) <= band_half_h:
                pixels[(x, y)] = _PB_K

    # Step 3: button — black outer ring + white inner, large enough that
    # it extends BEYOND the band into both halves (the iconic pokeball
    # button pops out of the band).
    for y in range(size):
        for x in range(size):
            dx = x - cx
            dy = y - cy
            d2 = dx * dx + dy * dy
            if d2 <= button_outer_r * button_outer_r:
                pixels[(x, y)] = _PB_K
    for y in range(size):
        for x in range(size):
            dx = x - cx
            dy = y - cy
            d2 = dx * dx + dy * dy
            if d2 <= button_inner_r * button_inner_r:
                pixels[(x, y)] = _PB_W

    # Step 4: 1-px black outline along the silhouette — paint any
    # not-yet-set cell whose 4-neighbor is inside the ball.
    body_keys = list(pixels.keys())
    for x, y in body_keys:
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < size and 0 <= ny < size and (nx, ny) not in pixels:
                pixels[(nx, ny)] = _PB_K

    return tuple((x, y, *c) for (x, y), c in pixels.items())


POKEBALL_HIRES = HiResEmoji(pixels=_generate_pokeball_hires(size=32), physical_size=32)
