"""QuoteCache: shared singleton owning all Finnhub I/O (Phase 4)."""

from unittest import mock

import pytest

from led_ticker_stocks import _cache


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
    """Once a symbol's LAST-KNOWN state settles to CLOSED, a subsequent cycle
    must NOT refetch it — freeze it and save the per-key rate budget.

    The generalized per-symbol freeze (Task 3) reads each quote's own stored
    `state` from the END of the previous cycle, not the just-fetched global
    state — this is what lets the same freeze check work for Twelve Data,
    which has no separate global status call at all. One consequence for
    Finnhub: on the very cycle the market transitions open->closed, AAPL's
    stored state is still OPEN (from the prior cycle), so it is fetched ONE
    more time before the freeze can see CLOSED and take hold on the cycle
    after that — a one-cycle lag versus the old global-state-gates-everyone
    check, in exchange for a single unified freeze rule."""
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
    await c.update()  # transition cycle: last-known state was OPEN -> one more fetch
    assert calls == ["AAPL", "AAPL"]

    await c.update()  # now frozen: last-known state is CLOSED
    assert calls == ["AAPL", "AAPL"]  # unchanged — frozen, no third call


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


async def test_ensure_started_no_token_routes_to_demo(monkeypatch):
    from led_ticker_stocks._cache import get_cache
    from led_ticker_stocks.state import MarketState

    monkeypatch.delenv("TWELVEDATA_API_KEY", raising=False)
    cache = get_cache()
    cache.register(["EUR/USD"])
    await cache.ensure_started(session=object(), provider="twelvedata")
    assert cache.state() is MarketState.OPEN  # demo feed marks OPEN
    assert cache.get("EUR/USD") is not None


async def test_warm_closed_symbol_is_frozen_cold_is_fetched(monkeypatch):
    """Generalized per-symbol freeze: attempted+CLOSED held, cold fetched."""
    from led_ticker_stocks._cache import get_cache
    from led_ticker_stocks.model import SymbolQuote, decimals_for
    from led_ticker_stocks.state import MarketState

    cache = get_cache()
    cache.register(["WARM", "COLD"])
    # WARM: attempted, last state CLOSED -> should be held.
    cache._attempted.add("WARM")
    cache._quotes["WARM"].state = MarketState.CLOSED
    calls = []

    class _Prov:
        async def fetch_market_state(self):
            return None  # per-symbol (twelvedata-style)

        async def fetch_quote(self, sym):
            calls.append(sym)
            return SymbolQuote(sym=sym, price=5.0, prev=4.0,
                               dp_decimals=decimals_for(5.0),
                               state=MarketState.OPEN)

    cache._provider = _Prov()
    cache._started = True
    import asyncio
    cache._poll_lock = asyncio.Lock()
    await cache.update()
    assert calls == ["COLD"]  # WARM held, COLD fetched
