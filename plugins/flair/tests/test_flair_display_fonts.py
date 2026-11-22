"""The flair namespace ships four OFL display fonts as `flair.<Name>` with a
plugin-declared default font_threshold of 45 (core plugin API (1, 3)); on an
older core they still register, at the loader default, with ONE warning."""

import logging
from pathlib import Path
from unittest import mock

import pytest
from led_ticker import _plugin_loader as L
from led_ticker.fonts import (
    list_available_hires_fonts,
)  # test-only; not on the plugin surface
from led_ticker.plugin import HiresFont, default_threshold, resolve_font

NAMES = ["BungeeShade", "BungeeOutline", "LondrinaShadow", "LondrinaOutline"]
FILES = {n: f"{n}-Regular.ttf" for n in NAMES}


@pytest.fixture
def loaded():
    L.reset_plugins()
    try:
        result = L.load_plugins(None, entry_points_enabled=True)
        assert not result.failed, result.failed
        yield
    finally:
        L.reset_plugins()


@pytest.mark.parametrize("name", NAMES)
def test_font_resolves_as_hires_with_threshold_45(loaded, name):
    font = resolve_font(f"flair.{name}", size=48)
    assert isinstance(font, HiresFont)
    assert font.threshold == 45
    assert default_threshold(f"flair.{name}") == 45
    assert f"flair.{name}" in list_available_hires_fonts()


def test_registered_paths_exist(loaded):
    from led_ticker.fonts import hires_loader

    for name in NAMES:
        assert Path(hires_loader._PLUGIN_FONTS[f"flair.{name}"]).is_file()


def test_plugin_names_are_namespaced_and_do_not_shadow_user_stems(loaded):
    # A sign may also carry config/fonts/BungeeShade-Regular.ttf (threshold 128).
    assert "flair.BungeeShade" in list_available_hires_fonts()
    assert default_threshold("BungeeShade-Regular") == 128


def test_new_core_registers_three_arg_no_warning(caplog):
    from led_ticker_flair.flair.display_fonts import register_display_fonts

    api = mock.Mock()
    with caplog.at_level(logging.WARNING, logger="led_ticker_flair"):
        register_display_fonts(api)
    assert api.font.call_args_list == [
        mock.call(n, f"fonts/{FILES[n]}", threshold=45) for n in NAMES
    ]
    assert not [r for r in caplog.records if r.levelno == logging.WARNING]


def test_old_core_registers_two_arg_and_warns_once(caplog, monkeypatch):
    from led_ticker_flair.flair import display_fonts

    monkeypatch.setattr(display_fonts, "API_VERSION", (1, 2))
    api = mock.Mock()
    with caplog.at_level(logging.WARNING, logger="led_ticker_flair"):
        display_fonts.register_display_fonts(api)
    assert api.font.call_args_list == [mock.call(n, f"fonts/{FILES[n]}") for n in NAMES]
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "font_threshold = 45" in warnings[0].getMessage()
