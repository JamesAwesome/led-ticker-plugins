# Stocks plugin: Twelve Data provider mode — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `provider = "twelvedata"` mode to `led-ticker-stocks` so one free Twelve Data key drives stocks + forex + crypto + indices, reusing the existing widget/layouts/trend-color/token surface. Finnhub stays the default and unchanged.

**Architecture:** A provider seam in the shared `QuoteCache` picks Finnhub (default) or Twelve Data at `ensure_started`. Market state becomes per-symbol on `SymbolQuote` (Finnhub stamps one global state onto all quotes; Twelve Data derives each from `is_market_open`). Value formatting auto-selects decimals by magnitude via `SymbolQuote.dp_decimals`, with a `decimals` override on the token source.

**Tech Stack:** Python 3.14, attrs, aiohttp, pytest + pytest-asyncio. Plugin in the `led-ticker-plugins` uv-workspace monorepo under `plugins/stocks/`.

## Global Constraints

- **Secrets are env-only.** Provider tokens come from environment ONLY, never config: `FINNHUB_API_TOKEN` (finnhub), `TWELVEDATA_API_KEY` (twelvedata). Never read a provider token from a config field. The token-leak regression tests (`test_config_token_is_ignored*` in `test_ticker.py`) must stay green.
- **No `from __future__ import annotations`** in any plugin source (PEP 649 / Python 3.14 rule — same as core).
- **Plugins import ONLY from `led_ticker.plugin`** — never `led_ticker.<internal>`.
- **Finnhub path stays byte-identical** in observable behavior. Equity prices are all `>= 10` so the magnitude rule yields 2 decimals (unchanged); the global-state stamp reproduces today's single-state rendering. All existing stocks tests must stay green.
- **`ruff check` clean** before any commit: `uv run --extra dev ruff check src/ tests/` from `plugins/stocks/`.
- **`attrs.define` classes**: fields with defaults must be `kw_only=True` when they follow non-default fields, matching the existing `SymbolQuote` / `StockSource` / `StocksTicker` style.
- **Version** is hatch-vcs / git-tag driven — do NOT hand-edit a version. The release (tag `stocks-v0.6.0`) happens after merge, outside this plan.
- Run all test commands from `plugins/stocks/`: `uv run --extra dev pytest tests/ -q`.

---

## File Structure

- `src/led_ticker_stocks/model.py` — **modify**: add `decimals_for(price)` helper + `state: MarketState` field on `SymbolQuote`.
- `src/led_ticker_stocks/twelvedata.py` — **create**: `TwelveDataClient` + `parse_quote` (TD `/quote` → `SymbolQuote` with per-symbol state + auto decimals).
- `src/led_ticker_stocks/providers.py` — **create**: `Provider` protocol + `FinnhubProvider` + `TwelveDataProvider` (wrap the HTTP clients, own the market-state semantics).
- `src/led_ticker_stocks/_cache.py` — **modify**: resolve a provider in `ensure_started`; refactor `update()` to a provider-neutral orchestration with a generalized per-symbol freeze.
- `src/led_ticker_stocks/source.py` — **modify**: `provider` field + provider-aware validation + `decimals` override.
- `src/led_ticker_stocks/ticker.py` — **modify**: `provider` field/param + provider-aware validation; story reads `quote.state`.
- `src/led_ticker_stocks/demo.py` — **modify**: seed demo quotes with magnitude decimals + `OPEN` state.
- `src/led_ticker_stocks/finnhub.py` — **modify**: `parse_quote` sets `dp_decimals` via `decimals_for` (keeps equities at 2).
- `plugins/stocks/examples/config.stocks-multiasset.bigsign.toml` — **create**: multi-asset smoke config.
- `plugins/stocks/README.md` — **modify**: multi-asset / provider section.
- Tests: `tests/test_model.py`, `tests/test_twelvedata.py` (new), `tests/test_providers.py` (new), `tests/test_cache.py`, `tests/test_source.py`, `tests/test_ticker.py`, `tests/test_demo.py`.

---

## Task 1: Auto-decimals helper + per-symbol state field on `SymbolQuote`

**Files:**
- Modify: `src/led_ticker_stocks/model.py`
- Modify: `src/led_ticker_stocks/finnhub.py`
- Modify: `src/led_ticker_stocks/demo.py`
- Test: `tests/test_model.py`, `tests/test_demo.py`

**Interfaces:**
- Consumes: nothing (foundation task).
- Produces:
  - `model.decimals_for(price: float) -> int` — magnitude→decimals: `abs(price) < 1` → 5, `< 10` → 4, else 2.
  - `SymbolQuote.state: MarketState` field, default `MarketState.CLOSED`.
  - `SymbolQuote.dp_decimals` is now set from `decimals_for(price)` at parse time (finnhub) and in demo seeding.

**Note on imports:** `model.py` will import `from led_ticker_stocks.state import MarketState`. `state.py` imports only stdlib + attrs (no `model` import), so there is no import cycle. Verify with the test in Step 2.

- [ ] **Step 1: Write the failing test** — append to `tests/test_model.py`:

```python
from led_ticker_stocks.model import decimals_for
from led_ticker_stocks.state import MarketState


def test_decimals_for_magnitude_bands():
    assert decimals_for(0.00042) == 5   # sub-1 (some crypto)
    assert decimals_for(0.5) == 5
    assert decimals_for(1.14669) == 4   # forex
    assert decimals_for(9.99) == 4
    assert decimals_for(208.89) == 2    # equity
    assert decimals_for(64906.62) == 2  # crypto large
    assert decimals_for(-3.5) == 4      # magnitude, not sign


def test_symbol_quote_defaults_to_closed_state():
    from led_ticker_stocks.model import SymbolQuote

    q = SymbolQuote(sym="AAPL", price=0.0, prev=0.0)
    assert q.state is MarketState.CLOSED
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev pytest tests/test_model.py -q`
Expected: FAIL — `ImportError: cannot import name 'decimals_for'`.

- [ ] **Step 3: Implement in `model.py`**

Add the import near the top (after the existing `import` lines):

```python
from led_ticker_stocks.state import MarketState
```

Add the helper (place it just above `format_price`):

```python
def decimals_for(price: float) -> int:
    """Pick display decimals from a value's magnitude.

    Lets one code path render every asset class sensibly: forex rates
    (~1.15) need 4 decimals, sub-1 values 5, and equities / large crypto
    (>=10) the usual 2. Finnhub equity prices are all >=10, so this yields
    2 there — unchanged from the old fixed default.
    """
    m = abs(price)
    if m < 1:
        return 5
    if m < 10:
        return 4
    return 2
```

Add the `state` field to `SymbolQuote` (after `low: float | None = None`):

```python
    state: MarketState = MarketState.CLOSED
```

- [ ] **Step 4: Set `dp_decimals` from magnitude in `finnhub.parse_quote`**

In `src/led_ticker_stocks/finnhub.py`, `parse_quote`, import and apply the helper. Change the `SymbolQuote(...)` construction so `dp_decimals` is computed:

```python
def parse_quote(sym, payload):
    from led_ticker_stocks.model import SymbolQuote, decimals_for

    high = payload.get("h")
    low = payload.get("l")
    price = float(payload.get("c") or 0.0)
    return SymbolQuote(
        sym=sym,
        price=price,
        prev=float(payload.get("pc") or 0.0),
        d=payload.get("d"),
        dp=payload.get("dp"),
        dp_decimals=decimals_for(price),
        high=float(high) if high is not None else None,
        low=float(low) if low is not None else None,
    )
```

- [ ] **Step 5: Seed demo quotes with magnitude decimals + OPEN state**

In `src/led_ticker_stocks/demo.py`, `seed_quotes`, set `dp_decimals` and `state`:

```python
def seed_quotes(symbols):
    from led_ticker_stocks.model import decimals_for
    from led_ticker_stocks.state import MarketState

    out = {}
    for sym in symbols:
        p = _seed_price(sym)
        out[sym] = SymbolQuote(
            sym=sym, price=p, prev=p, dp_decimals=decimals_for(p), state=MarketState.OPEN
        )
        out[sym].spark.append(p)
    return out
```

- [ ] **Step 6: Add a demo-state test** — append to `tests/test_demo.py`:

```python
def test_seeded_demo_quotes_are_open_with_magnitude_decimals():
    from led_ticker_stocks.demo import seed_quotes
    from led_ticker_stocks.state import MarketState

    q = seed_quotes(["AAPL"])["AAPL"]
    assert q.state is MarketState.OPEN
    assert q.dp_decimals == 2  # _seed_price is 50-500 -> >=10 -> 2
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `uv run --extra dev pytest tests/test_model.py tests/test_demo.py tests/test_finnhub.py -q`
Expected: PASS. `test_finnhub.py` stays green (equity prices >= 10 → 2 decimals).

- [ ] **Step 8: Full suite + lint**

Run: `uv run --extra dev pytest tests/ -q && uv run --extra dev ruff check src/ tests/`
Expected: PASS, clean.

- [ ] **Step 9: Commit**

```bash
git add src/led_ticker_stocks/model.py src/led_ticker_stocks/finnhub.py src/led_ticker_stocks/demo.py tests/test_model.py tests/test_demo.py
git commit -m "feat(stocks): decimals_for magnitude helper + per-symbol quote state"
```

---

## Task 2: Twelve Data HTTP client + parser

**Files:**
- Create: `src/led_ticker_stocks/twelvedata.py`
- Test: `tests/test_twelvedata.py`

**Interfaces:**
- Consumes: `model.SymbolQuote`, `model.decimals_for`, `state.MarketState` (Task 1).
- Produces:
  - `twelvedata.TwelveDataClient(token, session)` with `async fetch_quote(sym) -> dict` — `GET https://api.twelvedata.com/quote?symbol=<sym>&apikey=<token>`; raises on non-200 (mirrors `FinnhubClient._get`).
  - `twelvedata.parse_quote(sym: str, payload: dict) -> SymbolQuote` — maps TD's string fields to floats, sets `state` from `is_market_open`, sets `dp_decimals` via `decimals_for`.
  - `twelvedata.QUOTE_URL` constant.

**TD `/quote` payload shape** (verified live with the `demo` key):
`{"symbol":"EUR/USD","open":"1.14634","high":"1.14689","low":"1.14618","close":"1.14669","previous_close":"1.14633","change":"0.00036","percent_change":"0.0314","is_market_open":true, ...}`. All numerics are STRINGS. An error payload is `{"code":401,"message":"...","status":"error"}` returned with a non-200 HTTP status.

- [ ] **Step 1: Write the failing test** — create `tests/test_twelvedata.py`:

```python
import unittest.mock as mock

import aiohttp
import pytest

from led_ticker_stocks.state import MarketState
from led_ticker_stocks.twelvedata import QUOTE_URL, TwelveDataClient, parse_quote


def _mock_session(json_body, status=200, capture=None):
    """aiohttp session mock: .get(url, params=) yields an async ctx whose
    response has .status, async .json(), and a raising .raise_for_status().
    Mirrors tests/test_finnhub.py._mock_session."""
    session = mock.Mock()
    resp = mock.AsyncMock()
    resp.status = status
    resp.json = mock.AsyncMock(return_value=json_body)

    def _raise_for_status():
        if status >= 400:
            raise aiohttp.ClientResponseError(
                request_info=mock.Mock(), history=(), status=status
            )

    resp.raise_for_status = mock.Mock(side_effect=_raise_for_status)
    ctx = mock.AsyncMock()
    ctx.__aenter__ = mock.AsyncMock(return_value=resp)
    ctx.__aexit__ = mock.AsyncMock(return_value=False)

    def _get(url, params=None):
        if capture is not None:
            capture["url"] = url
            capture["params"] = params
        return ctx

    session.get = mock.Mock(side_effect=_get)
    return session


_FOREX = {
    "symbol": "EUR/USD",
    "open": "1.14634",
    "high": "1.14689",
    "low": "1.14618",
    "close": "1.14669",
    "previous_close": "1.14633",
    "change": "0.00036",
    "percent_change": "0.0314",
    "is_market_open": True,
}

_STOCK_CLOSED = {
    "symbol": "AAPL",
    "close": "208.89",
    "previous_close": "210.35",
    "change": "-1.46",
    "percent_change": "-0.694",
    "high": "211.0",
    "low": "207.5",
    "is_market_open": False,
}


def test_parse_forex_maps_string_fields_to_floats():
    q = parse_quote("EUR/USD", _FOREX)
    assert q.sym == "EUR/USD"
    assert q.price == pytest.approx(1.14669)
    assert q.prev == pytest.approx(1.14633)
    assert q.d == pytest.approx(0.00036)
    assert q.dp == pytest.approx(0.0314)
    assert q.high == pytest.approx(1.14689)
    assert q.low == pytest.approx(1.14618)
    assert q.has_data


def test_parse_sets_open_state_from_is_market_open():
    assert parse_quote("EUR/USD", _FOREX).state is MarketState.OPEN
    assert parse_quote("AAPL", _STOCK_CLOSED).state is MarketState.CLOSED


def test_parse_sets_magnitude_decimals():
    assert parse_quote("EUR/USD", _FOREX).dp_decimals == 4     # ~1.15
    assert parse_quote("AAPL", _STOCK_CLOSED).dp_decimals == 2  # ~209


def test_parse_missing_high_low_is_none():
    payload = {"symbol": "X", "close": "5.0", "previous_close": "4.0",
               "is_market_open": True}
    q = parse_quote("X", payload)
    assert q.high is None and q.low is None


def test_parse_zeroed_is_no_data():
    payload = {"symbol": "ZZZ", "close": "0", "previous_close": "0",
               "is_market_open": False}
    q = parse_quote("ZZZ", payload)
    assert not q.has_data


async def test_fetch_quote_injects_apikey_and_symbol():
    captured = {}
    session = _mock_session(_FOREX, capture=captured)
    client = TwelveDataClient("tok", session=session)
    await client.fetch_quote("EUR/USD")
    assert captured["url"] == QUOTE_URL
    assert captured["params"]["apikey"] == "tok"
    assert captured["params"]["symbol"] == "EUR/USD"


async def test_fetch_quote_raises_on_non_200():
    session = _mock_session({"code": 401, "status": "error"}, status=401)
    client = TwelveDataClient("tok", session=session)
    with pytest.raises(aiohttp.ClientResponseError):
        await client.fetch_quote("EUR/USD")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev pytest tests/test_twelvedata.py -q`
Expected: FAIL — `ModuleNotFoundError: led_ticker_stocks.twelvedata`.

- [ ] **Step 3: Implement `src/led_ticker_stocks/twelvedata.py`**

```python
"""Twelve Data REST client (free tier): one uniform /quote across asset classes.

Unlike Finnhub (equities only, separate market-status call), Twelve Data's
/quote covers stocks, forex, and crypto with an identical response shape and
a per-symbol `is_market_open` flag baked in — so a mixed config gets correct
per-symbol market state with no extra request. All numeric fields arrive as
STRINGS; parse_quote coerces them. Token from TWELVEDATA_API_KEY (env only).
"""

import logging

from led_ticker_stocks.model import SymbolQuote, decimals_for
from led_ticker_stocks.state import MarketState

QUOTE_URL = "https://api.twelvedata.com/quote"


def _f(payload, key):
    """Coerce a TD string numeric to float; None for missing/blank."""
    v = payload.get(key)
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def parse_quote(sym, payload):
    price = _f(payload, "close") or 0.0
    prev = _f(payload, "previous_close") or 0.0
    state = MarketState.OPEN if payload.get("is_market_open") else MarketState.CLOSED
    return SymbolQuote(
        sym=sym,
        price=price,
        prev=prev,
        d=_f(payload, "change"),
        dp=_f(payload, "percent_change"),
        dp_decimals=decimals_for(price),
        high=_f(payload, "high"),
        low=_f(payload, "low"),
        state=state,
    )


class TwelveDataClient:
    def __init__(self, token, session):
        self._token = token
        self._session = session

    async def fetch_quote(self, sym):
        params = {"symbol": sym, "apikey": self._token}
        async with self._session.get(QUOTE_URL, params=params) as resp:
            if resp.status != 200:
                logging.warning("Twelve Data /quote failed: HTTP %s", resp.status)
                resp.raise_for_status()
            return await resp.json()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --extra dev pytest tests/test_twelvedata.py -q`
Expected: PASS.

- [ ] **Step 5: Lint + commit**

```bash
uv run --extra dev ruff check src/ tests/
git add src/led_ticker_stocks/twelvedata.py tests/test_twelvedata.py
git commit -m "feat(stocks): Twelve Data /quote client + parser (multi-asset, per-symbol state)"
```

---

## Task 3: Provider seam in `QuoteCache`

**Files:**
- Create: `src/led_ticker_stocks/providers.py`
- Modify: `src/led_ticker_stocks/_cache.py`
- Test: `tests/test_providers.py` (new), `tests/test_cache.py`

**Interfaces:**
- Consumes: `finnhub.FinnhubClient`/`parse_quote`, `twelvedata.TwelveDataClient`/`parse_quote`, `state.state_from_status`/`state_now_from_clock`, `model.SymbolQuote`, `MarketState` (Tasks 1-2).
- Produces:
  - `providers.FinnhubProvider(client)` / `providers.TwelveDataProvider(client)` each with:
    - `async fetch_market_state() -> MarketState | None` — Finnhub returns a global state (status call, clock fallback); Twelve Data returns `None` (state is per-symbol).
    - `async fetch_quote(sym) -> SymbolQuote` — fetch + parse.
  - `QuoteCache.ensure_started(session, *, interval, force_demo, provider="finnhub")` — resolves the provider from `provider` + the matching env token.
  - `_cache` module constant `_PROVIDER_ENV = {"finnhub": "FINNHUB_API_TOKEN", "twelvedata": "TWELVEDATA_API_KEY"}`.

**Freeze rule** (CORRECTED 2026-07-15 after the Task 3 review found a permanent-latch regression): a symbol is HELD this cycle iff it has been attempted AND **this cycle's global market state is CLOSED** — i.e. `sym in self._attempted AND global_state is MarketState.CLOSED`. Cold symbols always fetch once.

Do NOT gate on the per-quote `existing.state`: a held symbol skips its fetch, so `existing.state` never updates — gating on it latches the symbol CLOSED forever and it never resumes when the market reopens (dead panel until restart). Gate on `global_state`, which `fetch_market_state()` refreshes every cycle, so reopen (global_state → OPEN) unfreezes the symbol. For **Finnhub** this is byte-identical to the original code (`closed = self._state is CLOSED` recomputed each cycle) — same freeze on close, same resume on reopen, no one-cycle lag. For **Twelve Data** `global_state is None`, so `global_state is CLOSED` is False → TD symbols are never frozen here and fetch every cycle, which auto-detects each symbol's reopen from its own `is_market_open`; bound TD credit use with the poll interval (a per-symbol time-based re-probe freeze is possible future work, out of v1 scope). Per-symbol `existing.state` is still stamped on every fetched quote for the market CHIP (widget stories read `quote.state`) — it just isn't the freeze gate.

- [ ] **Step 1: Write the failing provider test** — create `tests/test_providers.py`:

```python
import unittest.mock as mock

from led_ticker_stocks.providers import FinnhubProvider, TwelveDataProvider
from led_ticker_stocks.state import MarketState


async def test_finnhub_provider_returns_global_state():
    client = mock.Mock()
    client.fetch_market_status = mock.AsyncMock(return_value={"isOpen": True})
    client.fetch_quote = mock.AsyncMock(return_value={"c": 10.0, "pc": 9.0})
    prov = FinnhubProvider(client)
    assert await prov.fetch_market_state() is MarketState.OPEN
    q = await prov.fetch_quote("AAPL")
    assert q.sym == "AAPL" and q.price == 10.0


async def test_finnhub_provider_falls_back_to_clock_on_status_error():
    client = mock.Mock()
    client.fetch_market_status = mock.AsyncMock(side_effect=RuntimeError("boom"))
    prov = FinnhubProvider(client)
    state = await prov.fetch_market_state()
    assert isinstance(state, MarketState)  # clock fallback, never raises


async def test_twelvedata_provider_state_is_per_symbol_none_global():
    client = mock.Mock()
    client.fetch_quote = mock.AsyncMock(
        return_value={"symbol": "EUR/USD", "close": "1.1", "previous_close": "1.0",
                      "is_market_open": True}
    )
    prov = TwelveDataProvider(client)
    assert await prov.fetch_market_state() is None
    q = await prov.fetch_quote("EUR/USD")
    assert q.state is MarketState.OPEN
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev pytest tests/test_providers.py -q`
Expected: FAIL — `ModuleNotFoundError: led_ticker_stocks.providers`.

- [ ] **Step 3: Implement `src/led_ticker_stocks/providers.py`**

```python
"""Provider seam: Finnhub (global market state) vs Twelve Data (per-symbol).

`QuoteCache` orchestrates the poll loop and freeze; a Provider supplies just
the two provider-specific pieces: how market state is obtained, and how a
symbol's quote is fetched + parsed. Finnhub makes one global market-status
call per cycle (clock fallback on failure) and every quote shares that state;
Twelve Data has no separate status call — each /quote carries is_market_open,
so fetch_market_state() returns None and per-symbol state rides on the quote.
"""

import logging

from led_ticker_stocks import finnhub, twelvedata
from led_ticker_stocks.state import (
    MarketState,
    state_from_status,
    state_now_from_clock,
)


class FinnhubProvider:
    def __init__(self, client):
        self._client = client

    async def fetch_market_state(self):
        try:
            status = await self._client.fetch_market_status()
            return state_from_status(status)
        except Exception as e:
            logging.warning(
                "stocks Finnhub: market-status request failed (%s); "
                "falling back to the US/Eastern clock",
                e,
            )
            return state_now_from_clock()

    async def fetch_quote(self, sym) -> "object":
        return finnhub.parse_quote(sym, await self._client.fetch_quote(sym))


class TwelveDataProvider:
    def __init__(self, client):
        self._client = client

    async def fetch_market_state(self):
        return None  # per-symbol; each quote carries is_market_open

    async def fetch_quote(self, sym):
        return twelvedata.parse_quote(sym, await self._client.fetch_quote(sym))
```

- [ ] **Step 4: Run provider tests to verify they pass**

Run: `uv run --extra dev pytest tests/test_providers.py -q`
Expected: PASS.

- [ ] **Step 5: Write the failing cache tests** — append to `tests/test_cache.py`:

```python
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


import asyncio


def _install_prov(cache, prov):
    cache._provider = prov
    cache._started = True
    cache._poll_lock = asyncio.Lock()


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
            return SymbolQuote(sym=sym, price=5.0, prev=4.0,
                               dp_decimals=decimals_for(5.0),
                               state=MarketState.CLOSED)

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
            return SymbolQuote(sym=sym, price=5.0, prev=4.0,
                               dp_decimals=decimals_for(5.0), state=box["s"])

    _install_prov(cache, _Prov())
    await cache.update()          # closed -> held
    assert calls == []
    box["s"] = MarketState.OPEN
    await cache.update()          # reopened -> MUST fetch again
    assert calls == ["AAPL"]


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
            return SymbolQuote(sym=sym, price=5.0, prev=4.0,
                               dp_decimals=decimals_for(5.0), state=MarketState.CLOSED)

    _install_prov(cache, _Prov())
    await cache.update()
    assert calls == ["BTC/USD"]  # NOT frozen despite attempted + CLOSED
```

- [ ] **Step 6: Run cache tests to verify they fail**

Run: `uv run --extra dev pytest tests/test_cache.py -q -k "twelvedata or warm_closed or no_token_routes"`
Expected: FAIL — `ensure_started` has no `provider` param / `cache._provider` does not exist.

- [ ] **Step 7: Implement the provider seam in `_cache.py`**

7a. Update imports at the top of `_cache.py` — replace the `from led_ticker_stocks.finnhub import FinnhubClient, parse_quote` line and the `state` import block with:

```python
from led_ticker_stocks.finnhub import FinnhubClient, parse_quote
from led_ticker_stocks.providers import FinnhubProvider, TwelveDataProvider
from led_ticker_stocks.twelvedata import TwelveDataClient
from led_ticker_stocks.state import MarketState
```

(Keep `parse_quote` — `register()` still uses it to seed a zeroed quote. Drop the now-unused `state_from_status` / `state_now_from_clock` imports if present; they moved into `providers.py`.)

Add the env map near the module constants:

```python
_PROVIDER_ENV = {
    "finnhub": "FINNHUB_API_TOKEN",
    "twelvedata": "TWELVEDATA_API_KEY",
}
```

7b. Add a `_provider` slot in `__init__` (next to `self._client`):

```python
        self._provider: object | None = None
```

7c. Change `ensure_started`'s signature to accept `provider` and resolve it:

```python
    async def ensure_started(
        self,
        session: object,
        *,
        interval: int = 60,
        force_demo: bool = False,
        provider: str = "finnhub",
    ) -> None:
```

Inside, replace the token/client-building block:

```python
        token = os.getenv(_PROVIDER_ENV.get(provider, "FINNHUB_API_TOKEN"), "")
        if force_demo or not token:
            self._demo_feed = DemoFeed(sorted(self._symbols))
            self._quotes = self._demo_feed.quotes
            self._state = MarketState.OPEN
        elif provider == "twelvedata":
            self._provider = TwelveDataProvider(TwelveDataClient(token, session))
        else:
            self._provider = FinnhubProvider(FinnhubClient(token, session))
```

(Delete the old `self._client = FinnhubClient(token, session)` assignment — `_client` is no longer used directly; `update()` goes through `_provider`.)

7d. Rewrite the live branch of `update()` (everything after the demo-feed early-return) to drive the provider:

```python
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
                held += 1
                continue
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
                # No fresh price, but adopt the state so the market CHIP
                # (widget reads quote.state) reflects reality even on a
                # no-trade tick. (The freeze gates on global_state, not this.)
                existing.state = fresh.state
                logging.debug(
                    "stocks QuoteCache: %s returned no data this tick — "
                    "holding last price",
                    sym,
                )
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
```

Remove the now-dead `closed = self._state is MarketState.CLOSED` block and the old status-fetch try/except (that logic now lives in `FinnhubProvider.fetch_market_state`).

7e. In `reset()`, add `self._provider = None` alongside `self._client = None`.

- [ ] **Step 8: Run the cache + provider tests**

Run: `uv run --extra dev pytest tests/test_cache.py tests/test_providers.py -q`
Expected: PASS.

- [ ] **Step 9: Full suite — confirm Finnhub path unchanged**

Run: `uv run --extra dev pytest tests/ -q`
Expected: PASS. If any existing `test_cache.py` test referenced `cache._client` or `fetch_market_status` on the cache directly, update it to the provider seam (the behavior it asserts — global state, closed-freeze — is preserved). Note any such change in the task report.

- [ ] **Step 10: Lint + commit**

```bash
uv run --extra dev ruff check src/ tests/
git add src/led_ticker_stocks/providers.py src/led_ticker_stocks/_cache.py tests/test_providers.py tests/test_cache.py
git commit -m "feat(stocks): provider seam in QuoteCache — finnhub | twelvedata, per-symbol freeze"
```

---

## Task 4: `provider` field + provider-aware validation + source `decimals` override; story reads per-symbol state

**Files:**
- Modify: `src/led_ticker_stocks/source.py`
- Modify: `src/led_ticker_stocks/ticker.py`
- Test: `tests/test_source.py`, `tests/test_ticker.py`

**Interfaces:**
- Consumes: `QuoteCache.ensure_started(..., provider=...)` (Task 3); `SymbolQuote.state` (Task 1).
- Produces:
  - `StockSource.provider: str = "finnhub"` (attrs field, kw_only) + `StockSource.decimals: int | None = None`; `update()` passes `provider=self.provider` to `ensure_started`; `_field_value` uses `self.decimals` when set.
  - **Minus-sign belt:** `update()` substitutes U+2212 `−` → ASCII `-` in the emitted token value (a token is rendered in an arbitrary user font that may lack U+2212, unlike the crawl BDF / hires-layout painters which control their own font). Ships the cure even before the core rasterizer fix (led-ticker PR #393) is released. See "Why" below.
  - `StocksTicker.provider: str = "finnhub"` (attrs field + `start()` param) → forwarded to `ensure_started`.
  - Both `validate_config`s: reject `/` symbols ONLY when `provider == "finnhub"`; reject an unknown `provider` value.
  - `_StockStory.draw` reads `quote.state` instead of `cache.state()`.

**Known providers constant:** define `_PROVIDERS = ("finnhub", "twelvedata")` in `source.py` and import it in `ticker.py` (single source of truth), OR define once in a shared spot. Simplest: define in `source.py`, `from led_ticker_stocks.source import _PROVIDERS` in `ticker.py`.

- [ ] **Step 1: Write the failing source tests** — append to `tests/test_source.py`:

```python
def test_validate_rejects_slash_symbol_for_finnhub():
    errs = StockSource.validate_config({"symbol": "EUR/USD"})  # provider defaults finnhub
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

    src = StockSource(id="s", provider="twelvedata", symbol="EUR/USD",
                      format="{price}", decimals=2)
    q = SymbolQuote(sym="EUR/USD", price=1.14669, prev=1.14,
                    dp_decimals=4, state=MarketState.OPEN)
    assert src._field_value(q, "price") == "1.15"  # forced 2, not auto 4


async def test_token_value_substitutes_u2212_minus_with_ascii(monkeypatch):
    """Minus-sign belt: emitted token value uses ASCII '-', not U+2212, so a
    negative renders in any user font (the panel showed '?' otherwise)."""
    from led_ticker_stocks._cache import get_cache
    from led_ticker_stocks.model import SymbolQuote, decimals_for
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

    src = StockSource(id="s", symbol="DKS", format="{price} {pct}")
    src._used_fields = ("price", "pct")
    await src.update()
    assert "−" not in src.current  # no U+2212
    assert "-" in src.current      # ASCII hyphen present
```

(Match the existing `StockSource(...)` construction style in `test_source.py` for required base fields like `id` — adjust the kwargs to whatever `PolledDataSource` requires there.)

- [ ] **Step 2: Run to verify failure**

Run: `uv run --extra dev pytest tests/test_source.py -q -k "slash or unknown_provider or decimals_override"`
Expected: FAIL.

- [ ] **Step 3: Implement in `source.py`**

Add the constant near the top (after `_DEFAULT_FORMAT`):

```python
_PROVIDERS = ("finnhub", "twelvedata")
```

Add the two attrs fields to `StockSource` (with the other kw_only fields):

```python
    provider: str = attrs.field(default="finnhub", kw_only=True)
    decimals: int | None = attrs.field(default=None, kw_only=True)
```

Rewrite the `/`-rejection in `validate_config` to be provider-aware, and add the provider-value check. Replace the existing `symbol` block:

```python
        provider = cfg.get("provider", "finnhub")
        if provider not in _PROVIDERS:
            errors.append(
                f"stocks.quote: unknown provider {provider!r} "
                f"(known: {', '.join(_PROVIDERS)})."
            )
        symbol = cfg.get("symbol")
        if not symbol:
            errors.append("stocks.quote: 'symbol' is required.")
        elif isinstance(symbol, str) and "/" in symbol and provider == "finnhub":
            errors.append(
                f"stocks.quote: {symbol!r} looks like forex — FX requires a paid "
                "Finnhub tier. Use provider = \"twelvedata\" for forex/crypto."
            )
```

In `_field_value`, use the override for every `format_price` call. Add a small helper at the top of the method:

```python
    def _field_value(self, q: SymbolQuote, name: str) -> Any:
        dec = self.decimals if self.decimals is not None else q.dp_decimals
        if name == "price":
            return format_price(q.price, dec)
        if name == "change":
            return format_change(q.change, dec)
        # ... (pct unchanged), prev/high/low/day_range use `dec` in place of
        #     q.dp_decimals in their format_price calls.
```

Update the `prev`, `high`, `low`, `day_range` branches to pass `dec` instead of `q.dp_decimals`. (`pct`, `arrow`, `symbol` are unaffected.)

In `update()`, pass the provider through AND apply the minus-sign belt to the emitted value:

```python
        await get_cache().ensure_started(
            self.session, interval=self.interval, provider=self.provider
        )
        q = get_cache().get(self.symbol)
        if q is None or not q.has_data:
            return
        fields = {name: self._field_value(q, name) for name in self._used_fields}
        # Minus-sign belt: a token is embedded in an arbitrary user message
        # font that may lack U+2212 MINUS SIGN (which format_change/format_pct
        # emit for negatives) — it renders as "?" there. Core PR #393 fixes
        # this generally in the hi-res rasterizer, but substitute here too so
        # the cure ships with the plugin, font-agnostic, before a core release.
        value = self.format.format(**fields).replace("−", "-")
        self._set_value(value)
```

**Why (root cause, led-ticker hardware 2026-07-15):** the token format `"{price} {pct}"` on a down symbol emits `−1.98%` (U+2212). U+2212 is absent from the core hi-res charset, so an Inter-Bold `message` drew core's `?` fallback → `DKS 207.19 ?1.98%` on the panel. The crawl (BDF) and card/dashboard (plugin `_paint._subst`) already handle it; only the inline token slipped through.

- [ ] **Step 4: Write the failing ticker tests** — append to `tests/test_ticker.py`:

```python
def test_ticker_validate_rejects_slash_for_finnhub():
    msgs = StocksTicker.validate_config({"symbols": ["EUR/USD"]})
    assert any("forex" in m.lower() for m in msgs)


def test_ticker_validate_accepts_slash_for_twelvedata():
    msgs = StocksTicker.validate_config(
        {"symbols": ["EUR/USD"], "provider": "twelvedata"}
    )
    assert msgs == []


def test_ticker_validate_rejects_unknown_provider():
    msgs = StocksTicker.validate_config({"symbols": ["AAPL"], "provider": "bogus"})
    assert any("provider" in m.lower() for m in msgs)


async def test_start_forwards_provider_to_cache(monkeypatch):
    import led_ticker_stocks.ticker as tk

    captured = {}

    async def _ensure(self, session, *, interval=60, force_demo=False,
                      provider="finnhub"):
        captured["provider"] = provider

    monkeypatch.setattr(tk.QuoteCache, "ensure_started", _ensure)
    await StocksTicker.start(
        symbols=["EUR/USD"], session=object(), provider="twelvedata", demo=False
    )
    assert captured["provider"] == "twelvedata"


def test_story_reads_per_symbol_state(canvas, monkeypatch):
    """A story draws with its own symbol's quote.state, not a global."""
    from led_ticker_stocks._cache import get_cache
    from led_ticker_stocks.model import SymbolQuote
    from led_ticker_stocks.state import MarketState

    cache = get_cache()
    cache.register(["BTCUSD"])
    q = cache.get("BTCUSD")
    q.price, q.prev, q.state = 100.0, 90.0, MarketState.OPEN
    story = tk_story("BTCUSD")  # helper below or inline _StockStory(...)
    # draw must not raise and must use OPEN state (LIVE chip). Assert via the
    # state STATE_META lookup path: patch draw_crawl_story to capture `state`.
```

For the last test, prefer a focused capture: monkeypatch the layout function the story dispatches to and assert the `state` argument equals `quote.state`. Keep it minimal — construct `_StockStory(sym="BTCUSD", layout="crawl", all_symbols=["BTCUSD"])` and patch `led_ticker_stocks.ticker.LAYOUTS["crawl"]` (or the imported symbol) to a capturing stub. If the existing `test_ticker.py` already has a pattern for exercising `draw`, mirror it.

- [ ] **Step 5: Run to verify failure**

Run: `uv run --extra dev pytest tests/test_ticker.py -q -k "provider or per_symbol_state"`
Expected: FAIL.

- [ ] **Step 6: Implement in `ticker.py`**

Add the import:

```python
from led_ticker_stocks.source import _PROVIDERS
```

Add the attrs field (with the other kw_only fields, near `demo`):

```python
    provider: str = attrs.field(default="finnhub", kw_only=True)
```

Make `validate_config` provider-aware — replace the `symbols` `/` loop and add the provider check:

```python
        provider = cfg.get("provider", "finnhub")
        if provider not in _PROVIDERS:
            msgs.append(
                f"stocks.ticker: unknown provider {provider!r} "
                f"(known: {', '.join(_PROVIDERS)})"
            )
        if provider == "finnhub":
            for s in symbols:
                if "/" in s:
                    msgs.append(
                        f"stocks.ticker: {s!r} looks like forex — FX requires a paid "
                        "Finnhub tier. Use provider = \"twelvedata\" for forex/crypto"
                    )
```

Add `provider` to `start()`'s signature and forward it. Add the parameter:

```python
        provider: str = "finnhub",
```

Include it in the `cls(...)` construction (it's an attrs field, so it also flows via `valid`), and pass it to `ensure_started`:

```python
        await get_cache().ensure_started(
            session, interval=update_interval, force_demo=demo, provider=provider
        )
```

In `_StockStory.draw`, replace `state = cache.state()` with the per-symbol read:

```python
        quote = self._quote_for(cache, self.sym)
        state = quote.state
```

(Remove the now-unused `state = cache.state()` line. For held layouts the same `state` is passed through.)

- [ ] **Step 7: Run source + ticker tests**

Run: `uv run --extra dev pytest tests/test_source.py tests/test_ticker.py -q`
Expected: PASS — including the token-leak regressions (`test_config_token_is_ignored*`).

- [ ] **Step 8: Full suite + lint**

Run: `uv run --extra dev pytest tests/ -q && uv run --extra dev ruff check src/ tests/`
Expected: PASS, clean.

- [ ] **Step 9: Commit**

```bash
git add src/led_ticker_stocks/source.py src/led_ticker_stocks/ticker.py tests/test_source.py tests/test_ticker.py
git commit -m "feat(stocks): provider field + provider-aware validation + source decimals; per-symbol chip state"
```

---

## Task 5: Multi-asset smoke config + README

**Files:**
- Create: `plugins/stocks/examples/config.stocks-multiasset.bigsign.toml`
- Modify: `plugins/stocks/README.md`
- Test: none (config is exercised by the plugin's existing render/validate smoke harness if present; otherwise validated manually per Step 3).

**Interfaces:**
- Consumes: everything from Tasks 1-4 (`provider = "twelvedata"`, auto-format, per-symbol state).
- Produces: a runnable example + user-facing docs for the provider.

- [ ] **Step 1: Create the smoke config**

`plugins/stocks/examples/config.stocks-multiasset.bigsign.toml`:

```toml
# Multi-asset stock/forex/crypto ticker via Twelve Data (one free key).
# Requires: pip install led-ticker-stocks==0.6.0 ; led-ticker-core >= 4.14.0
# Set TWELVEDATA_API_KEY in .env (free key: https://twelvedata.com/pricing).
# Run in demo mode with no key: every widget/source below still animates.

[display]
rows = 32
cols = 64
chain = 8
default_scale = 4

[title]
delay = 3

[transitions]
default = "push_left"
between_sections = "dissolve"

# --- A dashboard-style card cycling a stock, a forex pair, and crypto ---
[[playlist.section]]
mode = "one_at_a_time"
hold_time = 5

[[playlist.section.widget]]
type = "stocks.ticker"
provider = "twelvedata"
symbols = ["AAPL", "EUR/USD", "BTC/USD"]
layout = "card"
update_interval = 60

# --- A mixed-color inline token line: white label + trend-colored price ---
[[source]]
id = "eurusd"
type = "stocks.quote"
provider = "twelvedata"
symbol = "EUR/USD"
format = "{price}"
color = { style = "stocks.trend", symbol = "EUR/USD" }

[[playlist.section]]
mode = "slideshow"
hold_time = 6

[[playlist.section.widget]]
type = "message"
text = "EUR/USD :eurusd:"
font = "Inter-Bold"
font_size = 44
font_threshold = 80
font_color = [255, 255, 255]
```

- [ ] **Step 2: Validate the config**

From repo root (core `led-ticker` checkout, with the plugin installed in that env), or note in the report that validation requires the plugin installed:

```bash
led-ticker validate plugins/stocks/examples/config.stocks-multiasset.bigsign.toml
```

Expected: no errors. If the local env lacks the installed plugin, state that in the report and rely on the unit-tested `validate_config` paths from Task 4 instead.

- [ ] **Step 3: Update `README.md`**

Add a "Multi-asset via Twelve Data" section documenting:
- `provider = "twelvedata"` (default is `"finnhub"`), on both `stocks.ticker` and `stocks.quote`.
- Symbol formats: `AAPL` (stock), `EUR/USD` (forex), `BTC/USD` (crypto) — the slash routes the asset class; no exchange prefix.
- Free key from twelvedata.com, placed in `.env` as `TWELVEDATA_API_KEY` (env-only, never in config).
- Data is delayed (~1–15 min) on the free tier — fine at sign cadence.
- Finnhub stays the default and is equities-only (forex/crypto need `twelvedata`).
- Auto-formatting: forex shows 4 decimals, crypto/equities 2 with thousands separators — no config needed.

Match the README's existing heading style and tone.

- [ ] **Step 4: Commit**

```bash
git add plugins/stocks/examples/config.stocks-multiasset.bigsign.toml plugins/stocks/README.md
git commit -m "docs(stocks): multi-asset Twelve Data smoke config + README provider section"
```

---

## Task 6: Import-purity + registration sanity

**Files:**
- Modify: `tests/test_import_purity.py` (if it enumerates modules) — otherwise no change.
- Test: `tests/test_import_purity.py`, `tests/test_smoke.py`

**Interfaces:**
- Consumes: all new modules (`twelvedata.py`, `providers.py`).
- Produces: confirmation the new modules obey plugin import rules (only `led_ticker.plugin` for core symbols; no `from __future__`).

- [ ] **Step 1: Run the existing import-purity test against the new modules**

Run: `uv run --extra dev pytest tests/test_import_purity.py -q`
Expected: PASS. `providers.py` and `twelvedata.py` import only from `led_ticker_stocks.*` and stdlib/aiohttp — no `led_ticker.<internal>`, no `from __future__`. If the test globs `src/led_ticker_stocks/*.py`, the new files are already covered; confirm they pass.

- [ ] **Step 2: If the test enumerates a hardcoded module list, add the new modules**

Only if `test_import_purity.py` lists modules explicitly rather than globbing: add `twelvedata` and `providers`. If it globs, no change — note that in the report.

- [ ] **Step 3: Full suite final green**

Run: `uv run --extra dev pytest tests/ -q && uv run --extra dev ruff check src/ tests/`
Expected: PASS, clean.

- [ ] **Step 4: Commit (only if a file changed)**

```bash
git add tests/test_import_purity.py
git commit -m "test(stocks): cover twelvedata + providers modules in import-purity check"
```

---

## Post-implementation (outside this plan)

- **Docs-site PR** (separate, core `led-ticker` repo): add a "Multi-asset via Twelve Data" section to `docs/site/src/content/docs/widgets/stocks.mdx` — the `provider` knob, symbol formats, the free-key note, the delayed-data caveat. Not part of the plugin PR's merge gate.
- **Release:** tag `stocks-v0.6.0` after merge (hatch-vcs, gated publish flow) — the user approves the release.
- **Update the smoke-config header staleness note** in the existing DKS smoke configs if touched (per `project_colored_value_tokens` memory) — out of scope here.

## Self-Review

**Spec coverage:** provider seam (Task 3) ✓; TwelveDataClient + parse (Task 2) ✓; per-symbol state (Tasks 1, 3, 4) ✓; auto-format (Task 1) + source `decimals` override (Task 4) ✓; provider-aware validation (Task 4) ✓; minus-sign belt (Task 4) ✓ — pairs with the general core rasterizer fix in led-ticker PR #393; demo mode (Task 1) ✓; smoke config + README (Task 5) ✓; import purity (Task 6) ✓. Deferred widget prefix/suffix/decimals is explicitly out of scope per the 2026-07-15 trim — no task, matches the updated spec.

**Placeholder scan:** all code steps carry full code; the two "match existing style" notes (test base-field kwargs in Task 4 Step 1, story-draw capture in Task 4 Step 4) point at concrete existing patterns rather than leaving logic unwritten.

**Type consistency:** `provider: str` and `decimals: int | None` used identically across source/ticker; `fetch_market_state() -> MarketState | None` and `fetch_quote(sym) -> SymbolQuote` consistent between the two providers and their cache consumer; `SymbolQuote.state` set in finnhub parse (via global stamp), twelvedata parse (per-symbol), and demo seed. `_PROVIDERS` defined once in `source.py`, imported by `ticker.py`.
