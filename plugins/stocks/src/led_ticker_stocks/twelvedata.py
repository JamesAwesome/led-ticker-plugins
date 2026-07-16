"""Twelve Data REST client (free tier): one uniform /quote across asset classes.

Unlike Finnhub (equities only, separate market-status call), Twelve Data's
/quote covers stocks, forex, and crypto with an identical response shape and
a per-symbol `is_market_open` flag baked in — so a mixed config gets correct
per-symbol market state with no extra request. All numeric fields arrive as
STRINGS; parse_quote coerces them. Token from TWELVEDATA_API_KEY (env only).
"""

import logging

from led_ticker_stocks.model import SymbolQuote, decimals_for
from led_ticker_stocks.state import MarketState

QUOTE_URL = "https://api.twelvedata.com/quote"


def _f(payload, key):
    """Coerce a TD string numeric to float; None for missing/blank."""
    v = payload.get(key)
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def parse_quote(sym, payload):
    price = _f(payload, "close") or 0.0
    prev = _f(payload, "previous_close") or 0.0
    state = MarketState.OPEN if payload.get("is_market_open") else MarketState.CLOSED
    return SymbolQuote(
        sym=sym,
        price=price,
        prev=prev,
        d=_f(payload, "change"),
        dp=_f(payload, "percent_change"),
        dp_decimals=decimals_for(price),
        high=_f(payload, "high"),
        low=_f(payload, "low"),
        state=state,
    )


class TwelveDataClient:
    def __init__(self, token, session):
        self._token = token
        self._session = session

    async def fetch_quote(self, sym):
        params = {"symbol": sym, "apikey": self._token}
        async with self._session.get(QUOTE_URL, params=params) as resp:
            if resp.status != 200:
                logging.warning("Twelve Data /quote failed: HTTP %s", resp.status)
                resp.raise_for_status()
            return await resp.json()
