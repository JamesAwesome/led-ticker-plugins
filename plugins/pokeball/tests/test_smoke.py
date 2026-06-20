import pytest
from led_ticker import _plugin_loader as L
from led_ticker.transitions import get_transition_class

_POKEBALL_TRANSITIONS = (
    "pokeball.forward",
    "pokeball.reverse",
    "pokeball.alternating",
)


def test_entry_point_registers_pokeball_namespace():
    L.reset_plugins()
    try:
        result = L.load_plugins(None, entry_points_enabled=True)
        loaded = {info.namespace for info in result.loaded}
        assert "pokeball" in loaded, f"pokeball plugin not discovered: {result}"

        for name in _POKEBALL_TRANSITIONS:
            assert get_transition_class(name) is not None

        # pokeball emoji registered (lowres + hires). The loader merges
        # api._buffers["emojis"] → EMOJI_REGISTRY and
        # api._buffers["hires_emojis"] → HIRES_REGISTRY using _qualify(), so the
        # key is the namespaced slug "pokeball.ball".
        from led_ticker.pixel_emoji import EMOJI_REGISTRY, HIRES_REGISTRY

        assert "pokeball.ball" in EMOJI_REGISTRY
        assert "pokeball.ball" in HIRES_REGISTRY
    finally:
        L.reset_plugins()


def test_bogus_pokeball_name_does_not_resolve():
    """Confirm the check has teeth — an invented name raises ValueError."""
    L.reset_plugins()
    try:
        L.load_plugins(None, entry_points_enabled=True)
        with pytest.raises(ValueError, match="pokeball.nope"):
            get_transition_class("pokeball.nope")
    finally:
        L.reset_plugins()
