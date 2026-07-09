from led_ticker import _plugin_loader as L


def test_entry_point_registers_storefront_namespace():
    L.reset_plugins()
    try:
        result = L.load_plugins(None, entry_points_enabled=True)
        loaded = {info.namespace for info in result.loaded}
        assert "storefront" in loaded, f"storefront plugin not discovered: {result}"
    finally:
        L.reset_plugins()
