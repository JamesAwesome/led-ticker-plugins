"""Semantic design-handoff palette (design/README.md 'Design Tokens').

Verbatim port of the handoff table, stored 0-255 (the prototype's 0-1
storage is an artifact of its JS engine — our Color layer is 0-255).
One semantic hue per data field; never restyle locally.
"""

from led_ticker.plugin import Color, make_color

IDENT: Color = make_color(255, 255, 255)   # primary text / scores / neutral
WIN: Color = make_color(60, 220, 60)       # wins, positive, balls
LOSS: Color = make_color(255, 60, 60)      # losses, outs, inning triangle
AMBER: Color = make_color(255, 180, 0)     # headline numbers, dates, time
CYAN: Color = make_color(0, 220, 255)      # secondary metrics
MAGENTA: Color = make_color(255, 80, 255)  # distance / trajectory
VIOLET: Color = make_color(170, 90, 255)   # opponent (VS)
LABEL: Color = make_color(70, 90, 130)     # dim labels, dividers, empty bases
YEL: Color = make_color(255, 217, 0)       # strikes in the count
ORANGE: Color = make_color(255, 128, 0)    # series-win dashes


def dim(color: Color, factor: float) -> Color:
    """Prototype `brightness` arg -> channel scaling (0.0-1.0)."""
    return make_color(
        min(255, int(color.red * factor)),
        min(255, int(color.green * factor)),
        min(255, int(color.blue * factor)),
    )
