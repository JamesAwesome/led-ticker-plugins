"""led-ticker-basketball: live NBA scores for led-ticker, contributed via the
``led_ticker.plugins`` entry point.

The entry-point name ``basketball`` is the plugin namespace, so the widget is
``type = "basketball.scores"``. Data: ESPN's public scoreboard API (no key).
"""

from led_ticker_basketball.emoji import BALL, BALL_HIRES
from led_ticker_basketball.scores import BasketballScoreMonitor


def register(api):
    api.widget("scores")(BasketballScoreMonitor)
    api.emoji("ball", BALL)
    api.hires_emoji("ball", BALL_HIRES)
