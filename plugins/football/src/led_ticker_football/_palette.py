"""Semantic palette for the football renderers (0-255 Color constants).

One hue per data field so every renderer reads the same way: score/clock
white, quarter/date/kickoff amber, down & distance and spot cyan, the red
zone RED (reserved: nothing else is red), labels dim. Never restyle a field
locally — change it here.
"""

from led_ticker.plugin import Color, make_color

from led_ticker_football.teams import team

WHITE: Color = make_color(255, 255, 255)  # score, clock, lit timeout pips
AMBER: Color = make_color(255, 180, 0)  # quarter, date, kickoff, +PAT
CYAN: Color = make_color(0, 200, 220)  # down & distance, ball spot
RED: Color = make_color(230, 40, 40)  # red zone (situation + possession marker)
DIM: Color = make_color(70, 70, 70)  # labels, dividers, spent timeout pips
GREEN: Color = make_color(0, 220, 90)  # final winner score
LOSER: Color = make_color(120, 120, 120)  # final loser score
GRAY: Color = make_color(110, 110, 110)  # "@", records, BYE marker


def chip(abbrev: str) -> tuple[Color, Color]:
    """(primary, secondary) team colors as Colors."""
    t = team(abbrev)
    return make_color(*t.primary), make_color(*t.secondary)


def dim(color: Color, factor: float) -> Color:
    """Channel scaling (0.0-1.0)."""
    return make_color(
        min(255, int(color.red * factor)),
        min(255, int(color.green * factor)),
        min(255, int(color.blue * factor)),
    )


def lerp(a: Color, b: Color, t: float) -> Color:
    """Linear blend a -> b, t clamped to 0-1."""
    t = max(0.0, min(1.0, t))
    return make_color(
        round(a.red + (b.red - a.red) * t),
        round(a.green + (b.green - a.green) * t),
        round(a.blue + (b.blue - a.blue) * t),
    )
