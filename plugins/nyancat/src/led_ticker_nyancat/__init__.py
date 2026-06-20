"""led-ticker-nyancat: Nyan Cat sprite-trail transitions contributed via the
``led_ticker.plugins`` entry point.

The entry-point name ``nyancat`` is the plugin namespace, so transitions are
referenced in config.toml as ``transition = "nyancat.forward"`` etc.
"""

from led_ticker_nyancat.nyancat import NyanCat, NyanCatAlternating, NyanCatReverse


def register(api):
    api.transition("forward")(NyanCat)
    api.transition("reverse")(NyanCatReverse)
    api.transition("alternating")(NyanCatAlternating)
