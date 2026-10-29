"""led-ticker-football: live NFL scores for led-ticker, contributed via the
``led_ticker.plugins`` entry point.

The entry-point name ``football`` is the plugin namespace, so the widget is
``type = "football.scores"``. Data: ESPN's public scoreboard API (no key).
"""

from led_ticker_football import _logos
from led_ticker_football.emoji import BALL
from led_ticker_football.scores import FootballScoreMonitor
from led_ticker_football.teams import NFL_TEAMS


def register(api):
    api.widget("scores")(FootballScoreMonitor)
    api.emoji("ball", BALL)
    # Every bundled team logo is also an inline emoji, e.g. :football.phi:.
    for abbrev in NFL_TEAMS:
        pair = _logos.emoji(abbrev)
        if pair is not None:
            api.emoji(abbrev.lower(), pair[0])
            api.hires_emoji(abbrev.lower(), pair[1])
