"""One installed led-ticker-flair wheel registers all five namespaces via five
entry points (the crux of the pack consolidation): four sprite-trail families
plus the flair animation namespace."""

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


def test_one_wheel_registers_all_four_sprite_namespaces():
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


# ---------------------------------------------------------------------------
# flair namespace registration: blink, twinkle, snow (Task 8)
# ---------------------------------------------------------------------------


class _RecordingAPI:
    """Minimal PluginAPI stand-in recording every surface register() touches."""

    def __init__(self) -> None:
        self.animations: dict[str, type] = {}
        self.transitions: dict[str, type] = {}
        self.widgets: dict[str, type] = {}
        self.borders: dict[str, type] = {}
        self.backgrounds: dict[str, type] = {}

    @staticmethod
    def _deco(bucket: dict[str, type], name: str):
        def deco(cls):
            bucket[name] = cls
            return cls

        return deco

    def animation(self, name: str):
        return self._deco(self.animations, name)

    def transition(self, name: str):
        return self._deco(self.transitions, name)

    def widget(self, name: str):
        return self._deco(self.widgets, name)

    def border(self, name: str):
        return self._deco(self.borders, name)

    def background(self, name: str):
        return self._deco(self.backgrounds, name)


def test_flair_register_adds_blink_twinkle_snow():
    from led_ticker_flair.flair import register  # noqa: PLC0415

    api = _RecordingAPI()
    register(api)
    assert "blink" in api.animations
    assert "twinkle" in api.animations
    assert "twinkle" in api.backgrounds
    assert "snow" in api.backgrounds
    assert "snow" in api.transitions


def test_import_seam_requires_pixel_gain(monkeypatch):
    import dataclasses  # noqa: PLC0415

    import led_ticker.plugin as plugin  # noqa: PLC0415

    from led_ticker_flair.flair import register  # noqa: PLC0415

    @dataclasses.dataclass
    class _OldAnimationFrame:
        visible_text: str
        rotation: float = 0.0
        lens: object = None

    monkeypatch.setattr(plugin, "AnimationFrame", _OldAnimationFrame)
    with pytest.raises(ImportError, match="4.33"):
        register(_RecordingAPI())
