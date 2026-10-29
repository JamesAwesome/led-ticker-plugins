"""Bundled team-logo sprites: decoded once, cached, painted at real resolution."""

import functools
import io
import logging
from dataclasses import dataclass
from importlib import resources

from PIL import Image

from led_ticker_football.teams import NFL_TEAMS

logger = logging.getLogger(__name__)

LOGO_ROW = 28  # bigsign: one logo per 32px team row (board and celebration)
LOGO_LONG = 48  # longboi board edges and celebration detail
ALPHA_MIN = 128
DARK_FLOOR = 40


@dataclass(frozen=True)
class LogoSprite:
    size: int
    pixels: tuple[tuple[int, int, int, int, int], ...]


def _read_asset(abbrev: str) -> bytes:
    path = (
        resources.files("led_ticker_football")
        / "assets"
        / "logos"
        / f"{abbrev.upper()}.png"
    )
    return path.read_bytes()


def _decode(data: bytes, size: int) -> LogoSprite:
    img = Image.open(io.BytesIO(data)).convert("RGBA")
    img = img.resize((size, size), Image.Resampling.LANCZOS)
    out = []
    for y in range(size):
        for x in range(size):
            r, g, b, a = img.getpixel((x, y))  # type: ignore[misc]
            if a < ALPHA_MIN:
                continue
            r, g, b = (r * a) // 255, (g * a) // 255, (b * a) // 255
            if max(r, g, b) >= DARK_FLOOR:
                out.append((x, y, r, g, b))
    return LogoSprite(size=size, pixels=tuple(out))


@functools.cache
def sprite(abbrev: str, size: int) -> LogoSprite | None:
    if abbrev not in NFL_TEAMS:
        logger.debug("no logo for unknown team %r", abbrev)
        return None
    try:
        return _decode(_read_asset(abbrev), size)
    except Exception as exc:
        logger.debug("logo %s unavailable: %s", abbrev, exc)
        return None


def paint_logo(real, sprite: LogoSprite, x: int, y: int) -> None:
    """SetPixel each sprite pixel at (x, y) offset, clipped to the canvas."""
    w, h = real.width, real.height
    for px, py, r, g, b in sprite.pixels:
        X, Y = x + px, y + py
        if 0 <= X < w and 0 <= Y < h:
            real.SetPixel(X, Y, r, g, b)
