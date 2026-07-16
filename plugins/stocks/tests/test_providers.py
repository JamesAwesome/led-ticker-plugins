import unittest.mock as mock

from led_ticker_stocks.providers import FinnhubProvider, TwelveDataProvider
from led_ticker_stocks.state import MarketState


async def test_finnhub_provider_returns_global_state():
    client = mock.Mock()
    client.fetch_market_status = mock.AsyncMock(return_value={"isOpen": True})
    client.fetch_quote = mock.AsyncMock(return_value={"c": 10.0, "pc": 9.0})
    prov = FinnhubProvider(client)
    assert await prov.fetch_market_state() is MarketState.OPEN
    q = await prov.fetch_quote("AAPL")
    assert q.sym == "AAPL" and q.price == 10.0


async def test_finnhub_provider_falls_back_to_clock_on_status_error():
    client = mock.Mock()
    client.fetch_market_status = mock.AsyncMock(side_effect=RuntimeError("boom"))
    prov = FinnhubProvider(client)
    state = await prov.fetch_market_state()
    assert isinstance(state, MarketState)  # clock fallback, never raises


async def test_twelvedata_provider_state_is_per_symbol_none_global():
    client = mock.Mock()
    client.fetch_quote = mock.AsyncMock(
        return_value={
            "symbol": "EUR/USD",
            "close": "1.1",
            "previous_close": "1.0",
            "is_market_open": True,
        }
    )
    prov = TwelveDataProvider(client)
    assert await prov.fetch_market_state() is None
    q = await prov.fetch_quote("EUR/USD")
    assert q.state is MarketState.OPEN
