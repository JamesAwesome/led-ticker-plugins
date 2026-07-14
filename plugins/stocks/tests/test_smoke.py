"""Smoke test: the package registers a `stocks` plugin via the ENTRY-POINT channel."""

from led_ticker import _plugin_loader as L


def test_entry_point_registers_stocks_namespace():
    L.reset_plugins()
    try:
        result = L.load_plugins(None, entry_points_enabled=True)
        loaded = {info.namespace for info in result.loaded}
        assert "stocks" in loaded, (
            f"stocks plugin not discovered via entry point: {result}"
        )

        from led_ticker.widgets import get_widget_class

        assert get_widget_class("stocks.ticker") is not None
    finally:
        L.reset_plugins()
