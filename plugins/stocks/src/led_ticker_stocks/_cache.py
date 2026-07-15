"""Shared QuoteCache singleton: owns all Finnhub I/O for the stocks plugin.

Multiple `stocks.ticker` widgets (e.g. one per section/layout) previously each
ran their own `FinnhubClient` + poll loop, multiplying Finnhub request volume
per configured symbol set. `QuoteCache` centralizes registration + polling so
every widget instance shares one poll cycle keyed on the UNION of symbols
any widget has registered.

Consumers call `get_cache()` to reach the process-wide singleton, `register()`
their symbols, `ensure_started()` once (idempotent) to kick off the shared
poll loop, and `get()` / `state()` to read live data on each draw.
"""

import asyncio
import logging
import os
import time
from collections.abc import Iterable

from led_ticker.plugin import run_monitor_loop, spawn_tracked

from led_ticker_stocks.demo import DemoFeed, seed_quotes
from led_ticker_stocks.finnhub import FinnhubClient, parse_quote
from led_ticker_stocks.model import SymbolQuote
from led_ticker_stocks.state import MarketState, state_from_status, state_now_from_clock


class QuoteCache:
    """Owns the symbol set, live quotes, market state, and the single poll loop."""

    def __init__(self) -> None:
        self._symbols: set[str] = set()
        self._quotes: dict[str, SymbolQuote] = {}
        self._state: MarketState = MarketState.CLOSED
        self._client: FinnhubClient | None = None
        self._demo_feed: DemoFeed | None = None
        self._started: bool = False
        self._task: asyncio.Task[None] | None = None

    def register(self, symbols: Iterable[str]) -> None:
        """Union `symbols` into the tracked set; seed a zeroed quote for any new one."""
        for sym in symbols:
            self._symbols.add(sym)
            if sym not in self._quotes:
                self._quotes[sym] = parse_quote(sym, {"c": 0, "pc": 0})

    def get(self, symbol: str) -> SymbolQuote | None:
        return self._quotes.get(symbol)

    def state(self) -> MarketState:
        return self._state

    async def ensure_started(self, session: object, *, interval: int = 60) -> None:
        """Idempotently start the shared poll loop.

        No-op on every call after the first. Resolves the Finnhub token from
        env ONLY (never a param — see CLAUDE.md "Secrets belong in .env, not
        config.toml"): no token routes to the offline `DemoFeed` over the
        symbols registered so far, marking the market OPEN; a token builds a
        real `FinnhubClient`. Tolerates a failed initial `update()` so a
        rate-limited or unreachable Finnhub at boot doesn't block startup.
        """
        if self._started:
            return
        self._started = True

        token = os.getenv("FINNHUB_API_TOKEN", "")
        if not token:
            self._demo_feed = DemoFeed(sorted(self._symbols))
            self._quotes = self._demo_feed.quotes
            self._state = MarketState.OPEN
        else:
            self._client = FinnhubClient(token, session)

        try:
            await self.update()
        except Exception as e:
            logging.warning(
                "stocks QuoteCache: initial fetch failed (%s); "
                "starting with placeholders, will retry",
                e,
            )
        self._task = spawn_tracked(
            run_monitor_loop(self, max(interval, len(self._symbols) + 1))
        )

    async def update(self) -> None:
        """One poll cycle: demo step, or live market-status + per-symbol quotes."""
        if self._demo_feed is not None:
            # Late registrants (register() called after ensure_started) are
            # tracked in `_symbols` but not yet in the feed's own walk list
            # (`_symbols` on DemoFeed) — seed + splice them in here so they
            # get synthesized data instead of sitting zeroed forever.
            demo_symbols = self._demo_feed._symbols
            for sym in self._symbols:
                if sym not in demo_symbols:
                    seeded = seed_quotes([sym])[sym]
                    self._demo_feed.quotes[sym] = seeded
                    demo_symbols.append(sym)
            for _ in range(len(self._symbols)):
                self._demo_feed.step()
            self._state = MarketState.OPEN
            logging.info("stocks QuoteCache demo tick: %d symbols", len(self._symbols))
            return

        assert self._client is not None, (
            "stocks QuoteCache: live mode requires a client"
        )

        try:
            status = await self._client.fetch_market_status()
            self._state = state_from_status(status)
        except Exception as e:
            logging.warning(
                "stocks QuoteCache: market-status request failed (%s); "
                "falling back to the US/Eastern clock",
                e,
            )
            self._state = state_now_from_clock()
        if self._state is MarketState.CLOSED:
            logging.info("stocks QuoteCache: market closed — holding last prices")
            return  # frozen when closed (no quote calls)

        updated = 0
        for sym in self._symbols:
            payload = await self._client.fetch_quote(sym)
            fresh = parse_quote(sym, payload)
            existing = self._quotes[sym]
            if fresh.has_data:
                if fresh.price != existing.price:
                    existing.flash_t = time.monotonic()
                existing.price, existing.prev = fresh.price, fresh.prev
                existing.d, existing.dp = fresh.d, fresh.dp
                existing.high, existing.low = fresh.high, fresh.low
                existing.spark.append(fresh.price)
            else:
                logging.debug(
                    "stocks QuoteCache: %s returned no data this tick — "
                    "holding last price",
                    sym,
                )
            updated += 1
        logging.info(
            "stocks QuoteCache updated: %d/%d symbols", updated, len(self._symbols)
        )

    def reset(self) -> None:
        """Clear all state and cancel the spawned poll task (test seam)."""
        if self._task is not None:
            self._task.cancel()
        self._symbols = set()
        self._quotes = {}
        self._state = MarketState.CLOSED
        self._client = None
        self._demo_feed = None
        self._started = False
        self._task = None


_CACHE = QuoteCache()


def get_cache() -> QuoteCache:
    """Process-wide `QuoteCache` singleton shared by all `stocks.ticker` widgets."""
    return _CACHE
