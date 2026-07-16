"""Provider seam: Finnhub (global market state) vs Twelve Data (per-symbol).

`QuoteCache` orchestrates the poll loop and freeze; a Provider supplies just
the two provider-specific pieces: how market state is obtained, and how a
symbol's quote is fetched + parsed. Finnhub makes one global market-status
call per cycle (clock fallback on failure) and every quote shares that state;
Twelve Data has no separate status call — each /quote carries is_market_open,
so fetch_market_state() returns None and per-symbol state rides on the quote.
"""

import logging
from collections.abc import Callable
from typing import ClassVar, Protocol

from led_ticker_stocks import finnhub, twelvedata
from led_ticker_stocks.model import SymbolQuote
from led_ticker_stocks.state import MarketState, state_from_status, state_now_from_clock


class Provider(Protocol):
    """The two provider-specific pieces `QuoteCache` drives each cycle.

    `fetch_market_state` returns a global `MarketState` (Finnhub) or `None`
    when state is per-symbol on the quote (Twelve Data). `REQUESTS_PER_MINUTE`
    is the free-tier per-minute request cap the cache rate-limits to.
    """

    REQUESTS_PER_MINUTE: ClassVar[int]

    async def fetch_market_state(self) -> MarketState | None: ...

    async def fetch_quote(self, sym: str) -> SymbolQuote: ...

    async def fetch_plan_limit(self) -> int | None:
        """The key's actual per-minute request cap, if the provider can detect
        it (else None → the cache uses `REQUESTS_PER_MINUTE`). Must never raise."""
        ...

    def set_credit_observer(self, cb: Callable[[int], None]) -> None:
        """Register a callback fed the per-request remaining-budget signal
        (Twelve Data's api-credits-left). No-op for providers without it."""
        ...


class FinnhubProvider:
    # Finnhub free tier: 60 requests/min per token.
    REQUESTS_PER_MINUTE: ClassVar[int] = 60

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

    async def fetch_plan_limit(self) -> int | None:
        return None  # no auto-detect; the cache uses REQUESTS_PER_MINUTE (60)

    def set_credit_observer(self, cb: Callable[[int], None]) -> None:
        return  # Finnhub has no per-request credit header


class TwelveDataProvider:
    # Twelve Data free tier: 8 requests/min (the credit/day budget is bounded
    # separately by the poll interval). Cap a bit under to leave headroom.
    REQUESTS_PER_MINUTE: ClassVar[int] = 8

    def __init__(self, client):
        self._client = client

    async def fetch_market_state(self) -> MarketState | None:
        return None  # per-symbol; each quote carries is_market_open

    async def fetch_quote(self, sym: str) -> SymbolQuote:
        return twelvedata.parse_quote(sym, await self._client.fetch_quote(sym))

    async def fetch_plan_limit(self) -> int | None:
        """Per-minute cap from /api_usage, or None on ANY failure (the cache
        then falls back to REQUESTS_PER_MINUTE). Logs the detected tier so a
        troubleshooting user can confirm detection. Never raises."""
        try:
            usage = await self._client.fetch_api_usage()
        except Exception as e:
            logging.warning(
                "stocks: Twelve Data rate auto-detect failed (%s); using default", e
            )
            return None
        limit = usage.get("plan_limit")
        if isinstance(limit, bool) or not isinstance(limit, (int, float)) or limit <= 0:
            return None
        limit = int(limit)
        logging.info(
            "stocks: Twelve Data plan %r — %d req/min",
            usage.get("plan_category", "?"),
            limit,
        )
        return limit

    def set_credit_observer(self, cb: Callable[[int], None]) -> None:
        self._client._on_credits = cb
