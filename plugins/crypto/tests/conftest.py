"""Shared test fixtures."""

import unittest.mock as mock

import pytest


@pytest.fixture
def canvas():
    """Mock LED canvas with standard width and height."""
    c = mock.Mock()
    c.width = 160
    c.height = 16
    return c
