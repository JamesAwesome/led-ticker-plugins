"""Bundled team-logo sprites: decoded once, cached, painted at real resolution."""

import functools
import io
import logging
from dataclasses import dataclass
from importlib import resources

from led_ticker.plugin import HiResEmoji, PixelData
from PIL import Image

from led_ticker_football.teams import NFL_TEAMS

logger = logging.getLogger(__name__)

LOGO_ROW = 28  # bigsign: one logo per 32px team row (board and celebration)
LOGO_LONG = 48  # longboi board edges and celebration detail
EMOJI_HIRES = 32  # :<ns>.<team>: inline emoji, the core inline-sprite height
EMOJI_HIRES_MAX_W = 64
EMOJI_LOWRES = 8  # its lo-res pair (smallsign, and the inline-text gate)
ALPHA_MIN = 128
TINY_ALPHA_MIN = 64  # the 8x8 lo-res emoji (see _decode_fit)
_OPAQUE = [255 if a >= ALPHA_MIN else 0 for a in range(256)]  # alpha -> crop mask
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


def _lit(
    img: Image.Image, alpha_min: int = ALPHA_MIN, premultiply: bool = True
) -> tuple[tuple[int, int, int, int, int], ...]:
    out = []
    for y in range(img.height):
        for x in range(img.width):
            r, g, b, a = img.getpixel((x, y))  # type: ignore[misc]
            if a < alpha_min:
                continue
            if premultiply:
                r, g, b = (r * a) // 255, (g * a) // 255, (b * a) // 255
            if max(r, g, b) >= DARK_FLOOR:
                out.append((x, y, r, g, b))
    return tuple(out)


def _decode(data: bytes, size: int) -> LogoSprite:
    img = Image.open(io.BytesIO(data)).convert("RGBA")
    img = img.resize((size, size), Image.Resampling.LANCZOS)
    return LogoSprite(size=size, pixels=_lit(img))


def _decode_fit(
    data: bytes, height: int, max_w: int, *, tiny: bool = False
) -> LogoSprite:
    """Crop to the visible logo, then fit it in ``max_w`` x ``height`` keeping
    its aspect, centred vertically. A square resize leaves a wide logo (WSH,
    NYJ) a thin strip, and at 8x8 nothing at all. ``tiny`` (the 8x8 lo-res)
    keeps the half-covered edge pixels at full colour, or the thinnest wide
    marks drop to a few dots."""
    img = Image.open(io.BytesIO(data)).convert("RGBA")
    bbox = img.getchannel("A").point(_OPAQUE).getbbox()
    if bbox is not None:
        img = img.crop(bbox)
    k = min(height / img.height, max_w / img.width)
    w, h = max(1, round(img.width * k)), max(1, round(img.height * k))
    img = img.resize((w, h), Image.Resampling.LANCZOS)
    dy = (height - h) // 2
    return LogoSprite(
        size=height,
        pixels=tuple(
            (x, y + dy, r, g, b)
            for x, y, r, g, b in (
                _lit(img, TINY_ALPHA_MIN, premultiply=False) if tiny else _lit(img)
            )
        ),
    )


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


def _trim_x(pixels):
    """Shift lit pixels flush left; return them with the lit width."""
    min_x = min(x for x, *_ in pixels)
    max_x = max(x for x, *_ in pixels)
    return tuple((x - min_x, y, r, g, b) for x, y, r, g, b in pixels), max_x - min_x + 1


@functools.cache
def emoji(abbrev: str) -> tuple[PixelData, HiResEmoji] | None:
    """The team's inline emoji pair, or None when its logo is unavailable.

    Both sprites are trimmed to their lit columns: core auto-trims its own
    hi-res emoji, but plugin hi-res sprites land in the registry as given.
    Never raises (``register`` calls it for every team).
    """
    if abbrev not in NFL_TEAMS:
        return None
    try:
        data = _read_asset(abbrev)
        lo = _decode_fit(data, EMOJI_LOWRES, EMOJI_LOWRES, tiny=True)
        hi = _decode_fit(data, EMOJI_HIRES, EMOJI_HIRES_MAX_W)
    except Exception as exc:
        logger.debug("logo emoji %s unavailable: %s", abbrev, exc)
        return None
    if not lo.pixels or not hi.pixels:
        return None
    lo_pixels, _ = _trim_x(lo.pixels)
    hi_pixels, hi_w = _trim_x(hi.pixels)
    return list(lo_pixels), HiResEmoji(
        pixels=hi_pixels, physical_size=hi.size, physical_width=hi_w
    )
