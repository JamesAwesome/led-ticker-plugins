import unittest.mock as mock

import aiohttp
import pytest

from led_ticker_stocks.finnhub import FinnhubClient, parse_quote


def _mock_session(json_body, status=200, capture=None):
    """Build a Mock aiohttp session.

    `.get(url, params=)` records its params into `capture` (if given) and
    returns an async-context manager yielding a response with `.status`,
    async `.json()`, and a `.raise_for_status()` that raises
    `aiohttp.ClientResponseError` when status != 200 (mirroring aiohttp's
    own behavior). Same pattern as plugins/crypto/tests/test_coingecko.py.
    """
    session = mock.Mock()

    resp = mock.AsyncMock()
    resp.status = status
    resp.json = mock.AsyncMock(return_value=json_body)

    def _raise_for_status():
        if status >= 400:
            raise aiohttp.ClientResponseError(
                request_info=mock.Mock(),
                history=(),
                status=status,
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


async def test_get_raises_on_non_200():
    session = _mock_session({"error": "forbidden"}, status=403)
    client = FinnhubClient("tok", session=session)
    with pytest.raises(aiohttp.ClientResponseError):
        await client.fetch_quote("AAPL")


async def test_get_injects_token_into_params():
    captured = {}
    session = _mock_session({"c": 1.0}, capture=captured)
    client = FinnhubClient("tok", session=session)
    await client.fetch_quote("AAPL")
    assert captured["params"]["token"] == "tok"
    assert captured["params"]["symbol"] == "AAPL"


def test_parse_quote_maps_fields():
    payload = {
        "c": 317.31,
        "d": 1.99,
        "dp": 0.6311,
        "h": 323.45,
        "l": 315.78,
        "o": 317.015,
        "pc": 315.32,
        "t": 1,
    }
    q = parse_quote("AAPL", payload)
    assert q.sym == "AAPL"
    assert q.price == 317.31 and q.prev == 315.32
    assert q.d == 1.99 and q.dp == 0.6311
    assert q.has_data


def test_parse_quote_maps_high_low():
    payload = {"c": 317.31, "pc": 315.32, "h": 323.45, "l": 315.78}
    q = parse_quote("AAPL", payload)
    assert q.high == pytest.approx(323.45)
    assert q.low == pytest.approx(315.78)


def test_parse_quote_missing_high_low_is_none():
    payload = {"c": 317.31, "pc": 315.32}
    q = parse_quote("AAPL", payload)
    assert q.high is None and q.low is None


def test_parse_quote_zeroed_is_no_data():
    payload = {
        "c": 0,
        "d": None,
        "dp": None,
        "h": 0,
        "l": 0,
        "o": 0,
        "pc": 0,
        "t": 0,
    }
    q = parse_quote("ZZZZ", payload)
    assert not q.has_data
    assert q.change is None and q.pct is None
