"""The bundled hi-res sprite asset must ship with the package."""

from pathlib import Path

import led_ticker_flair.nyancat


def test_nyancat_sprite_present():
    base = Path(led_ticker_flair.nyancat.__file__).resolve().parent
    p = base / "sprites" / "nyancat.webp"
    assert p.is_file(), f"missing bundled sprite: {p}"
