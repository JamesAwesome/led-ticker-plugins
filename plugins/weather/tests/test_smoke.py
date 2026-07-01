from led_ticker import _plugin_loader as L


def test_entry_point_registers_weather_namespace():
    L.reset_plugins()
    try:
        result = L.load_plugins(None, entry_points_enabled=True)
        loaded = {info.namespace for info in result.loaded}
        assert "weather" in loaded, f"weather plugin not discovered: {result}"

        from led_ticker.widgets import get_widget_class

        assert get_widget_class("weather.current") is not None

        # source registered under the same namespace
        from led_ticker.app.factories import get_source_class

        assert get_source_class("weather.current") is not None
    finally:
        L.reset_plugins()
