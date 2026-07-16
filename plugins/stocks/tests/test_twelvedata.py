import unittest.mock as mock

import aiohttp
import pytest

from led_ticker_stocks.state import MarketState
from led_ticker_stocks.twelvedata import QUOTE_URL, TwelveDataClient, parse_quote


def _mock_session(json_body, status=200, capture=None, headers=None):
    """aiohttp session mock: .get(url, params=) yields an async ctx whose
    response has .status, async .json(), and a raising .raise_for_status().
    Mirrors tests/test_finnhub.py._mock_session."""
    session = mock.Mock()
    resp = mock.AsyncMock()
    resp.status = status
    resp.headers = headers or {}  # real dict: .get() returns str or None
    resp.json = mock.AsyncMock(return_value=json_body)

    def _raise_for_status():
        if status >= 400:
            raise aiohttp.ClientResponseError(
                request_info=mock.Mock(), history=(), status=status
            )

    resp.raise_for_status = mock.Mock(side_effect=_raise_for_status)
    ctx = mock.AsyncMock()
    ctx.__aenter__ = mock.AsyncMock(return_value=resp)
    ctx.__aexit__ = mock.AsyncMock(return_value=False)

    def _get(url, params=None):
        if capture is not None:
            capture["url"] = url
            capture["params"] = params
        return ctx

    session.get = mock.Mock(side_effect=_get)
    return session


_FOREX = {
    "symbol": "EUR/USD",
    "open": "1.14634",
    "high": "1.14689",
    "low": "1.14618",
    "close": "1.14669",
    "previous_close": "1.14633",
    "change": "0.00036",
    "percent_change": "0.0314",
    "is_market_open": True,
}

_STOCK_CLOSED = {
    "symbol": "AAPL",
    "close": "208.89",
    "previous_close": "210.35",
    "change": "-1.46",
    "percent_change": "-0.694",
    "high": "211.0",
    "low": "207.5",
    "is_market_open": False,
}


def test_parse_forex_maps_string_fields_to_floats():
    q = parse_quote("EUR/USD", _FOREX)
    assert q.sym == "EUR/USD"
    assert q.price == pytest.approx(1.14669)
    assert q.prev == pytest.approx(1.14633)
    assert q.d == pytest.approx(0.00036)
    assert q.dp == pytest.approx(0.0314)
    assert q.high == pytest.approx(1.14689)
    assert q.low == pytest.approx(1.14618)
    assert q.has_data


def test_parse_sets_open_state_from_is_market_open():
    assert parse_quote("EUR/USD", _FOREX).state is MarketState.OPEN
    assert parse_quote("AAPL", _STOCK_CLOSED).state is MarketState.CLOSED


def test_parse_sets_magnitude_decimals():
    assert parse_quote("EUR/USD", _FOREX).dp_decimals == 4  # ~1.15
    assert parse_quote("AAPL", _STOCK_CLOSED).dp_decimals == 2  # ~209


def test_parse_missing_high_low_is_none():
    payload = {
        "symbol": "X",
        "close": "5.0",
        "previous_close": "4.0",
        "is_market_open": True,
    }
    q = parse_quote("X", payload)
    assert q.high is None and q.low is None


def test_parse_zeroed_is_no_data():
    payload = {
        "symbol": "ZZZ",
        "close": "0",
        "previous_close": "0",
        "is_market_open": False,
    }
    q = parse_quote("ZZZ", payload)
    assert not q.has_data


async def test_fetch_quote_injects_apikey_and_symbol():
    captured = {}
    session = _mock_session(_FOREX, capture=captured)
    client = TwelveDataClient("tok", session=session)
    await client.fetch_quote("EUR/USD")
    assert captured["url"] == QUOTE_URL
    assert captured["params"]["apikey"] == "tok"
    assert captured["params"]["symbol"] == "EUR/USD"


async def test_fetch_quote_raises_on_non_200():
    session = _mock_session({"code": 401, "status": "error"}, status=401)
    client = TwelveDataClient("tok", session=session)
    with pytest.raises(aiohttp.ClientResponseError):
        await client.fetch_quote("EUR/USD")


_API_USAGE = {
    "current_usage": 1,
    "plan_limit": 300,
    "daily_usage": 60,
    "plan_daily_limit": 100000,
    "plan_category": "pro",
}


async def test_fetch_api_usage_returns_body_with_apikey():
    captured = {}
    session = _mock_session(_API_USAGE, capture=captured)
    client = TwelveDataClient("tok", session=session)
    result = await client.fetch_api_usage()
    assert result["plan_limit"] == 300
    assert result["plan_category"] == "pro"
    assert captured["params"]["apikey"] == "tok"


async def test_fetch_api_usage_raises_on_non_200():
    session = _mock_session({"code": 401, "status": "error"}, status=401)
    client = TwelveDataClient("tok", session=session)
    with pytest.raises(aiohttp.ClientResponseError):
        await client.fetch_api_usage()


async def test_fetch_quote_reports_credits_left_via_callback():
    seen = []
    session = _mock_session(_FOREX, headers={"api-credits-left": "6"})
    client = TwelveDataClient("tok", session=session, on_credits=seen.append)
    await client.fetch_quote("EUR/USD")
    assert seen == [6]  # parsed int from the header


async def test_fetch_quote_no_header_does_not_call_back():
    seen = []
    session = _mock_session(_FOREX)  # no api-credits-left header
    client = TwelveDataClient("tok", session=session, on_credits=seen.append)
    await client.fetch_quote("EUR/USD")
    assert seen == []  # missing header => no signal, never "0"


async def test_fetch_quote_bad_header_is_ignored():
    seen = []
    session = _mock_session(_FOREX, headers={"api-credits-left": "n/a"})
    client = TwelveDataClient("tok", session=session, on_credits=seen.append)
    await client.fetch_quote("EUR/USD")
    assert seen == []


async def test_fetch_quote_negative_header_is_ignored():
    """A nonsensical negative credits-left is defensively rejected (never fed
    to the limiter as a real budget)."""
    seen = []
    session = _mock_session(_FOREX, headers={"api-credits-left": "-5"})
    client = TwelveDataClient("tok", session=session, on_credits=seen.append)
    await client.fetch_quote("EUR/USD")
    assert seen == []
