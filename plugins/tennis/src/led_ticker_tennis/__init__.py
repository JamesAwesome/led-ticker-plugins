"""led-ticker-tennis: live tennis scores (ATP, WTA, Challenger, ITF) for
led-ticker, contributed via the ``led_ticker.plugins`` entry point.

The entry-point name ``tennis`` is the plugin namespace, so the widget is
``type = "tennis.scores"``. Data: the Live Tennis API (https://livetennisapi.com),
free tier — this plugin is maintained by that API's vendor.
"""

from led_ticker_tennis.scores import TennisScoreMonitor


def register(api):
    api.widget("scores")(TennisScoreMonitor)
