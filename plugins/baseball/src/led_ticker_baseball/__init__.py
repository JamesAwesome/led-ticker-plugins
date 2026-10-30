"""led-ticker-baseball: MLB scores/standings/attendance widgets, baseball emoji, and
baseball transitions, contributed via the ``led_ticker.plugins`` entry point.

The entry-point name ``baseball`` is the plugin namespace, so widgets are
``type = "baseball.scores"`` / ``"baseball.standings"`` /
``"baseball.promotions"`` / ``"baseball.statcast"`` / ``"baseball.attendance"``,
transitions are ``baseball.roll`` / ``baseball.roll_reverse`` /
``baseball.roll_alternating``, and the emoji are ``:baseball.ball:`` plus a
logo per team (``:baseball.phi:``).
"""

from led_ticker_baseball import _logos
from led_ticker_baseball.attendance import MLBAttendanceMonitor
from led_ticker_baseball.emoji import BALL, BALL_HIRES
from led_ticker_baseball.promotions import MLBPromotionsMonitor
from led_ticker_baseball.scores import MLBScoreMonitor
from led_ticker_baseball.standings import MLBStandingsMonitor
from led_ticker_baseball.statcast import MLBStatcastMonitor
from led_ticker_baseball.teams import MLB_TEAM_NAMES
from led_ticker_baseball.transition import (
    Baseball,
    BaseballAlternating,
    BaseballReverse,
)


def register(api):
    api.widget("scores")(MLBScoreMonitor)
    api.widget("standings")(MLBStandingsMonitor)
    api.widget("promotions")(MLBPromotionsMonitor)
    api.widget("statcast")(MLBStatcastMonitor)
    api.widget("attendance")(MLBAttendanceMonitor)
    api.transition("roll")(Baseball)
    api.transition("roll_reverse")(BaseballReverse)
    api.transition("roll_alternating")(BaseballAlternating)
    api.emoji("ball", BALL)
    api.hires_emoji("ball", BALL_HIRES)
    # Every bundled team logo is also an inline emoji, e.g. :baseball.phi:.
    for abbrev in MLB_TEAM_NAMES:
        pair = _logos.emoji(abbrev)
        if pair is not None:
            api.emoji(abbrev.lower(), pair[0])
            api.hires_emoji(abbrev.lower(), pair[1])
