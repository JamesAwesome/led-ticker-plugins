"""The ``:hockey.puck:`` emoji: an 8x8 lo-res sprite (a stick and a puck),
also painted as the sport icon on the smallsign band board."""

from led_ticker.plugin import PixelData

_S = (210, 160, 90)  # stick
_G = (150, 150, 160)  # puck: gray, never near-black (black is invisible)

_ROWS = [
    "S.......",
    ".S......",
    "..S.....",
    "...S....",
    "....S...",
    "....SSS.",
    ".GGG.SSS",
    ".GGG....",
]
PUCK: PixelData = [
    (x, y, color[0], color[1], color[2])
    for y, row in enumerate(_ROWS)
    for x, c in enumerate(row)
    if c != "."
    for color in (_G if c == "G" else _S,)
]
