"""led-ticker-arcade: video-game & anime sprite-trail transitions contributed
via the ``led_ticker.plugins`` entry point.

The entry-point name ``arcade`` is the plugin namespace, so transitions are
referenced as ``transition = "arcade.pacman"`` etc. in config.toml.
"""

from led_ticker_arcade.emoji import POKEBALL, POKEBALL_HIRES
from led_ticker_arcade.nyancat import NyanCat, NyanCatAlternating, NyanCatReverse
from led_ticker_arcade.pacman import Pacman, PacmanAlternating, PacmanReverse
from led_ticker_arcade.pokeball import Pokeball, PokeballAlternating, PokeballReverse
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
    api.transition("nyancat")(NyanCat)
    api.transition("nyancat_reverse")(NyanCatReverse)
    api.transition("nyancat_alternating")(NyanCatAlternating)
    api.transition("pokeball")(Pokeball)
    api.transition("pokeball_reverse")(PokeballReverse)
    api.transition("pokeball_alternating")(PokeballAlternating)
    api.emoji("pokeball", POKEBALL)
    api.hires_emoji("pokeball", POKEBALL_HIRES)
