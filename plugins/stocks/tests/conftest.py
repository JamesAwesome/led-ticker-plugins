"""Shared test fixtures."""

import unittest.mock as mock

import pytest

from led_ticker_stocks._cache import get_cache


@pytest.fixture
def canvas():
    """Mock smallsign LED canvas (160x16, scale 1)."""
    c = mock.Mock()
    c.width = 160
    c.height = 16
    c.scale = 1
    return c


@pytest.fixture(autouse=True)
def _reset_quote_cache():
    """Keep the process-wide QuoteCache singleton hermetic across tests.

    Any test (widget or cache-level) that touches `stocks.ticker` may reach
    the shared cache; without a reset before AND after, symbol registration
    and a spawned poll task can leak between tests.
    """
    get_cache().reset()
    yield
    get_cache().reset()
