# Stocks Ticker — Phase 4 Implementation Plan (quote source + shared cache)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Add a `stocks.quote` inline-price source (`:stocks.<id>:` tokens) backed by a plugin-level shared `QuoteCache`, and refactor the shipped `stocks.ticker` widget to read from that cache (dedup Finnhub fetches across widget + all tokens). Ships as v0.4.0.

**Architecture:** One module-level `QuoteCache` singleton owns all Finnhub I/O: a single poll loop fetches the union of registered symbols once per cycle, freezes when the market's closed, is demo-aware, and stamps `flash_t` on price changes (so the Phase-3 flash still fires). Both the source and the (refactored) widget `register()` symbols and `get()` from the cache — nobody else fetches.

**Tech Stack:** Python 3.14, `led_ticker.plugin` (`PolledDataSource`, `run_monitor_loop`, `spawn_tracked`), pytest + HeadlessCanvas. `plugins/stocks/` on `feat/stocks-phase4`.

**Spec:** `docs/superpowers/specs/2026-07-14-stocks-phase4-quote-source-design.md`.

## Global Constraints

- Plugin SRC imports ONLY from `led_ticker.plugin` (+ sibling `led_ticker_stocks.*`); no unused imports; no `# type: ignore`; Python 3.14 (no `__future__`); parenthesis-free multi-except OK.
- **Token is env-only** (`FINNHUB_API_TOKEN`) — the cache reads it from env; NEVER a config path (preserve the Phase-1 security invariant; the config→token leak regression must stay closed).
- **No network at import.** `time.monotonic()`/`os.getenv` at runtime are fine (not a workflow script).
- Cache is a **module-level singleton** with a **`reset()`** test seam — tests MUST call it (autouse fixture) so state doesn't leak between tests.
- **Behavior-preserving widget refactor:** rendering, the Phase-3 flash, the dashboard watch column, and container-refresh (stories re-read live each pass) all keep working. All Phase 1–3 widget/render tests stay green.
- Rate discipline moves to the cache: one loop polls `len(symbols)` quotes + 1 status/cycle at `effective_interval = max(interval, len(symbols)+1)` — strictly better than N independent loops.
- Commands from WORKTREE ROOT (`~/projects/github/jamesawesome/led-ticker-plugins--stocks-phase4`): `uv run pytest plugins/stocks`, coverage `--cov=plugins/stocks/src` (≥90), `uv run ruff check plugins/stocks`, `ruff format --check`, `uv run pyright plugins/stocks/src`.

## File Structure

```
plugins/stocks/src/led_ticker_stocks/
  _cache.py     # NEW  QuoteCache singleton (register/get/state/ensure_started/update/reset) + module _CACHE
  model.py      # MOD  SymbolQuote gains high/low; parse_quote retains Finnhub h/l
  ticker.py     # MOD  StocksTicker + _StockStory read the cache (drop own client/loop/state)
  source.py     # NEW  StockSource(PolledDataSource): fields + format + validate_config
  __init__.py   # MOD  + api.source("quote")(StockSource)
tests/
  conftest.py   # MOD  autouse fixture: _CACHE.reset() before each test
  test_cache.py test_source.py                          # NEW
  test_ticker.py test_render_smoke.py ... (migrate)     # MOD
```

---

## Task 1: `QuoteCache` + SymbolQuote high/low

**Files:** Create `src/led_ticker_stocks/_cache.py`, `tests/test_cache.py`; Modify `model.py`, `tests/conftest.py`.

**Interfaces produced:**
- `model.SymbolQuote` gains `high: float | None = None`, `low: float | None = None` (kw fields). `finnhub.parse_quote` sets them from `payload.get("h")`/`payload.get("l")` (float-or-None).
- `_cache.QuoteCache`:
  - `register(symbols: Iterable[str]) -> None` — union into `_symbols`; seed `_quotes[s]` with a zeroed `SymbolQuote` if absent.
  - `get(symbol: str) -> SymbolQuote | None`
  - `state() -> MarketState`
  - `async ensure_started(self, session, *, interval: int = 60) -> None` — idempotent (guard on `_started`); resolve `token = os.getenv("FINNHUB_API_TOKEN","")`; no token → build `DemoFeed(sorted(_symbols))`, adopt its quotes, state OPEN; else `FinnhubClient(token, session)`; tolerate a failed initial `update()` (log warn); `spawn_tracked(run_monitor_loop(self, max(interval, len(_symbols)+1)))`.
  - `async update(self) -> None` — the one poll cycle (below).
  - `reset(self) -> None` — clear all state + cancel the spawned task (test seam).
- `_cache._CACHE = QuoteCache()` module singleton; `_cache.get_cache() -> QuoteCache` accessor (so consumers + tests share one instance).

`update()` logic (port from `ticker.py:217-250`, generalized to `_symbols`):
- Demo: ensure every symbol in `_symbols` is in the feed (add late registrants), `step()` once per symbol, state OPEN, INFO log; return.
- Live: `fetch_market_status()` → `state_from_status` (fallback `state_now_from_clock()` on exception); if CLOSED, INFO log + return (frozen). Else per symbol `fetch_quote` → `parse_quote`; **if `fresh.has_data and fresh.price != existing.price: existing.flash_t = time.monotonic()`** (Phase-3 flash); if `fresh.has_data` write `price/prev/d/dp/high/low` + `spark.append`; INFO log the updated count.

- [ ] **Step 1: Write failing tests** (`tests/test_cache.py`, mocked client — no network; hermetic via `reset()`):
```python
import pytest
from led_ticker_stocks import _cache
from led_ticker_stocks.model import SymbolQuote


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


@pytest.mark.asyncio
async def test_update_live_mutates_and_stamps_flash(monkeypatch):
    import aiohttp
    monkeypatch.setenv("FINNHUB_API_TOKEN", "tok")
    c = _cache.get_cache(); c.register(["AAPL"])
    await c.ensure_started(session=aiohttp.ClientSession())  # spawns loop; tolerate initial
    async def q(sym): return {"c": 200.0, "d": 5.0, "dp": 2.5, "pc": 195.0, "h": 201, "l": 194}
    async def st(exchange="US"): return {"isOpen": True, "session": "regular"}
    c._client.fetch_quote = q; c._client.fetch_market_status = st
    before = c.get("AAPL").flash_t
    await c.update()
    assert c.get("AAPL").price == 200.0 and c.get("AAPL").high == 201.0
    assert c.get("AAPL").flash_t != before  # stamped on change


@pytest.mark.asyncio
async def test_closed_skips_quotes(monkeypatch):
    import aiohttp
    monkeypatch.setenv("FINNHUB_API_TOKEN", "tok")
    c = _cache.get_cache(); c.register(["AAPL"])
    await c.ensure_started(session=aiohttp.ClientSession())
    calls = []
    async def q(sym): calls.append(sym); return {"c": 1, "pc": 1}
    async def st(exchange="US"): return {"isOpen": False, "session": None}
    c._client.fetch_quote = q; c._client.fetch_market_status = st
    await c.update()
    assert calls == []  # frozen when closed


@pytest.mark.asyncio
async def test_demo_no_token_synthesizes(monkeypatch):
    monkeypatch.delenv("FINNHUB_API_TOKEN", raising=False)
    import unittest.mock as m
    c = _cache.get_cache(); c.register(["AAPL", "MSFT"])
    await c.ensure_started(session=m.Mock())
    assert c.get("AAPL").has_data  # demo feed seeded
    await c.update()  # steps without error
```
Plus a `test_ensure_started_idempotent` (two calls → one task) and a `parse_quote` high/low test in `tests/test_finnhub.py` (or test_model).

- [ ] **Step 2: Run → FAIL** (`_cache` missing). — `uv run pytest plugins/stocks/tests/test_cache.py -v`
- [ ] **Step 3: Implement** `model.py` (add high/low + parse_quote), `_cache.py`, and add the autouse `_CACHE.reset()` to `tests/conftest.py` (so migrated widget tests are hermetic too).
- [ ] **Step 4: Run → PASS**; then `uv run pytest plugins/stocks -q` (existing tests still green — model change is additive), ruff + format + pyright clean.
- [ ] **Step 5: Commit** — `feat(stocks): shared QuoteCache (single poll loop, dedup, demo, flash) + SymbolQuote high/low`.

---

## Task 2: Refactor `stocks.ticker` onto the cache

**Files:** Modify `ticker.py`, `tests/test_ticker.py` (+ any widget/render test that constructs a live widget).

**Interfaces:**
- `_StockStory` drops the `quotes` + `state_ref` fields; instead reads `get_cache().get(self.sym)` and `get_cache().state()` in `draw()`. `all_symbols` stays (watch-column neighbor lookup → `get_cache().get(neighbor)`). A `None` from the cache (symbol not yet fetched) → render the no-data placeholder path (the layouts already handle a zeroed/absent quote — pass a seeded zeroed quote; the cache always seeds on register, so `get` returns a quote, never None, for registered symbols).
- `StocksTicker`: `__attrs_post_init__` builds `feed_stories` (per-symbol `_StockStory` with `focus_index`/`all_symbols`) but NO `_quotes`/`_client`/`_demo_feed`/`_state_ref`. `start()`: `get_cache().register(list(symbols))` then `await get_cache().ensure_started(session, interval=update_interval)`; drop the widget's own `run_monitor_loop`/`update()`. Keep `validate_config` unchanged. Keep `green_up`/`layout`/`padding` fields.
- The engine still treats the widget as a `Container` (`feed_stories`) — container-refresh re-reads stories each pass; stories read the live cache. (No widget-owned poll loop needed; the cache is the data monitor.)

- [ ] **Step 1: Update tests first (RED where behavior asserted).** The Phase-1/2/3 widget tests that monkeypatched `widget._client`/`_state_ref`/`_quotes` must migrate to drive the CACHE: seed via `get_cache().register([...])` + set `get_cache()._quotes[sym]` (or `ensure_started` + monkeypatch the cache client), and assert `_StockStory.draw` renders that data. E.g. rewrite `test_update_live_updates_shared_quotes` → assert the cache mutation surfaces in the story. Keep the flash test (Task-1 cache stamps flash_t; the story renders whiter — reuse `test_flash.py`'s approach but seed the cache). Keep the token-leak regression: assert a config-supplied `token` never reaches the cache client (the cache reads env only; `start()` has no token param). Run → the migrated tests FAIL against the un-refactored widget.
- [ ] **Step 2: Run → FAIL** (stories still read `self.quotes`). 
- [ ] **Step 3: Implement** the refactor. Verify no story reads `self.quotes`/`self.state_ref` anymore; `StocksTicker` has no `_client`/`_demo_feed`/`update()`.
- [ ] **Step 4: Run → PASS** — `uv run pytest plugins/stocks -v` (ALL green: cache, ticker, crawl, card, dashboard, flash, pulse, render smoke, import-purity, entry-point smoke). ruff + format + pyright clean. Confirm the token-leak regression tests still pass.
- [ ] **Step 5: Commit** — `refactor(stocks): stocks.ticker reads the shared QuoteCache (drops its own poll loop)`.

---

## Task 3: `StockSource` (`stocks.quote`) + registration

**Files:** Create `src/led_ticker_stocks/source.py`, `tests/test_source.py`; Modify `__init__.py`.

**Interfaces produced (mirror `plugins/weather/src/led_ticker_weather/source.py`):**
- `StockSource(PolledDataSource)` (`@attrs.define(eq=False)`): `symbol: str` (kw), `format: str = "{price}"` (kw), `placeholder: str = "…"` (kw), `_used_fields` (init=False, cached from `format` in `__attrs_post_init__`). On construct: `get_cache().register([symbol])`; set `self.current = placeholder`. In the async start path (however core starts a source — match weather; if weather calls `ensure_started`-equivalent, call `get_cache().ensure_started(self.session)`), ensure the cache is running.
- **Fields** (computed lazily from the cached `SymbolQuote`): `price` (`model.format_price(q.price, q.dp_decimals)`), `change` (`format_change`), `pct` (`format_pct`), `arrow` (`▲`/`▼`/`·`), `symbol`, `prev`, `high`, `low`, `day_range` (e.g. `"{low}–{high}"`). Only compute `_used_fields`.
- `async update(self)`: `q = get_cache().get(self.symbol)`; if `q is None or not q.has_data`: leave placeholder/last value and return; else compute referenced fields → `self._set_value(self.format.format(**fields))`.
- `validate_config(cls, cfg) -> list[str]` (weather's pattern): `symbol` required; FX-looking symbol (`/`) rejected with the paid-tier hint; `format` must be str, `string.Formatter().parse` guarded, unknown-field check against the field set, dry-run `format.format(**_SAMPLE)` for bad specs.
- `__init__.py`: add `api.source("quote")(StockSource)` (keep `api.widget("ticker")(StocksTicker)`).

- [ ] **Step 1: Write failing tests** (`tests/test_source.py`, autouse cache reset):
```python
def test_validate_requires_symbol():
    assert any("symbol" in m for m in StockSource.validate_config({}))

def test_validate_rejects_fx():
    assert any("forex" in m.lower() or "paid" in m.lower()
               for m in StockSource.validate_config({"symbol": "EUR/USD"}))

def test_validate_rejects_unknown_field():
    msgs = StockSource.validate_config({"symbol": "AAPL", "format": "{bogus}"})
    assert any("bogus" in m for m in msgs)

@pytest.mark.asyncio
async def test_update_renders_price_from_cache():
    from led_ticker_stocks import _cache
    from led_ticker_stocks.model import SymbolQuote
    c = _cache.get_cache(); c.register(["AAPL"])
    c._quotes["AAPL"] = SymbolQuote(sym="AAPL", price=317.31, prev=315.32, d=1.99, dp=0.6311)
    src = StockSource(symbol="AAPL", format="{price}")
    await src.update()
    assert src.current == "317.31"   # model.format_price

@pytest.mark.asyncio
async def test_update_rich_format():
    ...  # format="{symbol} {price} {arrow}{pct}" -> "AAPL 317.31 ▲+0.63%"

@pytest.mark.asyncio
async def test_no_data_keeps_placeholder():
    ...  # cache seeded zeroed -> current stays "…"
```
Plus a registration smoke: the entry-point loads a `stocks.quote` source (extend `test_smoke.py` / add a source-registration assert).

- [ ] **Step 2: Run → FAIL** (`source` missing).
- [ ] **Step 3: Implement** `source.py` + `__init__.py`. Read `weather/source.py` for the exact `PolledDataSource` construction/start contract (how `self.session` arrives, whether an `ensure_started` hook exists) and match it.
- [ ] **Step 4: Run → PASS**; full suite green; ruff + format + pyright clean.
- [ ] **Step 5: Commit** — `feat(stocks): stocks.quote inline-price source (reads the shared cache)`.

---

## Task 4: Dedup integration test + docs + example

**Files:** `tests/test_source.py` (integration), `README.md`, `CLAUDE.md`, `examples/config.stocks-token.smallsign.toml` (new).

- [ ] **Step 1: Dedup integration test** — register the same symbol via a widget-style `register` AND a source; monkeypatch the cache client's `fetch_quote` to count calls; run one `update()` cycle; assert the symbol is fetched **once** (not once-per-consumer). This is the teeth for the whole shared-cache premise.
- [ ] **Step 2: Docs** — README: a `## Inline price tokens` section (the `[[source]]` block, the field table, the **token inherits host-text color** caveat, the shared-cache/rate note, demo behavior). CLAUDE.md: the Phase-4 invariants (single `QuoteCache` owns all Finnhub I/O; widget + sources register/read; env-only token now in the cache; `reset()` test seam; flash stamped in the cache).
- [ ] **Step 3: Example** — `examples/config.stocks-token.smallsign.toml`: a `[[source]]` `stocks.quote` + a `message` using `:stocks.<id>:`; `demo`-friendly (renders offline). Validate it.
- [ ] **Step 4: Coverage gate + lint** — `uv run pytest plugins/stocks --cov=plugins/stocks/src` (≥90); ruff + format + pyright clean.
- [ ] **Step 5: Commit** — `docs(stocks): document inline price tokens + example; dedup integration test`.
- [ ] **Step 6: Controller** — headless-render the token example (demo) to confirm a live price substitutes into the message (not the placeholder); then `stocks-v0.4.0`.

---

## Deferred / out of scope
Indices/FX; per-token color; sparkline/history in a token; change-field flash on tokens. Widget rendering is unchanged this phase.

## Self-Review
- Spec §3 cache → T1; §4 source → T3; §5 widget refactor → T2; §6 testing → per-task + T4 dedup integration; §7 phasing → T1–T4. Covered.
- Signatures: `get_cache()` / `QuoteCache.register|get|state|ensure_started|update|reset` consistent T1↔T2↔T3. `SymbolQuote.high/low` added T1, read by source T3. `StockSource(symbol, format, placeholder)` T3 def + tests. Widget drops `_client/_demo_feed/_quotes/_state_ref/update` (T2) — no consumer references them after.
- Risk called out: T2 is the shipped-code refactor — its Step 1 migrates the existing widget tests to the cache path FIRST (RED) so the refactor is test-driven, and explicitly keeps the token-leak + flash regressions green.
