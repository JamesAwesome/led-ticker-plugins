"""Shared test fixtures for the led-ticker-weather plugin test suite.

The plugin doesn't ship core's conftest, so re-provide the small fixtures the
ported tests use.
"""

import unittest.mock as mock

import pytest
from led_ticker.plugin import HeadlessBackend, ScaledCanvas


@pytest.fixture
def canvas():
    """Mock LED canvas with standard width and height."""
    c = mock.Mock()
    c.width = 160
    c.height = 16
    return c


@pytest.fixture
def make_widget():
    """Factory for mock widgets with configurable draw width."""

    def _factory(content_width=40):
        widget = mock.Mock()
        widget.hold_time = 0.0
        widget.draw.side_effect = lambda c, cursor_pos=0, **kw: (
            c,
            cursor_pos + content_width,
        )
        return widget

    return _factory


@pytest.fixture
def smallsign():
    """160x16 scale-1 headless canvas (smallsign geometry)."""
    return HeadlessBackend(160, 16).create_canvas()


@pytest.fixture
def bigsign():
    """256x64 physical wrapped at scale 4 (bigsign geometry)."""
    real = HeadlessBackend(256, 64).create_canvas()
    return ScaledCanvas(real, scale=4, content_height=16)


@pytest.fixture
def longboi():
    """512x64 physical wrapped at scale 4 (longboi geometry)."""
    real = HeadlessBackend(512, 64).create_canvas()
    return ScaledCanvas(real, scale=4, content_height=16)


@pytest.fixture
def lit():
    """Lit pixels [(x, y, (r, g, b)), ...] in a physical region of a
    HeadlessCanvas (get_pixel is the one supported readback)."""

    def _lit(real, x0, y0, x1, y1):
        out = []
        for y in range(y0, y1):
            for x in range(x0, x1):
                p = real.get_pixel(x, y)
                if p != (0, 0, 0):
                    out.append((x, y, p))
        return out

    return _lit
