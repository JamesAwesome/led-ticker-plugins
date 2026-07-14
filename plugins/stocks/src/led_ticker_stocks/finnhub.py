"""Finnhub REST client (free tier): quote + market-status.

Forex is paid-only → not used.
"""

import logging

QUOTE_URL = "https://finnhub.io/api/v1/quote"
STATUS_URL = "https://finnhub.io/api/v1/stock/market-status"


def parse_quote(sym, payload):
    from led_ticker_stocks.model import SymbolQuote

    return SymbolQuote(
        sym=sym,
        price=float(payload.get("c") or 0.0),
        prev=float(payload.get("pc") or 0.0),
        d=payload.get("d"),
        dp=payload.get("dp"),
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
