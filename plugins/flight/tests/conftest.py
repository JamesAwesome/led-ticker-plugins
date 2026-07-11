import pytest
from led_ticker.plugin import HeadlessCanvas, ScaledCanvas


@pytest.fixture
def smallsign():
    """160x16 scale-1: the canvas IS the real canvas."""
    return HeadlessCanvas(160, 16)


@pytest.fixture
def bigsign():
    real = HeadlessCanvas(256, 64)
    return ScaledCanvas(real, scale=4, content_height=16)


@pytest.fixture
def longboi():
    real = HeadlessCanvas(512, 64)
    return ScaledCanvas(real, scale=4, content_height=16)
