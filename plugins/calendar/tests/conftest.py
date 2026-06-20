"""Shared test fixtures for the led-ticker-calendar plugin test suite.

The ported scores/scoreboard tests came from core, where a ``canvas`` fixture
(a simple Mock with width/height) lives in core's ``tests/conftest.py``. The
plugin doesn't ship core's conftest, so re-provide the same fixture here. The
rgbmatrix stub is already on the pytest path via ``pythonpath`` in
``pyproject.toml`` (``../led-ticker/tests/stubs``).
"""

import unittest.mock as mock

import pytest


@pytest.fixture
def canvas():
    """Mock LED canvas with standard width and height."""
    c = mock.Mock()
    c.width = 160
    c.height = 16
    return c


@pytest.fixture
def make_widget():
    """Factory for mock widgets with configurable draw width.

    Mirrors core's ``tests/conftest.py`` fixture; the ported baseball
    transition tests came from core and depend on it.
    """

    def _factory(content_width=40):
        widget = mock.Mock()
        widget.hold_time = 0.0
        widget.draw.side_effect = lambda c, cursor_pos=0, **kw: (
            c,
            cursor_pos + content_width,
        )
        return widget

    return _factory
