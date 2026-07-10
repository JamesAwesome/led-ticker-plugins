"""Parse the [storefront] TOML block into typed specs. Per-state corner /
orientation fall back to the shared [storefront] values; color accepts a flat
color or a color provider (shimmer/rainbow/...)."""

from zoneinfo import ZoneInfo

import attrs
from led_ticker.plugin import (
    FONT_DEFAULT,
    ColorProvider,
    as_color_provider,
    coerce_color_provider,
    make_color,
    resolve_font,
)

from led_ticker_storefront.schedule import parse_schedule

CORNERS = ("top_left", "top_right", "bottom_left", "bottom_right")
ORIENTATIONS = ("horizontal", "vertical")

_DEFAULT_OPEN = (0, 255, 0)
_DEFAULT_CLOSED = (255, 0, 0)


@attrs.define
class BadgeSpec:
    text: str
    color: ColorProvider
    corner: str
    orientation: str


@attrs.define
class StorefrontConfig:
    open: BadgeSpec
    closed: BadgeSpec
    background: tuple | None
    padding: int
    font_name: str | None
    font_size: int
    font: object
    tz: ZoneInfo | None
    schedule: dict


def enabled(block):
    return bool(block)


def _validate_choice(value, choices, field):
    if value not in choices:
        raise ValueError(f"storefront.{field} must be one of {choices}; got {value!r}")
    return value


def _badge(state_block, default_text, default_rgb, shared_corner, shared_orient, name):
    text = str(state_block.get("text", default_text))
    provider = coerce_color_provider(
        state_block.get("color"), f"storefront.{name}.color"
    ) or as_color_provider(make_color(*default_rgb))
    corner = _validate_choice(
        state_block.get("corner", shared_corner), CORNERS, f"{name}.corner"
    )
    orient = _validate_choice(
        state_block.get("orientation", shared_orient),
        ORIENTATIONS,
        f"{name}.orientation",
    )
    return BadgeSpec(text=text, color=provider, corner=corner, orientation=orient)


def _background(value):
    if value is None:
        return (0, 0, 0)
    if isinstance(value, str) and value.strip().lower() == "none":
        return None
    rgb = tuple(int(c) for c in value)
    if len(rgb) != 3:
        raise ValueError(
            f"storefront.background must be exactly 3 ints (r, g, b); got {value!r}"
        )
    if not all(0 <= c <= 255 for c in rgb):
        raise ValueError(
            f"storefront.background values must each be 0-255; got {value!r}"
        )
    return rgb


def parse_config(block):
    shared_corner = _validate_choice(
        block.get("corner", "top_right"), CORNERS, "corner"
    )
    shared_orient = _validate_choice(
        block.get("orientation", "horizontal"), ORIENTATIONS, "orientation"
    )
    tz_name = block.get("timezone")
    tz = ZoneInfo(tz_name) if tz_name else None
    font_name = block.get("font")
    font_size = int(block.get("font_size", 16))
    if font_size < 1:
        raise ValueError(f"storefront.font_size must be >= 1; got {font_size!r}")
    padding = int(block.get("padding", 2))
    if padding < 0:
        raise ValueError(f"storefront.padding must be >= 0; got {padding!r}")
    font = FONT_DEFAULT if font_name is None else resolve_font(font_name, font_size)
    return StorefrontConfig(
        open=_badge(
            block.get("open", {}),
            "OPEN",
            _DEFAULT_OPEN,
            shared_corner,
            shared_orient,
            "open",
        ),
        closed=_badge(
            block.get("closed", {}),
            "CLOSED",
            _DEFAULT_CLOSED,
            shared_corner,
            shared_orient,
            "closed",
        ),
        background=_background(block.get("background")),
        padding=padding,
        font_name=font_name,
        font_size=font_size,
        font=font,
        tz=tz,
        schedule=parse_schedule(block.get("schedule", {})),
    )
