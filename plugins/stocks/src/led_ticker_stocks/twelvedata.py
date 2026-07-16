"""Twelve Data REST client (free tier): one uniform /quote across asset classes.

Unlike Finnhub (equities only, separate market-status call), Twelve Data's
/quote covers stocks, forex, and crypto with an identical response shape and
a per-symbol `is_market_open` flag baked in — so a mixed config gets correct
per-symbol market state with no extra request. All numeric fields arrive as
STRINGS; parse_quote coerces them. Token from TWELVEDATA_API_KEY (env only).
"""

import logging
from collections.abc import Callable

from led_ticker_stocks.model import SymbolQuote, decimals_for
from led_ticker_stocks.state import MarketState

QUOTE_URL = "https://api.twelvedata.com/quote"
API_USAGE_URL = "https://api.twelvedata.com/api_usage"


def _f(payload, key):
    """Coerce a TD string numeric to float; None for missing/blank."""
    v = payload.get(key)
    if v is None or v == "":
        return None
    try:
        return float(v)
    except TypeError, ValueError:
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
    def __init__(self, token, session, on_credits: Callable[[int], None] | None = None):
        self._token = token
        self._session = session
        self._on_credits = on_credits

    async def fetch_quote(self, sym):
        params = {"symbol": sym, "apikey": self._token}
        async with self._session.get(QUOTE_URL, params=params) as resp:
            if resp.status != 200:
                logging.warning("Twelve Data /quote failed: HTTP %s", resp.status)
                resp.raise_for_status()
            body = await resp.json()
            self._report_credits(resp.headers)
            return body

    def _report_credits(self, headers) -> None:
        """Feed `api-credits-left` (remaining in the current minute window) to
        the observer, if set. Missing/non-integer header => no signal (never 0)."""
        if self._on_credits is None:
            return
        raw = headers.get("api-credits-left")
        if raw is None:
            return
        try:
            left = int(raw)
        except TypeError, ValueError:
            return
        if left >= 0:
            self._on_credits(left)

    async def fetch_api_usage(self):
        """Raw /api_usage body — reports the plan's per-minute `plan_limit`,
        daily limit, and `plan_category` (tier). Used to auto-size the request
        rate to the key's actual plan (free 8/min vs. a paid tier)."""
        params = {"apikey": self._token}
        async with self._session.get(API_USAGE_URL, params=params) as resp:
            if resp.status != 200:
                logging.warning("Twelve Data /api_usage failed: HTTP %s", resp.status)
                resp.raise_for_status()
            return await resp.json()
