"""led-ticker-pacman: Pac-Man sprite-trail transitions contributed via the
``led_ticker.plugins`` entry point.

The entry-point name ``pacman`` is the plugin namespace, so transitions are
referenced in config.toml as ``transition = "pacman.forward"`` etc.
"""

from led_ticker_flair.pacman.pacman import Pacman, PacmanAlternating, PacmanReverse


def register(api):
    api.transition("forward")(Pacman)
    api.transition("reverse")(PacmanReverse)
    api.transition("alternating")(PacmanAlternating)
