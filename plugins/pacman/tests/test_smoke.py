import pytest
from led_ticker import _plugin_loader as L
from led_ticker.transitions import get_transition_class

_PACMAN_TRANSITIONS = (
    "pacman.forward",
    "pacman.reverse",
    "pacman.alternating",
)


def test_entry_point_registers_pacman_namespace():
    L.reset_plugins()
    try:
        result = L.load_plugins(None, entry_points_enabled=True)
        loaded = {info.namespace for info in result.loaded}
        assert "pacman" in loaded, f"pacman plugin not discovered: {result}"

        for name in _PACMAN_TRANSITIONS:
            assert get_transition_class(name) is not None
    finally:
        L.reset_plugins()


def test_bogus_pacman_name_does_not_resolve():
    """Confirm the check has teeth — an invented name raises ValueError."""
    L.reset_plugins()
    try:
        L.load_plugins(None, entry_points_enabled=True)
        with pytest.raises(ValueError, match="pacman.nope"):
            get_transition_class("pacman.nope")
    finally:
        L.reset_plugins()
