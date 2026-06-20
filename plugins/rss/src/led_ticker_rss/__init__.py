"""led-ticker-rss: RSS/Atom headline widget (rss.feed) contributed via the
``led_ticker.plugins`` entry point.

The entry-point name ``rss`` is the plugin namespace, so the widget is
referenced in config.toml as ``type = "rss.feed"``.
"""

from led_ticker_rss.rss import RSSFeedMonitor


def register(api):
    api.widget("feed")(RSSFeedMonitor)
