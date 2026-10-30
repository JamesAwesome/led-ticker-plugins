"""led-ticker-basketball: live NBA scores for led-ticker, contributed via the
``led_ticker.plugins`` entry point.

The entry-point name ``basketball`` is the plugin namespace, so the widget is
``type = "basketball.scores"``. Data: ESPN's public scoreboard API (no key).
"""

from led_ticker_basketball import _logos
from led_ticker_basketball.emoji import BALL, BALL_HIRES
from led_ticker_basketball.scores import BasketballScoreMonitor
from led_ticker_basketball.teams import NBA_TEAMS


def register(api):
    api.widget("scores")(BasketballScoreMonitor)
    api.emoji("ball", BALL)
    api.hires_emoji("ball", BALL_HIRES)
    # Every bundled team logo is also an inline emoji, e.g. :basketball.phi:.
    for abbrev in NBA_TEAMS:
        pair = _logos.emoji(abbrev)
        if pair is not None:
            api.emoji(abbrev.lower(), pair[0])
            api.hires_emoji(abbrev.lower(), pair[1])
