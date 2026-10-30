"""led-ticker-hockey: live NHL scores for led-ticker, contributed via the
``led_ticker.plugins`` entry point.

The entry-point name ``hockey`` is the plugin namespace, so the widget is
``type = "hockey.scores"``. Data: the NHL public web API (no key).
"""

from led_ticker_hockey import _logos
from led_ticker_hockey.emoji import PUCK
from led_ticker_hockey.scores import HockeyScoreMonitor
from led_ticker_hockey.teams import NHL_TEAMS


def register(api):
    api.widget("scores")(HockeyScoreMonitor)
    api.emoji("puck", PUCK)
    # Every bundled team logo is also an inline emoji, e.g. :hockey.phi:.
    for abbrev in NHL_TEAMS:
        pair = _logos.emoji(abbrev)
        if pair is not None:
            api.emoji(abbrev.lower(), pair[0])
            api.hires_emoji(abbrev.lower(), pair[1])
