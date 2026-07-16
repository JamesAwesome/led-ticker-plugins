"""Provider seam: Finnhub (global market state) vs Twelve Data (per-symbol).

`QuoteCache` orchestrates the poll loop and freeze; a Provider supplies just
the two provider-specific pieces: how market state is obtained, and how a
symbol's quote is fetched + parsed. Finnhub makes one global market-status
call per cycle (clock fallback on failure) and every quote shares that state;
Twelve Data has no separate status call — each /quote carries is_market_open,
so fetch_market_state() returns None and per-symbol state rides on the quote.
"""

import logging
from typing import Protocol

from led_ticker_stocks import finnhub, twelvedata
from led_ticker_stocks.model import SymbolQuote
from led_ticker_stocks.state import MarketState, state_from_status, state_now_from_clock


class Provider(Protocol):
    """The two provider-specific pieces `QuoteCache` drives each cycle.

    `fetch_market_state` returns a global `MarketState` (Finnhub) or `None`
    when state is per-symbol on the quote (Twelve Data).
    """

    async def fetch_market_state(self) -> MarketState | None: ...

    async def fetch_quote(self, sym: str) -> SymbolQuote: ...


class FinnhubProvider:
    def __init__(self, client):
        self._client = client

    async def fetch_market_state(self) -> MarketState | None:
        try:
            status = await self._client.fetch_market_status()
            return state_from_status(status)
        except Exception as e:
            logging.warning(
                "stocks Finnhub: market-status request failed (%s); "
                "falling back to the US/Eastern clock",
                e,
            )
            return state_now_from_clock()

    async def fetch_quote(self, sym: str) -> SymbolQuote:
        return finnhub.parse_quote(sym, await self._client.fetch_quote(sym))


class TwelveDataProvider:
    def __init__(self, client):
        self._client = client

    async def fetch_market_state(self) -> MarketState | None:
        return None  # per-symbol; each quote carries is_market_open

    async def fetch_quote(self, sym: str) -> SymbolQuote:
        return twelvedata.parse_quote(sym, await self._client.fetch_quote(sym))
