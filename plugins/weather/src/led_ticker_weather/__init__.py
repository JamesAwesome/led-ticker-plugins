"""led-ticker-weather: current-conditions widget (weather.current) contributed
via the ``led_ticker.plugins`` entry point.

The entry-point name ``weather`` is the plugin namespace, so the widget is
referenced in config.toml as ``type = "weather.current"``.
"""

from led_ticker_weather.source import WeatherSource
from led_ticker_weather.weather import WeatherWidget


def register(api):
    api.widget("current")(WeatherWidget)
    api.source("current")(WeatherSource)
