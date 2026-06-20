import pytest
from led_ticker import _plugin_loader as L
from led_ticker.transitions import get_transition_class

_SAILOR_MOON_TRANSITIONS = (
    "sailor_moon.forward",
    "sailor_moon.reverse",
    "sailor_moon.alternating",
)


def test_entry_point_registers_sailor_moon_namespace():
    L.reset_plugins()
    try:
        result = L.load_plugins(None, entry_points_enabled=True)
        loaded = {info.namespace for info in result.loaded}
        assert "sailor_moon" in loaded, f"sailor_moon plugin not discovered: {result}"

        for name in _SAILOR_MOON_TRANSITIONS:
            assert get_transition_class(name) is not None
    finally:
        L.reset_plugins()


def test_bogus_sailor_moon_name_does_not_resolve():
    """Confirm the check has teeth — an invented name raises ValueError."""
    L.reset_plugins()
    try:
        L.load_plugins(None, entry_points_enabled=True)
        with pytest.raises(ValueError, match="sailor_moon.nope"):
            get_transition_class("sailor_moon.nope")
    finally:
        L.reset_plugins()
