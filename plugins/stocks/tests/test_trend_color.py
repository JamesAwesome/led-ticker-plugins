"""stocks.trend color provider: green up / red down / neutral flat."""

import pytest

from led_ticker_stocks import _cache
from led_ticker_stocks import _palette as pal
from led_ticker_stocks.model import SymbolQuote
from led_ticker_stocks.trend_color import _DEFAULT_FLAT, StocksTrendColor


@pytest.fixture(autouse=True)
def _reset_cache():
    _cache.get_cache().reset()
    yield
    _cache.get_cache().reset()


def _rgb(c):
    return (c.red, c.green, c.blue)


def _seed(symbol, price, prev):
    c = _cache.get_cache()
    c.register([symbol])
    c._quotes[symbol] = SymbolQuote(sym=symbol, price=price, prev=prev)


def test_up_returns_up_color():
    _seed("AAPL", price=110.0, prev=100.0)  # change +10
    assert _rgb(StocksTrendColor(symbol="AAPL").color_for(0, 0, 1)) == _rgb(pal.UP)


def test_down_returns_down_color():
    _seed("AAPL", price=90.0, prev=100.0)  # change -10
    assert _rgb(StocksTrendColor(symbol="AAPL").color_for(0, 0, 1)) == _rgb(pal.DOWN)


def test_flat_change_returns_flat_color():
    _seed("AAPL", price=100.0, prev=100.0)  # change 0
    got = StocksTrendColor(symbol="AAPL").color_for(0, 0, 1)
    assert _rgb(got) == _rgb(_DEFAULT_FLAT)


def test_no_data_returns_flat_and_does_not_raise():
    # never seeded: __init__ registers a zeroed (no-data) quote -> change None -> flat
    p = StocksTrendColor(symbol="ZZZZ")
    assert _rgb(p.color_for(0, 0, 1)) == _rgb(_DEFAULT_FLAT)


def test_green_up_false_swaps_up_and_down():
    _seed("AAPL", price=110.0, prev=100.0)  # up
    p = StocksTrendColor(symbol="AAPL", green_up=False)
    assert _rgb(p.color_for(0, 0, 1)) == _rgb(pal.DOWN)  # up change -> down color


def test_color_overrides_applied():
    _seed("AAPL", price=110.0, prev=100.0)  # up
    p = StocksTrendColor(symbol="AAPL", up=[1, 2, 3])
    assert _rgb(p.color_for(0, 0, 1)) == (1, 2, 3)


def test_missing_symbol_raises():
    with pytest.raises(ValueError, match="symbol"):
        StocksTrendColor()


def test_trend_color_accepts_slash_symbol():
    """Forex/crypto symbols (EUR/USD, BTC/USD) must be accepted — the trend
    provider is a passive cache reader with no provider awareness; symbol
    validity is the source/widget's concern, not this provider's."""
    # Must not raise (previously rejected any '/' as forex).
    prov = StocksTrendColor(symbol="EUR/USD")
    assert prov.symbol == "EUR/USD"


@pytest.mark.parametrize("bad", [[300, 0, 0], [0, 0], [1, 2, "x"], [True, 0, 0]])
def test_bad_rgb_raises(bad):
    with pytest.raises(ValueError):
        StocksTrendColor(symbol="AAPL", up=bad)


def test_construction_registers_symbol():
    StocksTrendColor(symbol="MSFT")
    assert "MSFT" in _cache.get_cache()._symbols


def test_provider_flags():
    assert StocksTrendColor.per_char is False
    assert StocksTrendColor.frame_invariant is False
