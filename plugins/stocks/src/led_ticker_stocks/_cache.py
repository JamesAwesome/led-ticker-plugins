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

from led_ticker_stocks._ratelimit import AsyncRateLimiter
from led_ticker_stocks.demo import DemoFeed, seed_quotes
from led_ticker_stocks.finnhub import FinnhubClient, parse_quote
from led_ticker_stocks.model import SymbolQuote
from led_ticker_stocks.providers import FinnhubProvider, Provider, TwelveDataProvider
from led_ticker_stocks.state import MarketState
from led_ticker_stocks.twelvedata import TwelveDataClient

_PROVIDER_ENV = {
    "finnhub": "FINNHUB_API_TOKEN",
    "twelvedata": "TWELVEDATA_API_KEY",
}


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
        self._provider: Provider | None = None
        # Per-minute request throttle, built from the provider's cap once the
        # provider is resolved. Guards against boot-burst / large-symbol 429s.
        self._limiter: AsyncRateLimiter | None = None
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
        self,
        session: object,
        *,
        interval: int = 60,
        force_demo: bool = False,
        provider: str = "finnhub",
    ) -> None:
        """Idempotently start the shared poll loop.

        No-op on every call after the first — this is a SHARED, single-mode
        cache: the FIRST widget to call `ensure_started` decides demo vs.
        live for every widget reading it, and every later call (even with a
        different `force_demo`) is silently ignored. A config that mixes a
        `demo = true` widget with a plain live widget in the same process
        resolves to whichever one's `start()` happens to run first — this
        is a pre-existing property of the shared-cache design, not new here.

        Resolves the provider token from env ONLY (never a param — see
        CLAUDE.md "Secrets belong in .env, not config.toml"): `force_demo`
        OR no token routes to the offline `DemoFeed` over the symbols
        registered so far, marking the market OPEN; otherwise a token
        builds the real provider (`FinnhubProvider` or `TwelveDataProvider`)
        selected by `provider`. Tolerates a failed initial `update()` so a
        rate-limited or unreachable upstream at boot doesn't block startup.

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

        token = os.getenv(_PROVIDER_ENV.get(provider, "FINNHUB_API_TOKEN"), "")
        if force_demo or not token:
            self._demo_feed = DemoFeed(sorted(self._symbols))
            self._quotes = self._demo_feed.quotes
            self._state = MarketState.OPEN
        elif provider == "twelvedata":
            self._provider = TwelveDataProvider(TwelveDataClient(token, session))
        else:
            self._provider = FinnhubProvider(FinnhubClient(token, session))

        if self._provider is not None:
            self._limiter = AsyncRateLimiter(self._provider.REQUESTS_PER_MINUTE)

        # Hold the poll lock for the eager fetch so a second consumer's
        # `ensure_started` -> `_catch_up_new_symbols` (which also takes the
        # lock) can't fire a redundant fetch of the same symbols before this
        # populates `_attempted` (the boot-race double-fetch).
        try:
            async with self._poll_lock:
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

    async def _fetch_one(self, sym: str, global_state: MarketState | None) -> None:
        """Rate-limited fetch + in-place merge of one symbol's live quote.

        Assumes the caller decided this symbol is NOT frozen this cycle. Shared
        by the full `update()` loop and the surgical late-registrant catch-up
        so both throttle identically and merge the same way.
        """
        if self._limiter is not None:
            await self._limiter.acquire()
        assert self._provider is not None
        existing = self._quotes[sym]
        fresh = await self._provider.fetch_quote(sym)
        self._attempted.add(sym)
        if global_state is not None:
            fresh.state = global_state  # Finnhub: stamp the one global state
        if fresh.has_data:
            if fresh.price != existing.price:
                existing.flash_t = time.monotonic()
            existing.price, existing.prev = fresh.price, fresh.prev
            existing.d, existing.dp = fresh.d, fresh.dp
            existing.high, existing.low = fresh.high, fresh.low
            existing.dp_decimals = fresh.dp_decimals
            existing.state = fresh.state
            existing.spark.append(fresh.price)
        else:
            # No fresh price, but adopt the state so the market CHIP (widget
            # reads quote.state) reflects reality even on a no-trade tick.
            existing.state = fresh.state
            logging.debug(
                "stocks QuoteCache: %s returned no data this tick — holding last price",
                sym,
            )

    async def _catch_up_new_symbols(self) -> None:
        """Fetch ONLY the symbols registered since the last poll — called when a
        later consumer (e.g. a stocks.ticker widget starting after a token
        already booted the cache) brings new symbols. Fetches just the cold
        ones, NOT a full `update()`: re-running the whole cycle re-fetches every
        already-warm symbol too (Twelve Data never freezes), stacking redundant
        requests at boot and tripping the per-minute 429. Demo seeds new symbols
        with no network, so it takes the cheap full path."""
        if not (self._symbols - self._attempted):
            return
        assert self._poll_lock is not None  # started implies the lock exists
        try:
            async with self._poll_lock:
                # Re-check under the lock: the eager fetch (also lock-held) or
                # another catch-up may have just warmed these.
                cold = self._symbols - self._attempted
                if not cold:
                    return
                if self._demo_feed is not None:
                    await self.update()  # demo: cheap, no network
                    return
                global_state = (
                    await self._provider.fetch_market_state()
                    if self._provider is not None
                    else None
                )
                if global_state is not None:
                    self._state = global_state
                for sym in sorted(cold):
                    await self._fetch_one(sym, global_state)
                if global_state is None:
                    self._state = (
                        MarketState.OPEN
                        if any(
                            q.state is MarketState.OPEN for q in self._quotes.values()
                        )
                        else MarketState.CLOSED
                    )
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

        assert self._provider is not None, (
            "stocks QuoteCache: live mode requires a provider"
        )

        global_state = await self._provider.fetch_market_state()
        if global_state is not None:
            self._state = global_state

        # Freeze on THIS cycle's global authority, not stale per-quote state.
        # A held symbol skips its fetch, so `existing.state` never updates —
        # gating on it would latch the symbol CLOSED forever and it would never
        # resume on reopen (dead panel until restart). `global_state` is
        # refreshed every cycle, so reopen (-> OPEN) unfreezes. Finnhub: this
        # equals the original `closed = self._state is CLOSED`. Twelve Data:
        # global_state is None -> never frozen here -> every symbol fetches each
        # cycle and auto-detects its own reopen from is_market_open (interval
        # bounds credit use).
        market_closed = global_state is MarketState.CLOSED
        fetched = held = 0
        for sym in list(self._symbols):  # snapshot: register() may add mid-await
            existing = self._quotes[sym]
            # Cold symbols (never attempted) always fetch once — Finnhub /quote
            # and Twelve Data /quote both return the last close even while shut,
            # so a fresh boot after hours still populates.
            if market_closed and sym in self._attempted:
                # Keep the market CHIP fresh for a held symbol: Finnhub stamps
                # the global state on every symbol every cycle so the chip flips
                # to CLSD on close even though the price is held. (Freeze gate is
                # `market_closed`, not this — so this cannot re-latch. TD never
                # reaches here: global_state is None, it never freezes.)
                if global_state is not None:
                    existing.state = global_state
                held += 1
                continue
            await self._fetch_one(sym, global_state)
            fetched += 1
        # For a per-symbol provider (Twelve Data), derive the legacy global
        # state() for any back-compat reader: OPEN if any tracked symbol is
        # open, else CLOSED. (Widget stories read quote.state directly now.)
        if global_state is None:
            self._state = (
                MarketState.OPEN
                if any(q.state is MarketState.OPEN for q in self._quotes.values())
                else MarketState.CLOSED
            )
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
        self._provider = None
        self._limiter = None
        self._demo_feed = None
        self._started = False
        self._task = None
        self._poll_lock = None


_CACHE = QuoteCache()


def get_cache() -> QuoteCache:
    """Process-wide `QuoteCache` singleton shared by all `stocks.ticker` widgets."""
    return _CACHE
