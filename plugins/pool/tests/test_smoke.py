"""Smoke test: the package registers a `pool` plugin via the ENTRY-POINT channel.

This is the strongest validation of the installed-plugin path — it proves
led-ticker discovers this package through `importlib.metadata.entry_points`
(not a local plugins dir), binds the `pool` namespace, and registers
`pool.monitor`.
"""

from led_ticker import _plugin_loader as L


def test_entry_point_registers_pool_namespace():
    L.reset_plugins()
    try:
        # entry_points_enabled=True picks up this installed package's
        # [project.entry-points."led_ticker.plugins"] pool = "led_ticker_pool:register"
        result = L.load_plugins(None, entry_points_enabled=True)
        loaded = {info.namespace for info in result.loaded}
        assert "pool" in loaded, f"pool plugin not discovered via entry point: {result}"

        from led_ticker.widgets import get_widget_class

        assert get_widget_class("pool.monitor") is not None
    finally:
        L.reset_plugins()
