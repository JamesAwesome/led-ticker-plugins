import pytest
from led_ticker import _plugin_loader as L
from led_ticker.transitions import get_transition_class

_ARCADE_TRANSITIONS = (
    "arcade.pacman",
    "arcade.pacman_reverse",
    "arcade.pacman_alternating",
    "arcade.sailor_moon",
    "arcade.sailor_moon_reverse",
    "arcade.sailor_moon_alternating",
)


def test_entry_point_registers_arcade_namespace():
    L.reset_plugins()
    try:
        result = L.load_plugins(None, entry_points_enabled=True)
        loaded = {info.namespace for info in result.loaded}
        assert "arcade" in loaded, f"arcade plugin not discovered: {result}"

        for name in _ARCADE_TRANSITIONS:
            assert get_transition_class(name) is not None

    finally:
        L.reset_plugins()


def test_bogus_arcade_name_does_not_resolve():
    """Confirm the check has teeth — an invented name raises ValueError."""
    L.reset_plugins()
    try:
        L.load_plugins(None, entry_points_enabled=True)
        with pytest.raises(ValueError, match="arcade.nope"):
            get_transition_class("arcade.nope")
    finally:
        L.reset_plugins()
