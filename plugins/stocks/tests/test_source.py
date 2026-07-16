"""StockSource (`stocks.quote`) — inline-price value token reading the shared cache."""

import unittest.mock as mock

from led_ticker_stocks import _cache
from led_ticker_stocks.model import SymbolQuote, format_change
from led_ticker_stocks.source import _DEFAULT_FORMAT, StockSource


def _src(**kw):
    return StockSource(id="stocks.aapl", session=mock.Mock(), interval=60, **kw)


def _seed_started(symbol: str, **quote_kw) -> None:
    """Simulate an already-running, populated cache (e.g. a `stocks.ticker`
    widget in the same process already called `ensure_started`). Marking
    `_started` avoids `StockSource.update()`'s own idempotent self-start
    from clobbering the quote we're about to seed."""
    c = _cache.get_cache()
    c.register([symbol])
    c._started = True
    c._attempted.add(symbol)  # already fetched -> no late-registrant catch-up
    quote_kw.setdefault("price", 0.0)
    quote_kw.setdefault("prev", 0.0)
    c._quotes[symbol] = SymbolQuote(sym=symbol, **quote_kw)


# ── validate_config ─────────────────────────────────────────────────────────


def test_validate_requires_symbol():
    assert any("symbol" in m for m in StockSource.validate_config({}))


def test_validate_rejects_fx():
    msgs = StockSource.validate_config({"symbol": "EUR/USD"})
    assert any("forex" in m.lower() or "paid" in m.lower() for m in msgs)


def test_validate_rejects_unknown_field():
    msgs = StockSource.validate_config({"symbol": "AAPL", "format": "{bogus}"})
    assert any("bogus" in m for m in msgs)


def test_validate_config_valid_block():
    errs = StockSource.validate_config({"symbol": "AAPL", "format": "{symbol} {price}"})
    assert errs == []


def test_validate_config_default_format_ok():
    assert StockSource.validate_config({"symbol": "AAPL"}) == []


def test_validate_config_malformed_format_returns_error():
    errs = StockSource.validate_config({"symbol": "AAPL", "format": "{price"})
    assert any("malformed" in e for e in errs)


def test_validate_config_non_str_format():
    errs = StockSource.validate_config({"symbol": "AAPL", "format": 123})
    assert errs, "expected an error for non-str format, got none"
    assert any("string" in e for e in errs)


def test_validate_config_bad_conversion_spec():
    errs = StockSource.validate_config({"symbol": "AAPL", "format": "{symbol:d}"})
    assert errs, "expected an error for %d on a str field, got none"


def test_validate_config_valid_float_spec_like_field():
    # `price` is already a formatted string field; a plain :s spec is fine.
    errs = StockSource.validate_config({"symbol": "AAPL", "format": "{price:s}"})
    assert errs == []


def test_default_format_constant():
    assert _DEFAULT_FORMAT == "{price}"


# ── construction / placeholder ──────────────────────────────────────────────


def test_placeholder_until_first_update():
    s = _src(symbol="AAPL", placeholder="—")
    assert s.current == "—" and s.version == 0  # nothing fetched yet


def test_construction_registers_symbol_with_cache():
    _src(symbol="MSFT")
    assert "MSFT" in _cache.get_cache()._symbols


# ── update() reading the shared cache ───────────────────────────────────────


async def test_update_renders_price_from_cache():
    _seed_started("AAPL", price=317.31, prev=315.32, d=1.99, dp=0.6311)
    src = _src(symbol="AAPL", format="{price}")
    await src.update()
    assert src.current == "317.31"  # model.format_price
    assert src.version == 1


async def test_update_rich_format():
    _seed_started("AAPL", price=317.31, prev=315.32, d=1.99, dp=0.6311)
    src = _src(symbol="AAPL", format="{symbol} {price} {arrow}{pct}")
    await src.update()
    assert src.current == "AAPL 317.31 ▲+0.63%"


async def test_update_down_arrow():
    _seed_started("AAPL", price=310.0, prev=315.32, d=-5.32, dp=-1.69)
    src = _src(symbol="AAPL", format="{arrow}{change}")
    await src.update()
    # Minus-sign belt: the emitted token substitutes U+2212 -> ASCII '-'.
    assert src.current == "▼" + format_change(-5.32, 2).replace("−", "-")


async def test_update_flat_arrow():
    _seed_started("AAPL", price=315.32, prev=315.32, d=0.0, dp=0.0)
    src = _src(symbol="AAPL", format="{arrow}")
    await src.update()
    assert src.current == "·"


async def test_update_high_low_and_day_range():
    _seed_started("AAPL", price=317.31, prev=315.32, high=320.0, low=310.5)
    src = _src(symbol="AAPL", format="{day_range}")
    await src.update()
    assert src.current == "310.50–320.00"


async def test_update_high_low_missing_renders_em_dash():
    _seed_started("AAPL", price=317.31, prev=315.32)  # high/low default None
    src = _src(symbol="AAPL", format="{high}|{low}")
    await src.update()
    assert src.current == "—|—"


async def test_token_resolves_to_last_close_when_market_closed(monkeypatch):
    """End-to-end regression for the after-hours boot bug: a token booted while
    the market is CLOSED must still resolve to the last close, not sit on its
    "…" placeholder. The shared cache now fetches cold symbols even when closed
    (Finnhub /quote returns the last close in `c`), so the token populates."""
    monkeypatch.setenv("FINNHUB_API_TOKEN", "tok")
    c = _cache.get_cache()
    c.register(["AAPL"])
    await c.ensure_started(session=mock.Mock())  # initial fetch fails, tolerated

    async def closed_status(exchange="US"):
        return {"isOpen": False, "session": None}

    async def last_close(sym):
        return {"c": 252.4, "pc": 252.0, "d": 0.4, "dp": 0.16, "h": 253, "l": 251}

    c._provider._client.fetch_market_status = closed_status
    c._provider._client.fetch_quote = last_close
    await c.update()  # closed + cold AAPL -> fetched once -> populated

    src = _src(symbol="AAPL", format="{symbol} {price} {arrow}{pct}", placeholder="…")
    await src.update()
    assert src.current == "AAPL 252.40 ▲+0.16%"  # the close, NOT the placeholder


async def test_no_data_keeps_placeholder():
    # register() alone seeds a zeroed (no-data) quote; mark started + attempted
    # so update() neither self-starts a demo feed nor catch-up-fetches — this
    # simulates a symbol that WAS fetched but returned no data (e.g. bad ticker).
    c = _cache.get_cache()
    c.register(["AAPL"])
    c._started = True
    c._attempted.add("AAPL")
    src = _src(symbol="AAPL", format="{price}", placeholder="…")
    await src.update()
    assert src.current == "…"
    assert src.version == 0


async def test_update_only_computes_used_fields(monkeypatch):
    """Lazy field build: an unreferenced field that would raise must not stall
    update()."""
    _seed_started("AAPL", price=317.31, prev=315.32)
    src = _src(symbol="AAPL", format="{price}")

    def _boom(self, q, name):
        raise AssertionError(f"computed unused field {name!r}")

    # Patch _field_value to blow up on ANY call, then only allow "price" through.
    orig = StockSource._field_value

    def _guarded(self, q, name):
        if name != "price":
            _boom(self, q, name)
        return orig(self, q, name)

    monkeypatch.setattr(StockSource, "_field_value", _guarded)
    await src.update()
    assert src.current == "317.31"


# ── self-starting the shared cache (token-only config, no widget) ──────────


async def test_update_self_starts_cache_when_not_started():
    """A `[[source]]`-only config (no `stocks.ticker` widget) must still
    populate the cache: `update()` self-starts it (idempotently) so a
    token-only setup isn't stuck on the placeholder forever."""
    c = _cache.get_cache()
    assert c._started is False
    src = _src(symbol="AAPL", format="{price}")
    await src.update()
    assert c._started is True
    assert c.state() is not None
    # No FINNHUB_API_TOKEN in the test env -> demo mode seeds real data.
    assert src.current != src.placeholder


async def test_update_self_start_is_idempotent_across_calls():
    src = _src(symbol="AAPL", format="{price}")
    await src.update()
    task_after_first = _cache.get_cache()._task
    await src.update()
    assert _cache.get_cache()._task is task_after_first


# ── provider field + provider-aware validation ──────────────────────────────


def test_validate_rejects_slash_symbol_for_finnhub():
    # provider defaults to finnhub
    errs = StockSource.validate_config({"symbol": "EUR/USD"})
    assert any("forex" in e.lower() for e in errs)


def test_validate_accepts_slash_symbol_for_twelvedata():
    errs = StockSource.validate_config({"symbol": "EUR/USD", "provider": "twelvedata"})
    assert errs == []


def test_validate_rejects_unknown_provider():
    errs = StockSource.validate_config({"symbol": "AAPL", "provider": "bogus"})
    assert any("provider" in e.lower() for e in errs)


def test_decimals_override_forces_fixed_decimals():
    from led_ticker_stocks.model import SymbolQuote
    from led_ticker_stocks.state import MarketState

    src = StockSource(
        id="s", provider="twelvedata", symbol="EUR/USD", format="{price}", decimals=2
    )
    q = SymbolQuote(
        sym="EUR/USD", price=1.14669, prev=1.14, dp_decimals=4, state=MarketState.OPEN
    )
    assert src._field_value(q, "price") == "1.15"  # forced 2, not auto 4


async def test_token_value_substitutes_u2212_minus_with_ascii(monkeypatch):
    """Minus-sign belt: emitted token value uses ASCII '-', not U+2212, so a
    negative renders in any user font (the panel showed '?' otherwise)."""
    from led_ticker_stocks._cache import get_cache
    from led_ticker_stocks.model import decimals_for
    from led_ticker_stocks.state import MarketState

    cache = get_cache()
    cache.register(["DKS"])
    q = cache.get("DKS")
    q.price, q.prev = 207.19, 209.90  # down -> negative pct -> U+2212
    q.dp_decimals, q.state = decimals_for(207.19), MarketState.OPEN

    # Avoid real network: make ensure_started a no-op.
    async def _noop(*a, **k):
        return None

    monkeypatch.setattr(type(cache), "ensure_started", _noop)

    src = _src(symbol="DKS", format="{price} {pct}")
    src._used_fields = ("price", "pct")
    await src.update()
    assert "−" not in src.current  # no U+2212
    assert "-" in src.current  # ASCII hyphen present
