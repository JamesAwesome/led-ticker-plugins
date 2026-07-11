"""led-ticker-flight: planes-overhead ADS-B tracker (flight.overhead).

The entry-point name ``flight`` is the plugin namespace, so the widget is
referenced in config.toml as ``type = "flight.overhead"``.
"""

from led_ticker_flight.widget import OverheadWidget


def register(api):
    api.widget("overhead")(OverheadWidget)
