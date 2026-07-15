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

    c._client.fetch_quote = q
    c._client.fetch_market_status = st
    before = c.get("AAPL").flash_t
    await c.update()
    assert c.get("AAPL").price == 200.0 and c.get("AAPL").high == 201.0
    assert c.get("AAPL").flash_t != before  # stamped on change


@pytest.mark.asyncio
async def test_closed_skips_quotes(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_TOKEN", "tok")
    c = _cache.get_cache()
    c.register(["AAPL"])
    await c.ensure_started(session=mock.Mock())
    calls = []

    async def q(sym):
        calls.append(sym)
        return {"c": 1, "pc": 1}

    async def st(exchange="US"):
        return {"isOpen": False, "session": None}

    c._client.fetch_quote = q
    c._client.fetch_market_status = st
    await c.update()
    assert calls == []  # frozen when closed


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
