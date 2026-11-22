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


# --- Display fonts (flair namespace) -------------------------------------
import hashlib  # noqa: E402

import led_ticker_flair.flair  # noqa: E402

_FONT_SHA256 = {
    "BungeeShade-Regular.ttf": "665c626082682b462f4e696308eafa7071c114da8f8ff3fb73a289c7ff7df482",
    "BungeeOutline-Regular.ttf": "9232000ff85fdbb68987007305f2de877486d63d31450f81b403461bbe721f1f",
    "LondrinaShadow-Regular.ttf": "bdc4a66213c2bed3a0e58912bb2e47f7b0ea51b07d291a43896eed5c87e01a21",
    "LondrinaOutline-Regular.ttf": "773c655bc6a2e9b699cfa8c4a5f615c6348686d018281bb8e6cdc470b2f05f4d",
}


def _fonts() -> Path:
    return Path(led_ticker_flair.flair.__file__).resolve().parent / "fonts"


def test_display_fonts_and_licences_present():
    """The four OFL display fonts ship unmodified (sha256-pinned) with one
    licence file per family and a SOURCES.md naming where they came from."""
    d = _fonts()
    for name, digest in _FONT_SHA256.items():
        assert (d / name).is_file(), f"missing {name}"
        assert hashlib.sha256((d / name).read_bytes()).hexdigest() == digest, name
    for fam in ("BungeeShade", "BungeeOutline", "LondrinaShadow", "LondrinaOutline"):
        lic = d / f"OFL-{fam}.txt"
        assert lic.is_file(), f"missing {lic.name}"
        assert "SIL OPEN FONT LICENSE" in lic.read_text(encoding="utf-8")
    assert "google/fonts" in (d / "SOURCES.md").read_text()
