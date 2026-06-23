"""led-ticker-flair / pokeball: Pokeball/Pikachu sprite-trail transitions + the
``:pokeball.ball:`` emoji, contributed via the ``led_ticker.plugins`` entry
point.

The entry-point name ``pokeball`` is the plugin namespace, so transitions are
``transition = "pokeball.forward"`` etc. and the emoji is ``:pokeball.ball:``.
"""

from led_ticker_flair.pokeball.emoji import POKEBALL, POKEBALL_HIRES
from led_ticker_flair.pokeball.pokeball import (
    Pokeball,
    PokeballAlternating,
    PokeballReverse,
)


def register(api):
    api.transition("forward")(Pokeball)
    api.transition("reverse")(PokeballReverse)
    api.transition("alternating")(PokeballAlternating)
    api.emoji("ball", POKEBALL)
    api.hires_emoji("ball", POKEBALL_HIRES)
