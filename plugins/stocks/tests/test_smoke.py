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

        # source registered under the same namespace
        from led_ticker.app.factories import get_source_class

        assert get_source_class("stocks.quote") is not None

        # color provider registered under the same namespace
        from led_ticker.color_providers import _PROVIDER_REGISTRY

        assert "stocks.trend" in _PROVIDER_REGISTRY

        # and it coerces from an inline font_color table
        from led_ticker.app.coercion import _coerce_color_provider

        prov = _coerce_color_provider({"style": "stocks.trend", "symbol": "AAPL"})
        assert prov is not None and prov.symbol == "AAPL"
    finally:
        L.reset_plugins()
