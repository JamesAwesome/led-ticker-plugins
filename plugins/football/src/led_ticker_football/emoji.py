"""The ``:football.ball:`` emoji: an 8x8 lo-res sprite, also painted as the
sport icon on the smallsign band board."""

from led_ticker.plugin import PixelData

_B = (160, 80, 30)  # leather
_W = (255, 255, 255)  # laces

# A ball on the diagonal with laces along its long axis.
_ROWS = [
    "....BBB.",
    "..BBBBBB",
    ".BBBWBBB",
    ".BBWBWBB",
    "BBWBWBB.",
    "BBBWBBB.",
    "BBBBBB..",
    ".BBB....",
]
BALL: PixelData = [
    (x, y, *(_W if c == "W" else _B))
    for y, row in enumerate(_ROWS)
    for x, c in enumerate(row)
    if c != "."
]
