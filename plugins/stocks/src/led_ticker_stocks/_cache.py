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
        # Symbols we've called fetch_quote for at least once (demo: seeded).
        # Drives two things: the closed-market freeze (skip a symbol we've
        # already tried, data or not) and the late-registrant catch-up
        # (fetch symbols registered after the initial fetch). NOT `has_data`
        # — a bad symbol has no data but must not refetch forever.
        self._attempted: set[str] = set()
        self._state: MarketState = MarketState.CLOSED
        self._client: FinnhubClient | None = None
        self._demo_feed: DemoFeed | None = None
        self._started: bool = False
        self._task: asyncio.Task[None] | None = None
        self._base_interval: int = 60
        # Serializes the two update() drivers (the poll loop and the
        # late-registrant catch-up) so they can't double-fetch concurrently.
        # Created in ensure_started (inside the running loop).
        self._poll_lock: asyncio.Lock | None = None

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
            # A consumer registering AFTER the cache started (e.g. a
            # stocks.ticker widget whose start() runs after a stocks.quote
            # token already booted the cache, or a hot-reloaded source)
            # brings symbols the initial fetch never saw. Catch them up now
            # so their cards / tokens populate immediately instead of sitting
            # cold (em-dash / "…") until the next poll cycle, a full interval
            # away. Cheap no-op when every registered symbol is already warm.
            await self._catch_up_new_symbols()
            return
        self._started = True
        self._base_interval = interval
        self._poll_lock = asyncio.Lock()

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

        Sleep-first: `ensure_started` already awaits one eager `update()`
        before spawning this loop, so firing another `update()` immediately
        here would double the initial Finnhub request burst
        (2×(N+1) requests back-to-back at boot) for no benefit — the eager
        call already populated values. The loop's first real work happens
        after one interval has elapsed.
        """
        assert self._poll_lock is not None  # spawned only after ensure_started
        consecutive_errors = 0
        while True:
            interval = self._effective_interval()
            if consecutive_errors:
                interval *= min(2**consecutive_errors, 10)
            await asyncio.sleep(interval)
            try:
                async with self._poll_lock:
                    await self.update()
                consecutive_errors = 0
            except Exception as e:
                consecutive_errors += 1
                logging.warning(
                    "stocks QuoteCache: poll cycle failed (%s); will retry", e
                )

    async def _catch_up_new_symbols(self) -> None:
        """Fetch symbols registered since the last poll — called when a later
        consumer starts an already-running cache. A no-op unless there is at
        least one symbol never attempted yet, so it doesn't refire on bad
        symbols (attempted, no data) or when everything is already warm."""
        if not (self._symbols - self._attempted):
            return
        assert self._poll_lock is not None  # started implies the lock exists
        try:
            async with self._poll_lock:
                await self.update()
        except Exception as e:
            logging.warning(
                "stocks QuoteCache: catch-up for late registrants failed "
                "(%s); the poll loop will retry",
                e,
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
            self._attempted.update(self._symbols)  # all seeded -> nothing pending
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
        # When closed, we freeze — but only symbols we've ALREADY fetched once.
        # A never-attempted symbol (fresh boot after hours, or a late
        # registrant) still needs ONE fetch to grab the last close: Finnhub
        # /quote returns it in `c` even while the market is shut. Skipping ALL
        # fetches when closed left cold symbols empty forever — em-dash cards,
        # "…" inline tokens. Keying the freeze on `_attempted` (not `has_data`)
        # also stops a bad symbol from refetching every closed cycle.
        closed = self._state is MarketState.CLOSED
        if closed:
            logging.info(
                "stocks QuoteCache: market closed — fetching last close for "
                "cold symbols, holding the rest"
            )

        fetched = held = 0
        # snapshot: a consumer may register() a new symbol during an await
        for sym in list(self._symbols):
            existing = self._quotes[sym]
            if closed and sym in self._attempted:
                held += 1  # frozen: already tried this symbol, don't spend a call
                continue
            payload = await self._client.fetch_quote(sym)
            self._attempted.add(sym)
            fresh = parse_quote(sym, payload)
            if fresh.has_data:
                if fresh.price != existing.price:
                    existing.flash_t = time.monotonic()
                existing.price, existing.prev = fresh.price, fresh.prev
                existing.d, existing.dp = fresh.d, fresh.dp
                existing.high, existing.low = fresh.high, fresh.low
                existing.dp_decimals = fresh.dp_decimals
                existing.spark.append(fresh.price)
            else:
                logging.debug(
                    "stocks QuoteCache: %s returned no data this tick — "
                    "holding last price",
                    sym,
                )
            fetched += 1
        logging.info(
            "stocks QuoteCache updated: %d fetched, %d held (%d symbols)",
            fetched,
            held,
            len(self._symbols),
        )

    def reset(self) -> None:
        """Clear all state and cancel the spawned poll task (test seam)."""
        if self._task is not None:
            self._task.cancel()
        self._symbols = set()
        self._quotes = {}
        self._attempted = set()
        self._state = MarketState.CLOSED
        self._client = None
        self._demo_feed = None
        self._started = False
        self._task = None
        self._poll_lock = None


_CACHE = QuoteCache()


def get_cache() -> QuoteCache:
    """Process-wide `QuoteCache` singleton shared by all `stocks.ticker` widgets."""
    return _CACHE
