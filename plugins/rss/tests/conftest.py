"""Shared test fixtures for the led-ticker-feeds plugin test suite.

The rgbmatrix stub is on the pytest path via ``pythonpath`` in
``pyproject.toml`` (``../led-ticker/tests/stubs``). The plugin doesn't ship
core's conftest, so re-provide the small fixtures the ported tests use.
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
