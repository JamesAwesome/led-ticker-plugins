"""Finnhub REST client (free tier): quote + market-status.

Forex is paid-only → not used.
"""

import logging

QUOTE_URL = "https://finnhub.io/api/v1/quote"
STATUS_URL = "https://finnhub.io/api/v1/stock/market-status"


def parse_quote(sym, payload):
    from led_ticker_stocks.model import SymbolQuote

    high = payload.get("h")
    low = payload.get("l")
    price = float(payload.get("c") or 0.0)
    return SymbolQuote(
        sym=sym,
        price=price,
        prev=float(payload.get("pc") or 0.0),
        d=payload.get("d"),
        dp=payload.get("dp"),
        # Finnhub is equities-only -> fixed 2 decimals (model default); a $7
        # stock is "7.45", not "7.4500". Magnitude auto-decimals (decimals_for)
        # applies only to the Twelve Data path (forex/sub-$1 need 4-5).
        high=float(high) if high is not None else None,
        low=float(low) if low is not None else None,
    )


class FinnhubClient:
    def __init__(self, token, session):
        self._token = token
        self._session = session

    async def _get(self, url, params):
        params = {**params, "token": self._token}
        async with self._session.get(url, params=params) as resp:
            if resp.status != 200:
                logging.warning("Finnhub %s failed: HTTP %s", url, resp.status)
                resp.raise_for_status()
            return await resp.json()

    async def fetch_quote(self, sym):
        return await self._get(QUOTE_URL, {"symbol": sym})

    async def fetch_market_status(self, exchange="US"):
        return await self._get(STATUS_URL, {"exchange": exchange})
