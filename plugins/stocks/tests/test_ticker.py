"""StocksTicker Container + _StockStory: shared-quote crawl stories."""

import logging
import unittest.mock as mock

import pytest

from led_ticker_stocks.finnhub import FinnhubClient
from led_ticker_stocks.model import SymbolQuote
from led_ticker_stocks.state import MarketState
from led_ticker_stocks.ticker import SYMBOL_SOFT_CAP, StocksTicker, _StockStory


def _canvas():
    c = mock.Mock()
    c.width = 160
    c.height = 16
    c.scale = 1
    return c


def test_validate_rejects_empty_symbols():
    msgs = StocksTicker.validate_config({"symbols": []})
    assert any("symbol" in m for m in msgs)


def test_validate_rejects_fx_symbol():
    msgs = StocksTicker.validate_config({"symbols": ["EUR/USD"]})
    assert any("forex" in m.lower() or "paid" in m.lower() for m in msgs)


def test_validate_rejects_unknown_layout():
    msgs = StocksTicker.validate_config({"symbols": ["AAPL"], "layout": "bogus"})
    assert any("layout" in m for m in msgs)


def test_story_draw_reads_shared_quotes():
    quotes = {
        "AAPL": SymbolQuote(sym="AAPL", price=317.31, prev=315.32, d=1.99, dp=0.6311)
    }
    state_ref = [MarketState.OPEN]
    story = _StockStory(
        sym="AAPL",
        quotes=quotes,
        state_ref=state_ref,
        layout=None,
        green_up=True,
        padding=6,
    )
    canvas, cursor = story.draw(_canvas(), 0)
    assert cursor > 0


@pytest.mark.asyncio
async def test_demo_start_builds_stories_without_token():
    widget = await StocksTicker.start(
        symbols=["AAPL", "MSFT"], session=mock.Mock(), demo=True
    )
    assert len(widget.feed_stories) == 2
    assert all(s.quotes["AAPL"].has_data for s in widget.feed_stories)


@pytest.mark.asyncio
async def test_update_live_updates_shared_quotes(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_TOKEN", "tok")
    widget = await StocksTicker.start(symbols=["AAPL"], session=mock.Mock(), demo=False)

    async def fake_quote(sym):
        return {"c": 200.0, "d": 5.0, "dp": 2.5, "pc": 195.0}

    async def fake_status(exchange="US"):
        return {"isOpen": True, "session": "regular"}

    widget._client.fetch_quote = fake_quote
    widget._client.fetch_market_status = fake_status
    await widget.update()
    assert widget.feed_stories[0].quotes["AAPL"].price == 200.0
    assert widget._state_ref[0] is MarketState.OPEN


@pytest.mark.asyncio
async def test_config_token_is_ignored(monkeypatch):
    """A config-supplied `token` kwarg (simulating `token = "..."` in
    config.toml, which core's factory would bind from `start()`'s
    signature if the parameter still existed) must never reach the
    Finnhub client. The token comes from env (FINNHUB_API_TOKEN) only.
    """
    monkeypatch.setenv("FINNHUB_API_TOKEN", "real-env-token")
    widget = await StocksTicker.start(
        symbols=["AAPL"],
        session=mock.Mock(),
        demo=False,
        token="LEAK",
    )
    assert widget.token != "LEAK"
    assert widget.token == "real-env-token"
    assert widget._client is not None
    assert widget._client._token != "LEAK"
    assert widget._client._token == "real-env-token"


@pytest.mark.asyncio
async def test_config_token_is_ignored_no_env(monkeypatch):
    """Same invariant with no env token set: routes to demo, never 'LEAK'."""
    monkeypatch.delenv("FINNHUB_API_TOKEN", raising=False)
    widget = await StocksTicker.start(
        symbols=["AAPL"],
        session=mock.Mock(),
        demo=False,
        token="LEAK",
    )
    assert widget.token != "LEAK"
    assert widget.token == ""
    assert widget._client is None  # empty token routes to the demo feed


@pytest.mark.asyncio
async def test_update_falls_back_to_clock_on_status_failure(monkeypatch):
    """Fix 1: a market-status fetch failure must not propagate, and the
    resulting state must actually be clock-derived (not just "unchanged") —
    proven by checking the quote loop's behavior is consistent with the
    clock-derived state rather than the previous state.
    """
    monkeypatch.setenv("FINNHUB_API_TOKEN", "tok")
    widget = await StocksTicker.start(symbols=["AAPL"], session=mock.Mock(), demo=False)
    widget._state_ref[0] = MarketState.CLOSED  # start from a known, different state

    async def failing_status(exchange="US"):
        raise RuntimeError("status endpoint unreachable")

    async def fake_quote(sym):
        return {"c": 123.0, "d": 1.0, "dp": 0.5, "pc": 122.0}

    widget._client.fetch_market_status = failing_status
    widget._client.fetch_quote = fake_quote
    monkeypatch.setattr(
        "led_ticker_stocks.ticker.state_now_from_clock", lambda: MarketState.OPEN
    )

    await widget.update()  # must not raise

    assert widget._state_ref[0] is MarketState.OPEN
    # OPEN (not CLOSED) means the quote loop actually ran off the
    # clock-derived state, proving the except branch drove the flow.
    assert widget.feed_stories[0].quotes["AAPL"].price == 123.0


@pytest.mark.asyncio
async def test_update_clock_fallback_closed_skips_quotes(monkeypatch):
    """Same fallback, but the clock-derived state is CLOSED — the existing
    no-quote-calls-when-closed logic must still apply to it.
    """
    monkeypatch.setenv("FINNHUB_API_TOKEN", "tok")
    widget = await StocksTicker.start(symbols=["AAPL"], session=mock.Mock(), demo=False)

    async def failing_status(exchange="US"):
        raise RuntimeError("boom")

    quote_calls = []

    async def fake_quote(sym):
        quote_calls.append(sym)
        return {"c": 999.0, "pc": 998.0}

    widget._client.fetch_market_status = failing_status
    widget._client.fetch_quote = fake_quote
    monkeypatch.setattr(
        "led_ticker_stocks.ticker.state_now_from_clock", lambda: MarketState.CLOSED
    )

    await widget.update()

    assert widget._state_ref[0] is MarketState.CLOSED
    assert quote_calls == []  # closed → no quote fetches, even via the fallback path


@pytest.mark.asyncio
async def test_update_holds_last_price_on_zeroed_tick(monkeypatch):
    """Fix 2: a transient zeroed quote for a symbol that already has good
    data must not clobber the last-known price/prev with 0.
    """
    monkeypatch.setenv("FINNHUB_API_TOKEN", "tok")
    widget = await StocksTicker.start(symbols=["AAPL"], session=mock.Mock(), demo=False)

    async def fake_status(exchange="US"):
        return {"isOpen": True, "session": "regular"}

    async def good_quote(sym):
        return {"c": 200.0, "d": 5.0, "dp": 2.5, "pc": 195.0}

    widget._client.fetch_market_status = fake_status
    widget._client.fetch_quote = good_quote
    await widget.update()
    quote = widget.feed_stories[0].quotes["AAPL"]
    assert quote.price == 200.0
    assert quote.prev == 195.0
    spark_len_before = len(quote.spark)

    async def zeroed_quote(sym):
        return {"c": 0, "pc": 0}

    widget._client.fetch_quote = zeroed_quote
    await widget.update()

    assert quote.price == 200.0  # held, not clobbered to 0
    assert quote.prev == 195.0
    assert len(quote.spark) == spark_len_before  # no-data tick doesn't append


@pytest.mark.asyncio
async def test_update_still_applies_good_data_after_holding(monkeypatch):
    """A symbol that legitimately has data still updates normally — the
    hold-last-price guard must not become a permanent freeze.
    """
    monkeypatch.setenv("FINNHUB_API_TOKEN", "tok")
    widget = await StocksTicker.start(symbols=["AAPL"], session=mock.Mock(), demo=False)

    async def fake_status(exchange="US"):
        return {"isOpen": True, "session": "regular"}

    widget._client.fetch_market_status = fake_status

    async def zeroed_quote(sym):
        return {"c": 0, "pc": 0}

    widget._client.fetch_quote = zeroed_quote
    await widget.update()
    assert not widget.feed_stories[0].quotes["AAPL"].has_data

    async def good_quote(sym):
        return {"c": 250.0, "d": 2.0, "dp": 0.8, "pc": 248.0}

    widget._client.fetch_quote = good_quote
    await widget.update()
    quote = widget.feed_stories[0].quotes["AAPL"]
    assert quote.price == 250.0
    assert quote.prev == 248.0


@pytest.mark.asyncio
async def test_start_warns_above_symbol_soft_cap(caplog):
    """Fix 3: exceeding SYMBOL_SOFT_CAP logs exactly one warning and does
    not otherwise change behavior.
    """
    caplog.set_level(logging.WARNING)
    symbols = [f"SYM{i}" for i in range(SYMBOL_SOFT_CAP + 5)]
    widget = await StocksTicker.start(symbols=symbols, session=mock.Mock(), demo=True)

    assert len(widget.feed_stories) == len(symbols)
    cap_warnings = [
        r
        for r in caplog.records
        if r.levelno == logging.WARNING and "60 req/min" in r.getMessage()
    ]
    assert len(cap_warnings) == 1


@pytest.mark.asyncio
async def test_start_no_warning_at_or_below_soft_cap(caplog):
    caplog.set_level(logging.WARNING)
    symbols = [f"SYM{i}" for i in range(SYMBOL_SOFT_CAP)]
    await StocksTicker.start(symbols=symbols, session=mock.Mock(), demo=True)

    cap_warnings = [r for r in caplog.records if "60 req/min" in r.getMessage()]
    assert cap_warnings == []


@pytest.mark.asyncio
async def test_start_tolerates_initial_fetch_failure(monkeypatch, caplog):
    """Covers the previously-uncovered except branch in start(): the first
    update() raising must not prevent the widget from being constructed.
    """
    monkeypatch.setenv("FINNHUB_API_TOKEN", "tok")

    async def fake_status(self, exchange="US"):
        return {"isOpen": True, "session": "regular"}

    async def failing_quote(self, sym):
        raise RuntimeError("network down")

    monkeypatch.setattr(FinnhubClient, "fetch_market_status", fake_status)
    monkeypatch.setattr(FinnhubClient, "fetch_quote", failing_quote)

    caplog.set_level(logging.WARNING)
    widget = await StocksTicker.start(symbols=["AAPL"], session=mock.Mock(), demo=False)

    assert widget is not None
    assert len(widget.feed_stories) == 1
    assert any("initial fetch failed" in r.getMessage() for r in caplog.records)
