"""Bundled sprite assets must ship with the led-ticker-flair wheel.

Only nyancat and pokeball bundle sprite files; pacman and sailor_moon render
from inline pixel data (no sprites/ dir) and are intentionally not asserted here.
"""

from pathlib import Path

import led_ticker_flair.nyancat
import led_ticker_flair.pokeball


def _sprites(mod) -> Path:
    return Path(mod.__file__).resolve().parent / "sprites"


def test_nyancat_sprite_present():
    assert (_sprites(led_ticker_flair.nyancat) / "nyancat.webp").is_file()


def test_pokeball_sprites_present():
    d = _sprites(led_ticker_flair.pokeball)
    for f in ("pokeball-pikachu.gif", "pokeball.gif", "pikachu-run-transparent.gif"):
        assert (d / f).is_file(), f"missing {f}"
