"""led-ticker-flight: planes-overhead ADS-B tracker (flight.overhead).

The entry-point name ``flight`` is the plugin namespace, so the widget is
referenced in config.toml as ``type = "flight.overhead"``.
"""


def register(api):
    # Widget wired in the widget task; keeping register importable from day one.
    pass
