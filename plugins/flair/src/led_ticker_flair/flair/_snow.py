"""Shared snowflake model for the ``flair.snow`` background and the snow
transition.

Pure functions of ``(i, frame, geometry, seed, ...)``: no ``random`` module,
no mutable state, so a re-rendered frame is identical. Flake ``i`` falls at a
constant speed and wraps vertically; each wrap (``epoch``) re-rolls its
column and brightness, so it re-enters somewhere new.
"""

import functools
import math

from led_ticker.plugin import emoji_slugs

from led_ticker_flair.flair._twinkle import hash32
from led_ticker_flair.flair.stickers import capture_sprite

# Salts for the derived per-flake quantities (distinct per quantity).
SALT_SPEED = 11
SALT_Y0 = 12
SALT_PHASE = 13
SALT_X0 = 14
SALT_INTENSITY = 15

_PLUS = ((1, 0), (0, 1), (1, 1), (2, 1), (1, 2))
_U32 = 2**32


def validate_flake(flake: object) -> None:
    """Raise ``ValueError`` unless ``flake`` is "dot", "plus" or an emoji slug
    with an 8x8 low-res form (shared by the background and the transition)."""
    if not isinstance(flake, str):
        raise ValueError(f"flake must be a string; got {flake!r}")
    if flake not in ("dot", "plus") and (
        flake not in emoji_slugs() or not capture_sprite(flake, 1, None)
    ):
        raise ValueError(
            f'flake {flake!r} is not "dot", "plus" or an emoji slug with an '
            '8x8 low-res form (pack-only slugs have none); use "dot"'
        )


def validate_color(color: object) -> None:
    ok = (
        isinstance(color, list | tuple)
        and len(color) == 3
        and all(
            isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 255
            for v in color
        )
    )
    if not ok:
        raise ValueError(
            f"color must be an [r, g, b] triple of ints 0-255; got {color!r}"
        )


def flake_height(flake: str) -> int:
    """Real-pixel height of a flake's sprite."""
    if flake == "dot":
        return 1
    if flake == "plus":
        return 3
    return max((y for (_x, y), _c in _sprite(flake)), default=-1) + 1


@functools.cache
def _sprite(slug: str) -> tuple[tuple[tuple[int, int], tuple[int, int, int]], ...]:
    return tuple(capture_sprite(slug, 1, None).items())


@functools.cache
def _pixels(flake: str, color: tuple[int, int, int]) -> dict:
    if flake == "dot":
        return {(0, 0): color}
    if flake == "plus":
        return {p: color for p in _PLUS}
    return dict(_sprite(flake))


def flake_pixels(
    flake: str, color: tuple[int, int, int]
) -> dict[tuple[int, int], tuple[int, int, int]]:
    """Bbox-normalized ``{(x, y): rgb}`` for a flake: ``"dot"`` (1 px),
    ``"plus"`` (5-px +), or an emoji slug's 8x8 low-res sprite."""
    return dict(_pixels(flake, tuple(color)))  # type: ignore[arg-type]


def flake_count(width: int, height: int, density: float) -> int:
    return max(1, round(density * width * height / 1000))


def flake_position(
    i: int,
    frame: int,
    w: int,
    h: int,
    seed: int,
    speed: float,
    speed_variation: float,
    drift: float,
    wind: float,
    sprite_h: int,
) -> tuple[int, int, float]:
    """``(x, y, intensity)`` of flake ``i`` at ``frame``; ``y`` is the top row
    (may be negative while entering) and ``intensity`` is in ``[0.5, 1]``."""
    h0 = hash32(i, 0, seed, SALT_SPEED)
    v = h / 100 * speed * (1 + speed_variation * (2 * h0 / _U32 - 1))
    span = h + sprite_h
    y0 = hash32(i, 0, seed, SALT_Y0) / _U32 * span
    phase = hash32(i, 0, seed, SALT_PHASE) / _U32 * 2 * math.pi
    travel = y0 + v * frame
    epoch = int(travel // span)
    y = int(travel % span) - sprite_h
    x0 = hash32(i, epoch, seed, SALT_X0) / _U32 * w
    intensity = 0.5 + 0.5 * hash32(i, epoch, seed, SALT_INTENSITY) / _U32
    x = int(x0 + wind * frame + drift * 3 * math.sin(frame / 10 + phase)) % w
    return x, y, intensity
