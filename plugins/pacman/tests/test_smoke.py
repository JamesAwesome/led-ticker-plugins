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

_HIRES_TRANSITIONS = (
    "arcade.nyancat",
    "arcade.nyancat_reverse",
    "arcade.nyancat_alternating",
    "arcade.pokeball",
    "arcade.pokeball_reverse",
    "arcade.pokeball_alternating",
)


def test_entry_point_registers_arcade_namespace():
    L.reset_plugins()
    try:
        result = L.load_plugins(None, entry_points_enabled=True)
        loaded = {info.namespace for info in result.loaded}
        assert "arcade" in loaded, f"arcade plugin not discovered: {result}"

        for name in _ARCADE_TRANSITIONS:
            assert get_transition_class(name) is not None

        for name in _HIRES_TRANSITIONS:
            assert get_transition_class(name) is not None

        # pokeball emoji registered (lowres + hires) under the arcade namespace.
        # The loader merges api._buffers["emojis"] → EMOJI_REGISTRY and
        # api._buffers["hires_emojis"] → HIRES_REGISTRY using _qualify(), so
        # the key is the namespaced slug "arcade.pokeball".
        from led_ticker.pixel_emoji import EMOJI_REGISTRY, HIRES_REGISTRY

        assert "arcade.pokeball" in EMOJI_REGISTRY
        assert "arcade.pokeball" in HIRES_REGISTRY

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
