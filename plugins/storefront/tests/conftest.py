import pytest
from led_ticker.plugin import HeadlessCanvas


@pytest.fixture
def real_canvas():
    """A bigsign-sized software canvas (256x64) standing in for the real panel."""
    return HeadlessCanvas(256, 64)


@pytest.fixture
def small_canvas():
    """A smallsign-sized software canvas (160x16)."""
    return HeadlessCanvas(160, 16)
