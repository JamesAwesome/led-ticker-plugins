import pytest
from led_ticker import _plugin_loader as L
from led_ticker.transitions import get_transition_class

_NYANCAT_TRANSITIONS = (
    "nyancat.forward",
    "nyancat.reverse",
    "nyancat.alternating",
)


def test_entry_point_registers_nyancat_namespace():
    L.reset_plugins()
    try:
        result = L.load_plugins(None, entry_points_enabled=True)
        loaded = {info.namespace for info in result.loaded}
        assert "nyancat" in loaded, f"nyancat plugin not discovered: {result}"

        for name in _NYANCAT_TRANSITIONS:
            assert get_transition_class(name) is not None
    finally:
        L.reset_plugins()


def test_bogus_nyancat_name_does_not_resolve():
    """Confirm the check has teeth — an invented name raises ValueError."""
    L.reset_plugins()
    try:
        L.load_plugins(None, entry_points_enabled=True)
        with pytest.raises(ValueError, match="nyancat.nope"):
            get_transition_class("nyancat.nope")
    finally:
        L.reset_plugins()
