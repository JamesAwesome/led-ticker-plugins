import pytest

from led_ticker_stocks.model import (
    SymbolQuote,
    decimals_for,
    format_change,
    format_pct,
    format_price,
)
from led_ticker_stocks.state import MarketState


def test_has_data_false_on_zero():
    assert not SymbolQuote(sym="X", price=0.0, prev=0.0).has_data
    assert not SymbolQuote(sym="X", price=10.0, prev=0.0).has_data
    assert SymbolQuote(sym="X", price=10.0, prev=9.0).has_data


def test_change_pct_prefers_finnhub_fields():
    q = SymbolQuote(sym="AAPL", price=317.31, prev=315.32, d=1.99, dp=0.6311)
    assert q.change == pytest.approx(1.99)
    assert q.pct == pytest.approx(0.6311)


def test_change_pct_recompute_when_fields_none():
    q = SymbolQuote(sym="AAPL", price=110.0, prev=100.0, d=None, dp=None)
    assert q.change == pytest.approx(10.0)
    assert q.pct == pytest.approx(10.0)


def test_change_pct_none_when_no_data():
    q = SymbolQuote(sym="X", price=0.0, prev=0.0, d=None, dp=None)
    assert q.change is None and q.pct is None


def test_push_price_updates_and_accumulates_spark():
    q = SymbolQuote(sym="X", price=100.0, prev=99.0)
    q.push_price(101.0)
    q.push_price(102.0)
    assert q.price == 102.0
    assert list(q.spark)[-2:] == [101.0, 102.0]


def test_spark_bounded_to_64():
    q = SymbolQuote(sym="X", price=1.0, prev=1.0)
    for i in range(100):
        q.push_price(float(i))
    assert len(q.spark) == 64


def test_formatting():
    assert format_price(1234.5, 2) == "1,234.50"
    assert format_change(1.99, 2) == "+1.99"
    assert format_change(-2.5, 2) == "−2.50"  # U+2212 minus
    assert format_change(None, 2) == "—"
    assert format_pct(0.63) == "+0.63%"
    assert format_pct(-1.2) == "−1.20%"
    assert format_pct(None) == "—"


def test_decimals_for_magnitude_bands():
    assert decimals_for(0.00042) == 5  # sub-1 (some crypto)
    assert decimals_for(0.5) == 5
    assert decimals_for(1.0) == 4  # boundary
    assert decimals_for(1.14669) == 4  # forex
    assert decimals_for(9.99) == 4
    assert decimals_for(10.0) == 2  # boundary
    assert decimals_for(208.89) == 2  # equity
    assert decimals_for(64906.62) == 2  # crypto large
    assert decimals_for(-3.5) == 4  # magnitude, not sign


def test_symbol_quote_defaults_to_closed_state():
    q = SymbolQuote(sym="AAPL", price=0.0, prev=0.0)
    assert q.state is MarketState.CLOSED
