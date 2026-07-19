"""Shared pytest fixtures for led-ticker-flair tests."""

from unittest import mock

import pytest


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


@pytest.fixture(autouse=True, scope="session")
def _prewarm_poker_geometry():
    """Warm ALL poker suit geometry synchronously before any test runs, so
    the background warm introduced for the first-firing stall never has a
    live thread during tests (a mid-test thread would pollute the mask-spy
    counts in TestNoPerFiringRasterization)."""
    from led_ticker_flair.flair import poker

    poker._warm_worker(list(poker.SUITS), yield_s=0)
    poker._warm_dispatched.update(poker.SUITS)
    yield
