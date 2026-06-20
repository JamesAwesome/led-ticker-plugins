"""led-ticker-sailor-moon: Sailor Moon sprite-trail transitions contributed via
the ``led_ticker.plugins`` entry point.

The entry-point name ``sailor_moon`` is the plugin namespace, so transitions are
referenced in config.toml as ``transition = "sailor_moon.forward"`` etc.
"""

from led_ticker_sailor_moon.sailor_moon import (
    SailorMoon,
    SailorMoonAlternating,
    SailorMoonReverse,
)


def register(api):
    api.transition("forward")(SailorMoon)
    api.transition("reverse")(SailorMoonReverse)
    api.transition("alternating")(SailorMoonAlternating)
