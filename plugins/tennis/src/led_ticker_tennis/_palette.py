"""Semantic palette for the tennis renderers (0-255 Color constants).

One hue per data field, so the three renderers (physical scoreboard, hi-res
crawl, legacy scale-1 text) read the same way: names white, games amber,
points cyan, the serve marker ball-yellow, the break-point marker red.
Never restyle a field locally — change it here.
"""

from led_ticker.plugin import Color, make_color

IDENT: Color = make_color(255, 255, 255)  # player names, neutral text
WIN: Color = make_color(60, 220, 60)  # winner (final), live "SET n" label
LOSS: Color = make_color(255, 60, 60)  # break-point marker
AMBER: Color = make_color(255, 180, 0)  # games per set, start time
CYAN: Color = make_color(0, 220, 255)  # in-game points
SERVE: Color = make_color(255, 217, 0)  # serving indicator (tennis-ball yellow)
LABEL: Color = make_color(70, 90, 130)  # dim labels, tournament line
LABEL_HI: Color = make_color(165, 185, 220)  # loser (final), FINAL/RET labels
TB: Color = make_color(255, 128, 0)  # tiebreak marker


def dim(color: Color, factor: float) -> Color:
    """Channel scaling (0.0-1.0)."""
    return make_color(
        min(255, int(color.red * factor)),
        min(255, int(color.green * factor)),
        min(255, int(color.blue * factor)),
    )
