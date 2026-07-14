"""Semantic palette (RGB) from the design handoff.

`dim()` scales for market-state brightness.
"""

from led_ticker.plugin import Color, make_color

SYM: Color = make_color(255, 255, 255)
PRICE: Color = make_color(255, 180, 0)
UP: Color = make_color(60, 220, 60)
DOWN: Color = make_color(255, 60, 60)
FLAT: Color = make_color(255, 180, 0)
IDX: Color = make_color(0, 220, 255)  # retained for future indices (unused in v1)
FX: Color = make_color(170, 90, 255)  # retained for future forex (unused in v1)
LABEL: Color = make_color(70, 90, 130)
WHITE: Color = make_color(255, 255, 255)


def dim(color: Color, factor: float) -> Color:
    """Return `color` with every channel scaled by `factor` (0.0-1.0), rounded."""
    return make_color(
        round(color.red * factor),
        round(color.green * factor),
        round(color.blue * factor),
    )
