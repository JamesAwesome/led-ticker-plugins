"""The ``:basketball.ball:`` emoji: 8x8 lo-res sprite and a 32x32 hi-res disc."""

import math

from led_ticker.plugin import HiResEmoji, PixelData

_F = (255, 120, 30)  # fill
_S = (110, 50, 20)  # seams

# Vertical seam at x=3, horizontal at y=3, side seams at x=1 and x=6 (rows 2-5).
_ROWS = [
    "..FSFF..",
    ".FFSFFF.",
    "FSFSFFSF",
    "SSSSSSSS",
    "FSFSFFSF",
    "FSFSFFSF",
    ".FFSFFF.",
    "..FSFF..",
]
BALL: PixelData = [
    (
        x,
        y,
        (_S if c == "S" else _F)[0],
        (_S if c == "S" else _F)[1],
        (_S if c == "S" else _F)[2],
    )
    for y, row in enumerate(_ROWS)
    for x, c in enumerate(row)
    if c != "."
]


def _generate_basketball_hires(
    size: int = 32,
) -> tuple[tuple[int, int, int, int, int], ...]:
    c = (size - 1) / 2.0
    body_r = size / 2 - 0.5
    lo, hi = size // 2 - 1, size // 2

    def seam(x: int, y: int) -> bool:
        if x in (lo, hi) or y in (lo, hi):
            return True
        for ax in (-size / 8, size + size / 8 - 1):
            d = math.hypot(x - ax, y - c)
            if abs(d - (size / 2 - 1)) <= 1.0:
                return True
        return False

    out = []
    for y in range(size):
        for x in range(size):
            if math.hypot(x - c, y - c) > body_r:
                continue
            out.append((x, y, *(_S if seam(x, y) else _F)))
    return tuple(out)


BALL_HIRES = HiResEmoji(pixels=_generate_basketball_hires(size=32), physical_size=32)
