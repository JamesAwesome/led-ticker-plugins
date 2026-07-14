"""Shared test fixtures."""

import unittest.mock as mock

import pytest


@pytest.fixture
def canvas():
    """Mock smallsign LED canvas (160x16, scale 1)."""
    c = mock.Mock()
    c.width = 160
    c.height = 16
    c.scale = 1
    return c
