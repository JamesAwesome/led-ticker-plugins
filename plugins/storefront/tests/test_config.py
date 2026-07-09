from zoneinfo import ZoneInfo

import pytest
from led_ticker.plugin import ColorProviderBase

from led_ticker_storefront.config import enabled, parse_config


def test_enabled_gate():
    assert enabled({}) is False
    assert enabled({"open": {"text": "OPEN"}}) is True


def test_defaults():
    cfg = parse_config({"schedule": {"mon": "09:00-17:00"}})
    assert cfg.open.text == "OPEN"
    assert cfg.closed.text == "CLOSED"
    assert isinstance(cfg.open.color, ColorProviderBase)
    assert isinstance(cfg.closed.color, ColorProviderBase)
    assert cfg.background == (0, 0, 0)          # opaque black default
    assert cfg.font_size == 16
    assert cfg.open.corner == "top_right"       # shared default
    assert cfg.open.orientation == "horizontal"
    assert cfg.tz is None
    assert cfg.schedule["mon"] == [(540, 1020)]


def test_shared_corner_orientation_fallback():
    cfg = parse_config({"corner": "bottom_left", "orientation": "vertical"})
    assert cfg.open.corner == "bottom_left"
    assert cfg.closed.corner == "bottom_left"
    assert cfg.open.orientation == "vertical"


def test_per_state_override():
    cfg = parse_config({
        "corner": "top_right",
        "open": {"corner": "top_left", "orientation": "vertical"},
    })
    assert cfg.open.corner == "top_left"
    assert cfg.open.orientation == "vertical"
    assert cfg.closed.corner == "top_right"     # inherits shared


def test_background_none_is_transparent():
    cfg = parse_config({"background": "none"})
    assert cfg.background is None


def test_background_color():
    cfg = parse_config({"background": [10, 20, 30]})
    assert cfg.background == (10, 20, 30)


def test_color_provider_shorthand():
    cfg = parse_config({"open": {"color": "shimmer"}})
    assert cfg.open.color.frame_invariant is False   # shimmer animates


def test_timezone_parsed():
    cfg = parse_config({"timezone": "America/New_York"})
    assert cfg.tz == ZoneInfo("America/New_York")


def test_bad_corner_raises():
    with pytest.raises(ValueError):
        parse_config({"corner": "middle"})


def test_bad_orientation_raises():
    with pytest.raises(ValueError):
        parse_config({"open": {"orientation": "diagonal"}})


def test_bad_timezone_raises():
    with pytest.raises(Exception):  # noqa: B017 - zoneinfo raises its own subclass
        parse_config({"timezone": "Mars/Olympus"})


def test_bad_schedule_raises():
    with pytest.raises(ValueError):
        parse_config({"schedule": {"mon": "9-5"}})
