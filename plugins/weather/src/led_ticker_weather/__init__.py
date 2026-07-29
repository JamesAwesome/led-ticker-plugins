"""led-ticker-weather: current-conditions widget (weather.current) and
multi-day forecast card (weather.forecast) contributed via the
``led_ticker.plugins`` entry point.

The entry-point name ``weather`` is the plugin namespace, so the widgets
are referenced in config.toml as ``type = "weather.current"`` /
``type = "weather.forecast"``.
"""

from led_ticker_weather.forecast import ForecastWidget
from led_ticker_weather.source import WeatherSource
from led_ticker_weather.weather import WeatherWidget


def register(api):
    api.widget("current")(WeatherWidget)
    api.widget("forecast")(ForecastWidget)
    api.source("current")(WeatherSource)
