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

from led_ticker.plugin import spawn_tracked

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
        self._base_interval: int = 60

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

    async def ensure_started(
        self, session: object, *, interval: int = 60, force_demo: bool = False
    ) -> None:
        """Idempotently start the shared poll loop.

        No-op on every call after the first — this is a SHARED, single-mode
        cache: the FIRST widget to call `ensure_started` decides demo vs.
        live for every widget reading it, and every later call (even with a
        different `force_demo`) is silently ignored. A config that mixes a
        `demo = true` widget with a plain live widget in the same process
        resolves to whichever one's `start()` happens to run first — this
        is a pre-existing property of the shared-cache design, not new here.

        Resolves the Finnhub token from env ONLY (never a param — see
        CLAUDE.md "Secrets belong in .env, not config.toml"): `force_demo`
        OR no token routes to the offline `DemoFeed` over the symbols
        registered so far, marking the market OPEN; otherwise a token
        builds a real `FinnhubClient`. Tolerates a failed initial
        `update()` so a rate-limited or unreachable Finnhub at boot doesn't
        block startup.

        The poll cadence is NOT fixed at spawn time: `_run_poll_loop` recomputes
        it from the live symbol count every cycle (`_effective_interval`), so a
        consumer that registers more symbols after the loop is already running
        still widens the interval — a fixed `run_monitor_loop` interval could
        not react to that, risking N quote calls + 1 status call per cycle
        exceeding Finnhub's per-key rate budget.
        """
        if self._started:
            return
        self._started = True
        self._base_interval = interval

        token = os.getenv("FINNHUB_API_TOKEN", "")
        if force_demo or not token:
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
        self._task = spawn_tracked(self._run_poll_loop())

    def _effective_interval(self) -> int:
        """Poll cadence: widens as the live symbol count grows.

        Recomputed fresh on every call (not cached) so late registrants —
        symbols added via `register()` after the poll loop already started —
        are reflected on the very next cycle instead of being stuck at the
        cadence that was correct when `ensure_started` first ran.
        """
        return max(self._base_interval, len(self._symbols) + 1)

    async def _run_poll_loop(self) -> None:
        """Self-paced poll loop (replaces `run_monitor_loop`).

        `run_monitor_loop` fixes its interval at spawn time, which can't
        widen when more symbols register later. This loop recomputes
        `_effective_interval()` fresh each cycle instead. Supervised like
        `run_monitor_loop`'s intent: a transient `update()` failure is
        logged and the loop keeps running (never dies on one bad cycle),
        with a simple exponential backoff on repeated failures.
        """
        consecutive_errors = 0
        while True:
            try:
                await self.update()
                consecutive_errors = 0
            except Exception as e:
                consecutive_errors += 1
                logging.warning(
                    "stocks QuoteCache: poll cycle failed (%s); will retry", e
                )
            interval = self._effective_interval()
            if consecutive_errors:
                interval *= min(2**consecutive_errors, 10)
            await asyncio.sleep(interval)

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
