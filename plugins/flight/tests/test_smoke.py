"""Package-level smoke: the entry point target imports and is callable."""

from led_ticker_flight import register
from led_ticker_flight.widget import OverheadWidget


def test_register_is_callable():
    assert callable(register)


def test_register_wires_overhead_widget():
    calls = []

    class _StubAPI:
        def widget(self, name):
            def _decorator(cls):
                calls.append((name, cls))
                return cls

            return _decorator

    register(_StubAPI())
    assert calls == [("overhead", OverheadWidget)]


def test_entry_point_registers_flight_namespace():
    from led_ticker import _plugin_loader as L

    L.reset_plugins()
    try:
        result = L.load_plugins(None, entry_points_enabled=True)
        loaded = {info.namespace for info in result.loaded}
        assert "flight" in loaded, f"flight plugin not discovered: {result}"

        from led_ticker.widgets import get_widget_class

        assert get_widget_class("flight.overhead") is OverheadWidget
    finally:
        L.reset_plugins()
