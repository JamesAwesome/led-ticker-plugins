"""led-ticker-football: live NFL scores for led-ticker, contributed via the
``led_ticker.plugins`` entry point.

The entry-point name ``football`` is the plugin namespace, so the widget is
``type = "football.scores"``. Data: ESPN's public scoreboard API (no key).
"""

from led_ticker_football.scores import FootballScoreMonitor


def register(api):
    api.widget("scores")(FootballScoreMonitor)
