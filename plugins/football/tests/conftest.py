"""Shared fixtures for the led-ticker-football test suite.

Real headless canvases come from `led_ticker.plugin`: smallsign 160x16 scale 1;
bigsign 256x64 and longboi 512x64 wrapped at scale 4 (16 logical rows).
"""

from zoneinfo import ZoneInfo

import pytest
from led_ticker.plugin import HeadlessBackend, ScaledCanvas

TZ = ZoneInfo("America/New_York")


@pytest.fixture
def tz():
    return TZ


@pytest.fixture
def smallsign():
    return HeadlessBackend(160, 16).create_canvas()


@pytest.fixture
def bigsign():
    real = HeadlessBackend(256, 64).create_canvas()
    return ScaledCanvas(real, scale=4, content_height=16)


@pytest.fixture
def longboi():
    real = HeadlessBackend(512, 64).create_canvas()
    return ScaledCanvas(real, scale=4, content_height=16)


@pytest.fixture(autouse=True)
def reset_sources():
    from led_ticker_football._source import _SHARED_SOURCES

    _SHARED_SOURCES.clear()
    yield
    _SHARED_SOURCES.clear()


@pytest.fixture
def synthetic_logo_png() -> bytes:
    import io

    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((4, 4, 60, 60), fill=(0, 107, 182, 255))
    draw.rectangle((2, 2, 5, 5), fill=(20, 20, 20, 255))
    draw.rectangle((58, 2, 61, 5), fill=(255, 255, 255, 60))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
