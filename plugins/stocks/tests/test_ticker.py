"""StocksTicker Container + _StockStory: reads live off the shared QuoteCache."""

import inspect
import logging
import time
import unittest.mock as mock

import attrs
import pytest
from led_ticker.plugin import HeadlessBackend

from led_ticker_stocks._cache import get_cache
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


def _bigsign_canvas():
    c = mock.Mock()
    c.width = 256
    c.height = 64
    c.scale = 1
    return c


def _smallsign_real():
    return HeadlessBackend(160, 16).create_canvas()


def _white_ish(canvas):
    # count pixels bright on all three channels (flash pushes price toward white)
    return sum(
        1 for v in canvas._pixels.values() if v[0] > 200 and v[1] > 200 and v[2] > 150
    )


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
    """Story no longer holds its own `quotes` dict — it reads live off the
    shared `QuoteCache` on every draw."""
    cache = get_cache()
    cache.register(["AAPL"])
    cache._quotes["AAPL"] = SymbolQuote(
        sym="AAPL", price=317.31, prev=315.32, d=1.99, dp=0.6311
    )
    story = _StockStory(sym="AAPL", layout=None, green_up=True, padding=6)
    canvas, cursor = story.draw(_canvas(), 0)
    assert cursor > 0


@pytest.mark.asyncio
async def test_demo_start_builds_stories_without_token(monkeypatch):
    monkeypatch.delenv("FINNHUB_API_TOKEN", raising=False)
    widget = await StocksTicker.start(symbols=["AAPL", "MSFT"], session=mock.Mock())
    assert len(widget.feed_stories) == 2
    cache = get_cache()
    assert all(cache.get(s).has_data for s in ["AAPL", "MSFT"])


@pytest.mark.asyncio
async def test_demo_start_wires_focus_index_and_all_symbols(monkeypatch):
    """Task 4: each story built by __attrs_post_init__ carries its own
    index into the shared, ordered display-symbol list (used by the card's
    paging dots and the dashboard's watch-column neighbors)."""
    monkeypatch.delenv("FINNHUB_API_TOKEN", raising=False)
    widget = await StocksTicker.start(
        symbols=["AAPL", "MSFT", "TSLA"], session=mock.Mock()
    )
    assert [s.focus_index for s in widget.feed_stories] == [0, 1, 2]
    for story in widget.feed_stories:
        assert story.all_symbols == ["AAPL", "MSFT", "TSLA"]


@pytest.mark.asyncio
async def test_story_draw_uses_card_layout_on_bigsign_canvas(monkeypatch):
    """A wide (bigsign) canvas resolves to the held `card` layout, which
    paints in place and returns the canvas width as a stable cursor
    (rather than a scroll position, which held layouts don't have)."""
    monkeypatch.delenv("FINNHUB_API_TOKEN", raising=False)
    widget = await StocksTicker.start(symbols=["AAPL", "MSFT"], session=mock.Mock())
    story = widget.feed_stories[0]
    canvas, end = story.draw(_bigsign_canvas())
    assert story._resolved == "card"
    assert end == canvas.width == 256


@pytest.mark.asyncio
async def test_update_live_updates_shared_quotes(monkeypatch):
    """The widget owns no quotes anymore — a cache poll mutates the shared
    `QuoteCache` in place, and the story picks it up on its very next draw.
    Before the poll, the cache holds only the zeroed placeholder seeded at
    `register()`, so the story renders the short '—' no-data segment; after
    a real quote lands, it renders the full price+chg+pct segment — a
    strictly longer cursor advance proves the story actually read the
    fresh cache state rather than something cached on the story itself.
    """
    monkeypatch.setenv("FINNHUB_API_TOKEN", "tok")
    widget = await StocksTicker.start(symbols=["AAPL"], session=mock.Mock())
    story = widget.feed_stories[0]
    _, end_before = story.draw(_canvas(), 0)

    cache = get_cache()

    async def fake_quote(sym):
        return {"c": 200.0, "d": 5.0, "dp": 2.5, "pc": 195.0}

    async def fake_status(exchange="US"):
        return {"isOpen": True, "session": "regular"}

    cache._provider._client.fetch_quote = fake_quote
    cache._provider._client.fetch_market_status = fake_status
    await cache.update()

    assert cache.get("AAPL").price == 200.0
    assert cache.state() is MarketState.OPEN

    _, end_after = story.draw(_canvas(), 0)
    assert end_after > end_before


@pytest.mark.asyncio
async def test_story_flashes_price_when_cache_stamps_flash_t(monkeypatch):
    """The cache stamps `flash_t` on a live price change (Task 1); the
    story must surface that through to the layout's flash-whiter render.
    `test_flash.py` proves the layout renders whiter given a flash-stamped
    quote directly — this proves the widget/cache wiring actually delivers
    one through `_StockStory.draw`.
    """
    monkeypatch.delenv("FINNHUB_API_TOKEN", raising=False)
    widget = await StocksTicker.start(symbols=["AAPL"], session=mock.Mock())
    story = widget.feed_stories[0]
    quote = get_cache().get("AAPL")
    quote.price, quote.prev, quote.d, quote.dp = 317.31, 315.32, 1.99, 0.6311

    quote.flash_t = time.monotonic()
    fresh = _smallsign_real()
    story.draw(fresh, 0)

    quote.flash_t = None
    stale = _smallsign_real()
    story.draw(stale, 0)

    assert _white_ish(fresh) > _white_ish(stale)


@pytest.mark.asyncio
async def test_config_token_is_ignored(monkeypatch):
    """A config-supplied `token` kwarg (simulating `token = "..."` in
    config.toml, which core's factory would bind from `start()`'s
    signature if the parameter existed) must never reach the Finnhub
    client — `start()` has no `token` parameter at all, and the token
    comes from env (FINNHUB_API_TOKEN) only, resolved by the shared cache.
    """
    assert "token" not in inspect.signature(StocksTicker.start).parameters

    monkeypatch.setenv("FINNHUB_API_TOKEN", "real-env-token")
    await StocksTicker.start(symbols=["AAPL"], session=mock.Mock(), token="LEAK")

    cache = get_cache()
    assert cache._provider is not None
    assert cache._provider._client._token != "LEAK"
    assert cache._provider._client._token == "real-env-token"


@pytest.mark.asyncio
async def test_config_token_is_ignored_no_env(monkeypatch):
    """Same invariant with no env token set: routes to demo, never 'LEAK'."""
    monkeypatch.delenv("FINNHUB_API_TOKEN", raising=False)
    await StocksTicker.start(symbols=["AAPL"], session=mock.Mock(), token="LEAK")

    cache = get_cache()
    assert cache._provider is None  # empty token routes to the demo feed
    assert cache._demo_feed is not None


@pytest.mark.asyncio
async def test_demo_field_forces_cache_demo(monkeypatch):
    """`demo = true` in config must force the shared cache into demo mode
    even when a live Finnhub token is present in env — the cache is
    single-mode per process, and `force_demo` is the knob that lets a
    `demo = true` widget win that mode regardless of the token (as long as
    it's the first widget to call `ensure_started`; see the shared-cache
    docstring on `QuoteCache.ensure_started`)."""
    monkeypatch.setenv("FINNHUB_API_TOKEN", "real-env-token")
    widget = await StocksTicker.start(symbols=["AAPL"], session=mock.Mock(), demo=True)

    assert widget.demo is True
    cache = get_cache()
    assert cache._provider is None  # NOT live, despite the env token
    assert cache._demo_feed is not None
    assert cache.get("AAPL").has_data  # demo feed seeded + stepped it


def test_validate_accepts_demo_and_token_fields():
    """Core allowlists a widget's config keys from `start()`'s explicit
    params UNION attrs-init fields (see CLAUDE.md). A v0.3.0 config with
    `demo = true` / `token = "..."` must resolve to keys in that set, or
    `led-ticker validate` hard-fails with "unknown field" — the Phase 4
    Task 2 refactor regressed exactly this for the plugin's own shipped
    `docs/demo.toml` + smoke configs.
    """
    allowed = {f.name for f in attrs.fields(StocksTicker)} | set(
        inspect.signature(StocksTicker.start).parameters
    )
    assert "demo" in allowed
    assert "token" in allowed

    # And the widget actually constructs with both set, without raising —
    # `token` is accepted-but-ignored, `demo` is a real field.
    widget = StocksTicker(symbols=["AAPL"], demo=True, token="ignored")
    assert widget.demo is True
    assert widget.token == "ignored"


@pytest.mark.asyncio
async def test_update_falls_back_to_clock_on_status_failure(monkeypatch):
    """Fix 1 (now living in the shared cache, ported by Task 1): a
    market-status fetch failure must not propagate, and the resulting
    state must actually be clock-derived (not just "unchanged") — proven
    by checking the quote loop's behavior is consistent with the
    clock-derived state rather than the previous state.
    """
    monkeypatch.setenv("FINNHUB_API_TOKEN", "tok")
    await StocksTicker.start(symbols=["AAPL"], session=mock.Mock())
    cache = get_cache()
    cache._state = MarketState.CLOSED  # start from a known, different state

    async def failing_status(exchange="US"):
        raise RuntimeError("status endpoint unreachable")

    async def fake_quote(sym):
        return {"c": 123.0, "d": 1.0, "dp": 0.5, "pc": 122.0}

    cache._provider._client.fetch_market_status = failing_status
    cache._provider._client.fetch_quote = fake_quote
    monkeypatch.setattr(
        "led_ticker_stocks.providers.state_now_from_clock", lambda: MarketState.OPEN
    )

    await cache.update()  # must not raise

    assert cache.state() is MarketState.OPEN
    # OPEN (not CLOSED) means the quote loop actually ran off the
    # clock-derived state, proving the except branch drove the flow.
    assert cache.get("AAPL").price == 123.0


@pytest.mark.asyncio
async def test_update_clock_fallback_closed_still_fetches_cold(monkeypatch):
    """Same fallback, but the clock-derived state is CLOSED. The closed policy
    applies to the fallback state too — but a COLD symbol still gets its one
    last-close fetch (a sign booted after hours must not sit on em-dash).
    """
    monkeypatch.setenv("FINNHUB_API_TOKEN", "tok")
    await StocksTicker.start(symbols=["AAPL"], session=mock.Mock())
    cache = get_cache()

    async def failing_status(exchange="US"):
        raise RuntimeError("boom")

    quote_calls = []

    async def fake_quote(sym):
        quote_calls.append(sym)
        return {"c": 999.0, "pc": 998.0}

    cache._provider._client.fetch_market_status = failing_status
    cache._provider._client.fetch_quote = fake_quote
    monkeypatch.setattr(
        "led_ticker_stocks.providers.state_now_from_clock", lambda: MarketState.CLOSED
    )

    await cache.update()

    assert cache.state() is MarketState.CLOSED  # fallback state applied
    assert quote_calls == ["AAPL"]  # cold symbol fetched once despite closed
    assert cache.get("AAPL").price == 999.0  # populated with the last close


@pytest.mark.asyncio
async def test_update_holds_last_price_on_zeroed_tick(monkeypatch):
    """Fix 2: a transient zeroed quote for a symbol that already has good
    data must not clobber the last-known price/prev with 0.
    """
    monkeypatch.setenv("FINNHUB_API_TOKEN", "tok")
    await StocksTicker.start(symbols=["AAPL"], session=mock.Mock())
    cache = get_cache()

    async def fake_status(exchange="US"):
        return {"isOpen": True, "session": "regular"}

    async def good_quote(sym):
        return {"c": 200.0, "d": 5.0, "dp": 2.5, "pc": 195.0}

    cache._provider._client.fetch_market_status = fake_status
    cache._provider._client.fetch_quote = good_quote
    await cache.update()
    quote = cache.get("AAPL")
    assert quote.price == 200.0
    assert quote.prev == 195.0
    spark_len_before = len(quote.spark)

    async def zeroed_quote(sym):
        return {"c": 0, "pc": 0}

    cache._provider._client.fetch_quote = zeroed_quote
    await cache.update()

    assert quote.price == 200.0  # held, not clobbered to 0
    assert quote.prev == 195.0
    assert len(quote.spark) == spark_len_before  # no-data tick doesn't append


@pytest.mark.asyncio
async def test_update_still_applies_good_data_after_holding(monkeypatch):
    """A symbol that legitimately has data still updates normally — the
    hold-last-price guard must not become a permanent freeze.
    """
    monkeypatch.setenv("FINNHUB_API_TOKEN", "tok")
    await StocksTicker.start(symbols=["AAPL"], session=mock.Mock())
    cache = get_cache()

    async def fake_status(exchange="US"):
        return {"isOpen": True, "session": "regular"}

    cache._provider._client.fetch_market_status = fake_status

    async def zeroed_quote(sym):
        return {"c": 0, "pc": 0}

    cache._provider._client.fetch_quote = zeroed_quote
    await cache.update()
    assert not cache.get("AAPL").has_data

    async def good_quote(sym):
        return {"c": 250.0, "d": 2.0, "dp": 0.8, "pc": 248.0}

    cache._provider._client.fetch_quote = good_quote
    await cache.update()
    quote = cache.get("AAPL")
    assert quote.price == 250.0
    assert quote.prev == 248.0


@pytest.mark.asyncio
async def test_start_warns_above_symbol_soft_cap(monkeypatch, caplog):
    """Fix 3: exceeding SYMBOL_SOFT_CAP logs exactly one warning and does
    not otherwise change behavior.
    """
    monkeypatch.delenv("FINNHUB_API_TOKEN", raising=False)
    caplog.set_level(logging.WARNING)
    symbols = [f"SYM{i}" for i in range(SYMBOL_SOFT_CAP + 5)]
    widget = await StocksTicker.start(symbols=symbols, session=mock.Mock())

    assert len(widget.feed_stories) == len(symbols)
    cap_warnings = [
        r
        for r in caplog.records
        if r.levelno == logging.WARNING and "60 req/min" in r.getMessage()
    ]
    assert len(cap_warnings) == 1


@pytest.mark.asyncio
async def test_start_no_warning_at_or_below_soft_cap(monkeypatch, caplog):
    monkeypatch.delenv("FINNHUB_API_TOKEN", raising=False)
    caplog.set_level(logging.WARNING)
    symbols = [f"SYM{i}" for i in range(SYMBOL_SOFT_CAP)]
    await StocksTicker.start(symbols=symbols, session=mock.Mock())

    cap_warnings = [r for r in caplog.records if "60 req/min" in r.getMessage()]
    assert cap_warnings == []


@pytest.mark.asyncio
async def test_start_tolerates_initial_fetch_failure(monkeypatch, caplog):
    """Covers the previously-uncovered except branch, now in the shared
    cache's `ensure_started`: the first `update()` raising must not
    prevent the widget from being constructed.
    """
    monkeypatch.setenv("FINNHUB_API_TOKEN", "tok")

    async def fake_status(self, exchange="US"):
        return {"isOpen": True, "session": "regular"}

    async def failing_quote(self, sym):
        raise RuntimeError("network down")

    monkeypatch.setattr(FinnhubClient, "fetch_market_status", fake_status)
    monkeypatch.setattr(FinnhubClient, "fetch_quote", failing_quote)

    caplog.set_level(logging.WARNING)
    widget = await StocksTicker.start(symbols=["AAPL"], session=mock.Mock())

    assert widget is not None
    assert len(widget.feed_stories) == 1
    assert any("initial fetch failed" in r.getMessage() for r in caplog.records)
