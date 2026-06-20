"""led-ticker-pool: a pool water-temperature monitor widget for led-ticker.

Contributed via the ``led_ticker.plugins`` entry point. The entry-point name
``pool`` is the plugin namespace, so the widget is ``type = "pool.monitor"``.
"""

from led_ticker_pool.monitor import PoolMonitor


def register(api):
    api.widget("monitor")(PoolMonitor)
