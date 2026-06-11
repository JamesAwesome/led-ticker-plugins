"""led-ticker-baseball: MLB scores/standings widgets, baseball emoji, and
baseball transitions, contributed via the ``led_ticker.plugins`` entry point.

The entry-point name ``baseball`` is the plugin namespace, so widgets are
``type = "baseball.scores"`` / ``"baseball.standings"`` /
``"baseball.promotions"``, transitions are ``baseball.roll`` /
``baseball.roll_reverse`` / ``baseball.roll_alternating``, and the emoji is
``:baseball.ball:``.
"""

from led_ticker_baseball.emoji import BALL, BALL_HIRES
from led_ticker_baseball.promotions import MLBPromotionsMonitor
from led_ticker_baseball.scores import MLBScoreMonitor
from led_ticker_baseball.standings import MLBStandingsMonitor
from led_ticker_baseball.transition import (
    Baseball,
    BaseballAlternating,
    BaseballReverse,
)


def register(api):
    api.widget("scores")(MLBScoreMonitor)
    api.widget("standings")(MLBStandingsMonitor)
    api.widget("promotions")(MLBPromotionsMonitor)
    api.transition("roll")(Baseball)
    api.transition("roll_reverse")(BaseballReverse)
    api.transition("roll_alternating")(BaseballAlternating)
    api.emoji("ball", BALL)
    api.hires_emoji("ball", BALL_HIRES)
