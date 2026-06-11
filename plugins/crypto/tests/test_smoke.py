"""Smoke test: the package registers a `crypto` plugin via the ENTRY-POINT channel."""

from led_ticker import _plugin_loader as L


def test_entry_point_registers_crypto_namespace():
    L.reset_plugins()
    try:
        result = L.load_plugins(None, entry_points_enabled=True)
        loaded = {info.namespace for info in result.loaded}
        assert "crypto" in loaded, (
            f"crypto plugin not discovered via entry point: {result}"
        )

        from led_ticker.widgets import get_widget_class

        assert get_widget_class("crypto.coingecko") is not None
    finally:
        L.reset_plugins()
