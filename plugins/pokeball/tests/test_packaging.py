"""The bundled hi-res sprite assets must ship with the package."""

from pathlib import Path

import led_ticker_arcade


def _sprites_dir() -> Path:
    return Path(led_ticker_arcade.__file__).resolve().parent / "sprites"


def test_nyancat_sprite_present():
    p = _sprites_dir() / "nyancat.webp"
    assert p.is_file(), f"missing bundled sprite: {p}"


def test_pikachu_sprite_present():
    p = _sprites_dir() / "pikachu-run-transparent.gif"
    assert p.is_file(), f"missing bundled sprite: {p}"


def test_pokeball_combined_sprite_present():
    p = _sprites_dir() / "pokeball-pikachu.gif"
    assert p.is_file(), f"missing bundled sprite: {p}"


def test_pokeball_ball_only_sprite_present():
    p = _sprites_dir() / "pokeball.gif"
    assert p.is_file(), f"missing bundled sprite: {p}"
