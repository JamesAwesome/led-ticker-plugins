import unittest.mock as mock

import pytest

from led_ticker_stocks.layouts import LAYOUTS, resolve_layout
from led_ticker_stocks.layouts.crawl import draw_crawl_story
from led_ticker_stocks.model import SymbolQuote
from led_ticker_stocks.state import MarketState


def _stub_canvas(width=160):
    c = mock.Mock()
    c.width = width
    c.height = 16
    c.scale = 1
    return c


def test_resolve_layout_defaults_by_width():
    assert resolve_layout(_stub_canvas(160), None) == "crawl"


def test_resolve_layout_override_wins():
    assert resolve_layout(_stub_canvas(160), "crawl") == "crawl"


def test_resolve_layout_unregistered_override_raises():
    with pytest.raises(ValueError):
        resolve_layout(_stub_canvas(160), "dashboard")  # not registered until Task 5


def test_resolve_layout_wide_canvas_defaults_to_card():
    assert resolve_layout(_stub_canvas(256), None) == "card"


def test_crawl_registered():
    assert LAYOUTS["crawl"] is draw_crawl_story


def test_draw_crawl_advances_cursor():
    c = _stub_canvas()
    q = SymbolQuote(sym="AAPL", price=317.31, prev=315.32, d=1.99, dp=0.6311)
    end = draw_crawl_story(c, q, MarketState.OPEN, 0, frame=0)
    assert end > 0  # cursor moved right past the drawn segment + padding


def test_crawl_no_data_does_not_crash():
    c = _stub_canvas()
    q = SymbolQuote(sym="ZZZZ", price=0.0, prev=0.0)
    end = draw_crawl_story(c, q, MarketState.CLOSED, 0, frame=0)
    assert end > 0


def test_crawl_flat_change_draws_middle_dot():
    c = _stub_canvas()
    q = SymbolQuote(sym="FLAT", price=100.0, prev=100.0, d=0.0, dp=0.0)
    end = draw_crawl_story(c, q, MarketState.OPEN, 0, frame=0)
    assert end > 0
