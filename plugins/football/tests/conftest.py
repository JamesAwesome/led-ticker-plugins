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
