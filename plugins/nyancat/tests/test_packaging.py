"""The bundled hi-res sprite asset must ship with the package."""

from pathlib import Path

import led_ticker_nyancat


def _sprites_dir() -> Path:
    return Path(led_ticker_nyancat.__file__).resolve().parent / "sprites"


def test_nyancat_sprite_present():
    p = _sprites_dir() / "nyancat.webp"
    assert p.is_file(), f"missing bundled sprite: {p}"
