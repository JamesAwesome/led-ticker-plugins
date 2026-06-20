from led_ticker import _plugin_loader as L


def test_entry_point_registers_baseball_namespace():
    L.reset_plugins()
    try:
        result = L.load_plugins(None, entry_points_enabled=True)
        loaded = {info.namespace for info in result.loaded}
        assert "baseball" in loaded, f"baseball plugin not discovered: {result}"

        from led_ticker.widgets import get_widget_class

        assert get_widget_class("baseball.scores") is not None
        assert get_widget_class("baseball.standings") is not None
        assert get_widget_class("baseball.promotions") is not None
        assert get_widget_class("baseball.statcast") is not None
        assert get_widget_class("baseball.attendance") is not None

        from led_ticker.transitions import get_transition_class

        assert get_transition_class("baseball.roll") is not None
        assert get_transition_class("baseball.roll_reverse") is not None
        assert get_transition_class("baseball.roll_alternating") is not None

        from led_ticker.pixel_emoji import EMOJI_REGISTRY, HIRES_REGISTRY

        assert "baseball.ball" in EMOJI_REGISTRY
        assert "baseball.ball" in HIRES_REGISTRY
    finally:
        L.reset_plugins()
