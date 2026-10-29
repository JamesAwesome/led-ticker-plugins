"""led-ticker-hockey: live NHL scores for led-ticker, contributed via the
``led_ticker.plugins`` entry point.

The entry-point name ``hockey`` is the plugin namespace, so the widget is
``type = "hockey.scores"``. Data: the NHL public web API (no key).
"""

from led_ticker_hockey.emoji import PUCK
from led_ticker_hockey.scores import HockeyScoreMonitor


def register(api):
    api.widget("scores")(HockeyScoreMonitor)
    api.emoji("puck", PUCK)
