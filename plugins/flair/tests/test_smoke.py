"""One installed led-ticker-flair wheel registers all four homage namespaces
via four entry points (the crux of the pack consolidation)."""

import pytest
from led_ticker import _plugin_loader as L
from led_ticker.pixel_emoji import EMOJI_REGISTRY, HIRES_REGISTRY
from led_ticker.transitions import get_transition_class

_NAMESPACES = {"nyancat", "pokeball", "pacman", "sailor_moon"}
_TRANSITIONS = [
    f"{fam}.{variant}"
    for fam in _NAMESPACES
    for variant in ("forward", "reverse", "alternating")
]


def test_one_wheel_registers_all_four_namespaces():
    L.reset_plugins()
    try:
        result = L.load_plugins(None, entry_points_enabled=True)
        loaded = {info.namespace for info in result.loaded}
        missing = _NAMESPACES - loaded
        assert loaded >= _NAMESPACES, f"missing namespaces: {missing} ({result})"
        for name in _TRANSITIONS:
            assert get_transition_class(name) is not None, f"{name} did not resolve"
    finally:
        L.reset_plugins()


def test_pokeball_emoji_registers():
    L.reset_plugins()
    try:
        L.load_plugins(None, entry_points_enabled=True)
        assert "pokeball.ball" in EMOJI_REGISTRY
        assert "pokeball.ball" in HIRES_REGISTRY
    finally:
        L.reset_plugins()


def test_bogus_name_does_not_resolve():
    L.reset_plugins()
    try:
        L.load_plugins(None, entry_points_enabled=True)
        with pytest.raises(ValueError, match="nyancat.nope"):
            get_transition_class("nyancat.nope")
    finally:
        L.reset_plugins()
