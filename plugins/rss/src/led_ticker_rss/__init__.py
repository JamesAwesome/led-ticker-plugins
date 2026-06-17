"""led-ticker-feeds: data-feed widgets contributed via the
``led_ticker.plugins`` entry point.

The entry-point name ``feeds`` is the plugin namespace, so the RSS widget is
``type = "feeds.rss"`` in config.toml. Weather is planned for this repo and
will register as ``feeds.weather`` with one more ``api.widget`` line below.
"""

from led_ticker_feeds.rss import RSSFeedMonitor


def register(api):
    api.widget("rss")(RSSFeedMonitor)
