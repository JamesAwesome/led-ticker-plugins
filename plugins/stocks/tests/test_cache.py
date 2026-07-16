"""QuoteCache: shared singleton owning all Finnhub I/O (Phase 4)."""

import asyncio
from unittest import mock

import pytest

from led_ticker_stocks import _cache


def _install_prov(cache, prov):
    cache._provider = prov
    cache._started = True
    cache._poll_lock = asyncio.Lock()


@pytest.fixture(autouse=True)
def _reset_cache():
    _cache.get_cache().reset()
    yield
    _cache.get_cache().reset()


def test_register_dedups_and_seeds():
    c = _cache.get_cache()
    c.register(["AAPL", "MSFT"])
    c.register(["AAPL", "NVDA"])  # AAPL repeat
    assert c.get("AAPL") is not None and c.get("NVDA") is not None
    assert {"AAPL", "MSFT", "NVDA"} <= c._symbols
    assert not c.get("AAPL").has_data  # seeded zeroed


def test_get_unknown_symbol_returns_none():
    c = _cache.get_cache()
    assert c.get("ZZZZ") is None


@pytest.mark.asyncio
async def test_update_live_mutates_and_stamps_flash(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_TOKEN", "tok")
    c = _cache.get_cache()
    c.register(["AAPL"])
    await c.ensure_started(session=mock.Mock())  # spawns loop; tolerate initial

    async def q(sym):
        return {"c": 200.0, "d": 5.0, "dp": 2.5, "pc": 195.0, "h": 201, "l": 194}

    async def st(exchange="US"):
        return {"isOpen": True, "session": "regular"}

    c._provider._client.fetch_quote = q
    c._provider._client.fetch_market_status = st
    before = c.get("AAPL").flash_t
    await c.update()
    assert c.get("AAPL").price == 200.0 and c.get("AAPL").high == 201.0
    assert c.get("AAPL").flash_t != before  # stamped on change


@pytest.mark.asyncio
async def test_update_live_survives_concurrent_register_during_await(monkeypatch):
    """A consumer calling register() while update() is parked on an in-flight
    fetch_quote() await must not raise `RuntimeError: Set changed size during
    iteration` — update() iterates a snapshot of _symbols, not the live set."""
    monkeypatch.setenv("FINNHUB_API_TOKEN", "tok")
    c = _cache.get_cache()
    c.register(["AAPL"])
    await c.ensure_started(session=mock.Mock())  # spawns loop; tolerate initial

    calls = []

    async def q(sym):
        calls.append(sym)
        if len(calls) == 1:
            # Simulate a concurrent registrant during this in-flight await —
            # this used to mutate the set update() is iterating over.
            c.register(["NEWSYM"])
        return {"c": 200.0, "d": 5.0, "dp": 2.5, "pc": 195.0, "h": 201, "l": 194}

    async def st(exchange="US"):
        return {"isOpen": True, "session": "regular"}

    c._provider._client.fetch_quote = q
    c._provider._client.fetch_market_status = st

    await c.update()  # must not raise


@pytest.mark.asyncio
async def test_update_live_does_not_restamp_flash_on_unchanged_price(monkeypatch):
    """flash_t is stamped ONLY on a real price change — a second tick that
    returns the SAME price must leave flash_t untouched."""
    monkeypatch.setenv("FINNHUB_API_TOKEN", "tok")
    c = _cache.get_cache()
    c.register(["AAPL"])
    await c.ensure_started(session=mock.Mock())  # spawns loop; tolerate initial

    async def q(sym):
        return {"c": 200.0, "d": 5.0, "dp": 2.5, "pc": 195.0, "h": 201, "l": 194}

    async def st(exchange="US"):
        return {"isOpen": True, "session": "regular"}

    c._provider._client.fetch_quote = q
    c._provider._client.fetch_market_status = st

    await c.update()  # first tick: price changes 0 -> 200, flash_t stamped
    stamped = c.get("AAPL").flash_t
    assert stamped is not None

    await c.update()  # second tick: same price, flash_t must be unchanged
    assert c.get("AAPL").flash_t == stamped


@pytest.mark.asyncio
async def test_closed_fetches_cold_symbols_once(monkeypatch):
    """A cold boot while the market is CLOSED must still fetch each symbol ONCE
    to grab the last close. Regression: the cache used to skip ALL quote calls
    when closed, so a sign booted after hours left the card on em-dash and
    inline tokens stuck on their "…" placeholder forever (Finnhub /quote
    returns the last close in `c` even when the market is shut)."""
    monkeypatch.setenv("FINNHUB_API_TOKEN", "tok")
    c = _cache.get_cache()
    c.register(["AAPL"])
    await c.ensure_started(session=mock.Mock())
    calls = []

    async def q(sym):
        calls.append(sym)
        return {"c": 252.4, "pc": 252.0, "d": 0.4, "dp": 0.16, "h": 253, "l": 251}

    async def st(exchange="US"):
        return {"isOpen": False, "session": None}

    c._provider._client.fetch_quote = q
    c._provider._client.fetch_market_status = st
    await c.update()
    assert calls == ["AAPL"]  # fetched once despite the market being closed
    assert c.get("AAPL").has_data  # populated with the last close
    assert c.get("AAPL").price == 252.4


@pytest.mark.asyncio
async def test_late_registrant_caught_up_on_ensure_started(monkeypatch):
    """A second consumer starting an already-running cache with NEW symbols
    (e.g. a stocks.ticker widget booting after a stocks.quote token already
    started the cache with just its own symbol) must fetch those symbols
    immediately via ensure_started's catch-up — not leave them cold until the
    next poll cycle a full interval away. Regression: after hours only the
    card whose symbol the token shared got data; the widget's others stayed
    on em-dash.
    """
    monkeypatch.setenv("FINNHUB_API_TOKEN", "tok")
    c = _cache.get_cache()

    # Consumer A (the token) starts the cache with only AAPL.
    c.register(["AAPL"])
    await c.ensure_started(session=mock.Mock())  # initial fetch fails, tolerated

    calls = []

    async def q(sym):
        calls.append(sym)
        return {"c": 100.0, "pc": 99.0}

    async def st(exchange="US"):
        return {"isOpen": False, "session": None}  # market closed

    c._provider._client.fetch_quote = q
    c._provider._client.fetch_market_status = st
    await c.update()  # A's first cycle warms AAPL
    assert calls == ["AAPL"]
    calls.clear()

    # Consumer B (the widget) registers MORE symbols, then calls ensure_started.
    # Already started -> must catch up the new symbols right now.
    c.register(["AAPL", "MSFT", "NVDA"])
    await c.ensure_started(session=mock.Mock())

    assert set(calls) == {"MSFT", "NVDA"}  # the NEW symbols, fetched immediately
    assert c.get("MSFT").has_data and c.get("NVDA").has_data
    assert "AAPL" not in calls  # already warm -> not refetched while closed


@pytest.mark.asyncio
async def test_ensure_started_no_catchup_when_all_symbols_warm(monkeypatch):
    """ensure_started's catch-up is a no-op when every registered symbol has
    already been fetched — a later consumer re-registering the SAME symbols
    must not trigger a redundant fetch."""
    monkeypatch.setenv("FINNHUB_API_TOKEN", "tok")
    c = _cache.get_cache()
    c.register(["AAPL"])
    await c.ensure_started(session=mock.Mock())

    calls = []

    async def q(sym):
        calls.append(sym)
        return {"c": 100.0, "pc": 99.0}

    async def st(exchange="US"):
        return {"isOpen": True, "session": "regular"}

    c._provider._client.fetch_quote = q
    c._provider._client.fetch_market_status = st
    await c.update()  # warm AAPL
    calls.clear()

    c.register(["AAPL"])  # same symbol, already warm
    await c.ensure_started(session=mock.Mock())
    assert calls == []  # nothing pending -> no catch-up fetch


@pytest.mark.asyncio
async def test_closed_holds_symbols_that_already_have_data(monkeypatch):
    """Once a symbol has been attempted and THIS cycle's global market state
    is CLOSED, a subsequent cycle must NOT refetch it — freeze it and save
    the per-key rate budget.

    The freeze gates on `global_state` (Finnhub: the just-fetched status for
    this cycle), not stale per-quote state — so the freeze takes hold
    immediately on the very cycle the market transitions open->closed, with
    no one-cycle lag."""
    monkeypatch.setenv("FINNHUB_API_TOKEN", "tok")
    c = _cache.get_cache()
    c.register(["AAPL"])
    await c.ensure_started(session=mock.Mock())
    calls = []

    async def q(sym):
        calls.append(sym)
        return {"c": 252.4, "pc": 252.0, "d": 0.4, "dp": 0.16, "h": 253, "l": 251}

    async def st_open(exchange="US"):
        return {"isOpen": True, "session": "regular"}

    async def st_closed(exchange="US"):
        return {"isOpen": False, "session": None}

    c._provider._client.fetch_quote = q
    c._provider._client.fetch_market_status = st_open
    await c.update()  # open cycle populates AAPL
    assert calls == ["AAPL"]

    c._provider._client.fetch_market_status = st_closed
    await c.update()  # closed cycle: frozen immediately, no second fetch
    assert calls == ["AAPL"]

    await c.update()  # still frozen: global state is still CLOSED
    assert calls == ["AAPL"]  # unchanged — frozen, no third call


@pytest.mark.asyncio
async def test_demo_no_token_synthesizes(monkeypatch):
    monkeypatch.delenv("FINNHUB_API_TOKEN", raising=False)

    c = _cache.get_cache()
    c.register(["AAPL", "MSFT"])
    await c.ensure_started(session=mock.Mock())
    assert c.get("AAPL").has_data  # demo feed seeded
    await c.update()  # steps without error


@pytest.mark.asyncio
async def test_demo_late_registrant_gets_synthesized_data(monkeypatch):
    """A symbol registered AFTER ensure_started must still be seeded and
    stepped by the demo feed, not left permanently zeroed."""
    monkeypatch.delenv("FINNHUB_API_TOKEN", raising=False)

    c = _cache.get_cache()
    c.register(["AAPL"])
    await c.ensure_started(session=mock.Mock())
    c.register(["MSFT"])  # late registrant, after ensure_started
    assert c.get("MSFT") is not None
    await c.update()
    assert c.get("MSFT").has_data


def test_effective_interval_widens_with_symbol_count():
    """Cadence must widen as MORE symbols register, even after the poll
    loop is already running — a fixed run_monitor_loop interval couldn't
    react to that; _effective_interval() recomputes live each cycle."""
    c = _cache.get_cache()
    c._base_interval = 5
    c.register(["AAPL", "MSFT"])
    before = c._effective_interval()
    assert before == 5  # base interval wins with only 2 symbols

    c.register([f"SYM{i}" for i in range(10)])  # late registrants
    after = c._effective_interval()
    assert after > before
    assert after == len(c._symbols) + 1


@pytest.mark.asyncio
async def test_ensure_started_idempotent(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_TOKEN", "tok")

    c = _cache.get_cache()
    c.register(["AAPL"])
    await c.ensure_started(session=mock.Mock())
    task_after_first = c._task
    await c.ensure_started(session=mock.Mock())
    assert c._task is task_after_first  # second call is a no-op


@pytest.mark.asyncio
async def test_reset_cancels_spawned_task(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_TOKEN", "tok")

    c = _cache.get_cache()
    c.register(["AAPL"])
    await c.ensure_started(session=mock.Mock())
    task = c._task
    assert task is not None
    c.reset()
    assert task.cancelled() or task.cancelling() > 0
    assert c.get("AAPL") is None
    assert c._symbols == set()


def test_state_defaults_closed():
    c = _cache.get_cache()
    from led_ticker_stocks.state import MarketState

    assert c.state() is MarketState.CLOSED


async def test_ensure_started_twelvedata_builds_td_provider(monkeypatch):
    from led_ticker_stocks._cache import get_cache
    from led_ticker_stocks.providers import TwelveDataProvider

    monkeypatch.setenv("TWELVEDATA_API_KEY", "tdkey")
    cache = get_cache()
    cache.register(["EUR/USD"])
    # Prevent real network: stub the provider's fetch to a no-data quote.
    started = {}

    async def _noop_update():
        started["ran"] = True

    monkeypatch.setattr(cache, "update", _noop_update)
    await cache.ensure_started(session=object(), provider="twelvedata")
    assert isinstance(cache._provider, TwelveDataProvider)
    # A per-minute rate limiter is built (auto-detected, or the safe default)
    # so a boot burst / large symbol list can't trip a 429.
    assert cache._limiter is not None


async def test_ensure_started_sizes_limiter_from_detected_plan_limit(monkeypatch):
    """A paid key's higher per-minute cap (detected via /api_usage) sizes the
    throttle, so a paid user isn't stuck at the free-tier rate."""
    import led_ticker_stocks.providers as providers_mod
    from led_ticker_stocks._cache import get_cache

    monkeypatch.setenv("TWELVEDATA_API_KEY", "tdkey")

    async def _detect_pro(self):
        return 300

    monkeypatch.setattr(
        providers_mod.TwelveDataProvider, "fetch_plan_limit", _detect_pro
    )
    cache = get_cache()
    cache.register(["EUR/USD"])

    async def _noop_update():
        pass

    monkeypatch.setattr(cache, "update", _noop_update)
    await cache.ensure_started(session=object(), provider="twelvedata")
    assert cache._limiter is not None
    assert cache._limiter._capacity == 300  # detected paid rate, not the 8 default


async def test_ensure_started_falls_back_to_default_when_detect_none(monkeypatch):
    """Detection failure (None) falls back to the provider's safe default (8)."""
    import led_ticker_stocks.providers as providers_mod
    from led_ticker_stocks._cache import get_cache

    monkeypatch.setenv("TWELVEDATA_API_KEY", "tdkey")

    async def _detect_none(self):
        return None

    monkeypatch.setattr(
        providers_mod.TwelveDataProvider, "fetch_plan_limit", _detect_none
    )
    cache = get_cache()
    cache.register(["EUR/USD"])

    async def _noop_update():
        pass

    monkeypatch.setattr(cache, "update", _noop_update)
    await cache.ensure_started(session=object(), provider="twelvedata")
    assert cache._limiter is not None
    assert cache._limiter._capacity == 8  # TwelveDataProvider.REQUESTS_PER_MINUTE


async def test_429_during_fetch_lowers_the_session_rate(monkeypatch):
    """A 429 is ground truth: it ratchets the shared limiter down for the
    session (a stale/shared/downgraded plan), then re-raises for the backoff."""
    from led_ticker_stocks._cache import get_cache
    from led_ticker_stocks._ratelimit import AsyncRateLimiter

    class _429(Exception):
        status = 429

    class _Prov:
        REQUESTS_PER_MINUTE = 8

        async def fetch_market_state(self):
            return None

        async def fetch_quote(self, sym):
            raise _429()

    cache = get_cache()
    cache.register(["EUR/USD"])
    cache._limiter = AsyncRateLimiter(300)  # detected paid rate
    _install_prov(cache, _Prov())
    before = cache._limiter._capacity
    with pytest.raises(_429):
        await cache._fetch_one("EUR/USD", None)
    assert cache._limiter._capacity == before / 2  # halved by note_rate_limited


async def test_catch_up_fetches_only_new_cold_symbols(monkeypatch):
    """Surgical catch-up: a late-registering widget fetches ONLY its new
    symbols, not the already-warm ones a token source primed. Re-fetching
    everything (Twelve Data never freezes) stacked the boot burst past the
    8/min cap and 429'd on the longboi."""
    from led_ticker_stocks._cache import get_cache
    from led_ticker_stocks.model import SymbolQuote, decimals_for
    from led_ticker_stocks.state import MarketState

    cache = get_cache()
    cache.register(["EUR/USD", "BTC/USD"])
    cache._attempted.update({"EUR/USD", "BTC/USD"})  # already warm (token sources)
    calls = []

    class _Prov:
        REQUESTS_PER_MINUTE = 8

        async def fetch_market_state(self):
            return None  # twelvedata-style (per-symbol)

        async def fetch_quote(self, sym):
            calls.append(sym)
            return SymbolQuote(
                sym=sym,
                price=5.0,
                prev=4.0,
                dp_decimals=decimals_for(5.0),
                state=MarketState.OPEN,
            )

    _install_prov(cache, _Prov())
    cache.register(["AAPL", "NVDA"])  # widget adds 2 new cold symbols
    await cache._catch_up_new_symbols()
    assert sorted(calls) == ["AAPL", "NVDA"]  # ONLY the new ones; warm not re-hit


async def test_ensure_started_no_token_routes_to_demo(monkeypatch):
    from led_ticker_stocks._cache import get_cache
    from led_ticker_stocks.state import MarketState

    monkeypatch.delenv("TWELVEDATA_API_KEY", raising=False)
    cache = get_cache()
    cache.register(["EUR/USD"])
    await cache.ensure_started(session=object(), provider="twelvedata")
    assert cache.state() is MarketState.OPEN  # demo feed marks OPEN
    assert cache.get("EUR/USD") is not None


async def test_warm_symbol_frozen_when_globally_closed_cold_fetched(monkeypatch):
    """Freeze on THIS cycle's global CLOSED (Finnhub-style provider): an
    attempted symbol is held, a cold one still fetches its last close."""
    from led_ticker_stocks._cache import get_cache
    from led_ticker_stocks.model import SymbolQuote, decimals_for
    from led_ticker_stocks.state import MarketState

    cache = get_cache()
    cache.register(["WARM", "COLD"])
    cache._attempted.add("WARM")
    calls = []

    class _Prov:
        async def fetch_market_state(self):
            return MarketState.CLOSED  # global (finnhub-style)

        async def fetch_quote(self, sym):
            calls.append(sym)
            return SymbolQuote(
                sym=sym,
                price=5.0,
                prev=4.0,
                dp_decimals=decimals_for(5.0),
                state=MarketState.CLOSED,
            )

    _install_prov(cache, _Prov())
    await cache.update()
    assert calls == ["COLD"]  # WARM held (attempted + globally closed), COLD fetched


async def test_reopen_refetches_previously_frozen_symbol(monkeypatch):
    """REGRESSION (Task 3 review): a symbol frozen while closed MUST resume
    fetching when the market reopens. Gating the freeze on stale per-quote
    state latched it CLOSED forever (dead panel until restart)."""
    from led_ticker_stocks._cache import get_cache
    from led_ticker_stocks.model import SymbolQuote, decimals_for
    from led_ticker_stocks.state import MarketState

    cache = get_cache()
    cache.register(["AAPL"])
    cache._attempted.add("AAPL")
    cache._quotes["AAPL"].state = MarketState.CLOSED
    calls = []
    box = {"s": MarketState.CLOSED}

    class _Prov:
        async def fetch_market_state(self):
            return box["s"]

        async def fetch_quote(self, sym):
            calls.append(sym)
            return SymbolQuote(
                sym=sym,
                price=5.0,
                prev=4.0,
                dp_decimals=decimals_for(5.0),
                state=box["s"],
            )

    _install_prov(cache, _Prov())
    await cache.update()  # closed -> held
    assert calls == []
    box["s"] = MarketState.OPEN
    await cache.update()  # reopened -> MUST fetch again
    assert calls == ["AAPL"]


async def test_held_finnhub_symbol_chip_state_follows_global(monkeypatch):
    """A warm Finnhub symbol that is FROZEN while closed must still show the
    CLOSED market state on its chip (quote.state), not a stale OPEN — the story
    reads quote.state for the chip."""
    from led_ticker_stocks._cache import get_cache
    from led_ticker_stocks.model import SymbolQuote, decimals_for
    from led_ticker_stocks.state import MarketState

    cache = get_cache()
    cache.register(["AAPL"])
    box = {"s": MarketState.OPEN}

    class _Prov:
        async def fetch_market_state(self):
            return box["s"]

        async def fetch_quote(self, sym):
            return SymbolQuote(
                sym=sym,
                price=50.0,
                prev=49.0,
                dp_decimals=decimals_for(50.0),
                state=box["s"],
            )

    _install_prov(cache, _Prov())
    await cache.update()  # open: AAPL fetched, state OPEN
    assert cache.get("AAPL").state is MarketState.OPEN
    box["s"] = MarketState.CLOSED
    await cache.update()  # closed: AAPL held, chip must flip
    assert cache.get("AAPL").state is MarketState.CLOSED


async def test_twelvedata_never_frozen_here_always_fetches(monkeypatch):
    """A per-symbol provider (global_state None) never freezes in update() —
    every symbol fetches each cycle so its own reopen is auto-detected, even
    one that is attempted with a CLOSED last state."""
    from led_ticker_stocks._cache import get_cache
    from led_ticker_stocks.model import SymbolQuote, decimals_for
    from led_ticker_stocks.state import MarketState

    cache = get_cache()
    cache.register(["BTC/USD"])
    cache._attempted.add("BTC/USD")
    cache._quotes["BTC/USD"].state = MarketState.CLOSED
    calls = []

    class _Prov:
        async def fetch_market_state(self):
            return None  # per-symbol (twelvedata-style)

        async def fetch_quote(self, sym):
            calls.append(sym)
            return SymbolQuote(
                sym=sym,
                price=5.0,
                prev=4.0,
                dp_decimals=decimals_for(5.0),
                state=MarketState.CLOSED,
            )

    _install_prov(cache, _Prov())
    await cache.update()
    assert calls == ["BTC/USD"]  # NOT frozen despite attempted + CLOSED
