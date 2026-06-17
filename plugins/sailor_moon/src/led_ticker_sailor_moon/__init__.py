"""led-ticker-arcade: video-game & anime sprite-trail transitions contributed
via the ``led_ticker.plugins`` entry point.

The entry-point name ``arcade`` is the plugin namespace, so transitions are
referenced as ``transition = "arcade.pacman"`` etc. in config.toml.
"""

from led_ticker_arcade.pacman import Pacman, PacmanAlternating, PacmanReverse
from led_ticker_arcade.sailor_moon import (
    SailorMoon,
    SailorMoonAlternating,
    SailorMoonReverse,
)


def register(api):
    api.transition("pacman")(Pacman)
    api.transition("pacman_reverse")(PacmanReverse)
    api.transition("pacman_alternating")(PacmanAlternating)
    api.transition("sailor_moon")(SailorMoon)
    api.transition("sailor_moon_reverse")(SailorMoonReverse)
    api.transition("sailor_moon_alternating")(SailorMoonAlternating)
