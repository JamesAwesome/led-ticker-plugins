from led_ticker import _plugin_loader as L


def test_entry_point_registers_hockey_namespace():
    L.reset_plugins()
    try:
        result = L.load_plugins(None, entry_points_enabled=True)
        loaded = {info.namespace for info in result.loaded}
        assert "hockey" in loaded, f"hockey plugin not discovered: {result}"

        from led_ticker.widgets import get_widget_class

        assert get_widget_class("hockey.scores") is not None

        from led_ticker.plugin import emoji_slugs

        assert "hockey.puck" in emoji_slugs()
    finally:
        L.reset_plugins()
