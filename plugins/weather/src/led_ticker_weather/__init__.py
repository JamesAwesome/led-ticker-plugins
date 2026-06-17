"""led-ticker-feeds: data-feed widgets contributed via the
``led_ticker.plugins`` entry point.

The entry-point name ``feeds`` is the plugin namespace, so widgets are
``type = "feeds.rss"`` and ``type = "feeds.weather"`` in config.toml.
"""

from led_ticker_feeds.rss import RSSFeedMonitor
from led_ticker_feeds.weather import WeatherWidget


def register(api):
    api.widget("rss")(RSSFeedMonitor)
    api.widget("weather")(WeatherWidget)
