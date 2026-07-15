# Stocks Phase 4 — `stocks.quote` inline-price source + shared quote cache (design spec)

**Date:** 2026-07-14
**Status:** approved (brainstorm) — pending user review before planning
**Home:** `led-ticker-plugins` monorepo, `plugins/stocks/` (branch `feat/stocks-phase4`)
**Builds on:** Phases 1–3 (`stocks-v0.3.0` — crawl/card/dashboard widgets, FinnhubClient, market-state machine, demo feed). Ships as **v0.4.0**.
**Analogs:** `weather.current` source (`plugins/weather/src/led_ticker_weather/source.py`) for the `PolledDataSource` + format-string pattern; core inline value tokens (`[[source]]` / `:id:`, `PolledDataSource`, `api.source`).

---

## 1. Summary

Add a **`stocks.quote` inline-value source** so a live price can be dropped into any text field as a `:stocks.<id>:` token (e.g. `text = "AAPL :stocks.aapl:"`). To keep the Finnhub free-tier budget sane when the ticker widget and multiple tokens reference overlapping symbols, introduce a **plugin-level shared `QuoteCache`**: one poll loop fetches the union of all registered symbols once per cycle, and both the source AND the (refactored) `stocks.ticker` widget read from it. AAPL is fetched once no matter how many tokens/widgets use it.

## 2. Decisions (brainstorm)

| Decision | Choice |
|---|---|
| Token default / fields | Default `format = "{price}"`; rich fields on tap (`price`/`change`/`pct`/`arrow`/`symbol`/`prev`/`high`/`low`/`day_range`) |
| Polling model | **Shared per-symbol `QuoteCache`** — dedup fetches across widget + all sources |
| Widget | **Refactored** onto the cache (its own `FinnhubClient`/`update()` loop removed; rendering untouched) |
| Demo tokens | No `FINNHUB_API_TOKEN` → the cache runs the synthesized feed; tokens show a moving demo price |

**Known limitation (documented):** inline tokens are plain-text substitution — the resolved string inherits the **host text's color**. A `▲`/`▼` in a token can't be independently green/red (unlike the widget). Note in README.

## 3. Shared `QuoteCache` (`_cache.py`)

A module-level singleton owning ALL Finnhub I/O for the plugin.

- **State:** `_quotes: dict[str, SymbolQuote]`, `_symbols: set[str]` (union of every registered symbol), `_state: MarketState`, `_started: bool`, the poll task handle, the resolved token, `_demo_feed | _client`.
- **API:**
  - `register(symbols: Iterable[str]) -> None` — add symbols to the union; if already polling, they're picked up next cycle.
  - `get(symbol: str) -> SymbolQuote | None` — read (never fetches).
  - `async ensure_started(session, *, interval=60) -> None` — idempotent; on first call resolves the env token (demo if absent), builds `FinnhubClient` or `DemoFeed`, and `spawn_tracked`s ONE `run_monitor_loop(self, effective_interval)`; `effective_interval = max(interval, len(symbols_at_start)+1)` and is recomputed as symbols grow.
  - `state() -> MarketState` — shared market state for consumers that dim by it (the widget).
  - `reset()` — test seam (drops the singleton state + cancels the task).
- **`update()` (the one poll cycle):** fetch `/stock/market-status` → set `_state`; if `CLOSED`, skip quote fetches (frozen, hold last); else round-robin `fetch_quote` each registered symbol, `parse_quote`, **stamp `flash_t` on a real price change** (so the widget's Phase-3 flash still fires), mutate the cached `SymbolQuote` in place (append spark on `has_data`). One INFO log per cycle. Demo: step the shared `DemoFeed` over the union, state OPEN.
- **Rate discipline:** the single loop polls `len(_symbols)` quotes + 1 status per cycle; `effective_interval` keeps it under 60/min per key. This is strictly better than today (the widget's own loop + N token loops would each poll independently).
- **Lifecycle:** the cache borrows the aiohttp `session` from the first consumer (the engine owns it). The poll task is `spawn_tracked` (cancelled on shutdown). No network at import.

## 4. The source — `StockSource` (`source.py`)

Mirrors `weather.current`'s `PolledDataSource` shape.

```toml
[[source]]
type = "stocks.quote"
id = "aapl"                 # → :stocks.aapl: in any text field
symbol = "AAPL"
format = "{price}"          # default; fields below
# interval = 60             # optional (folds into the cache cadence)
```
- `StockSource(PolledDataSource)`: fields `symbol`, `format` (default `"{price}"`), `placeholder` (`"…"`). On construction: `QuoteCache.register([symbol])` and (in the async start path) `ensure_started(session)`. Shows `placeholder` until the first value.
- **Fields exposed to `format`** (computed from the cached `SymbolQuote`): `price` (formatted via `model.format_price`), `change`, `pct`, `arrow` (`▲`/`▼`/`·`), `symbol`, `prev`, `high`/`low`/`day_range` (from `o`/`h`/`l` — extend `SymbolQuote` to retain `high`/`low` if not already). Only the fields referenced in `format` are computed (lazy, like weather's `_used_fields`).
- **`update()`** (core-driven per interval): READ `QuoteCache.get(symbol)` → compute the referenced fields → `self._set_value(self.format.format(**fields))`. No direct fetch (the cache owns I/O). No-data quote → keep the placeholder / last value.
- **`validate_config`**: `symbol` required; reject an FX-looking symbol (`/`) with the "forex requires a paid Finnhub tier" hint; `format` must be a string, parse-checked and dry-run over a typed `_SAMPLE` (weather's exact validation, catching unknown fields + bad conversion specs like `{price:zzz}`).
- **Registration:** `__init__.py` adds `api.source("quote")(StockSource)` alongside the existing `api.widget("ticker")(...)`.

## 5. Widget refactor (`ticker.py`)

Behavior-preserving; rendering untouched.
- `StocksTicker.start()`: `QuoteCache.register(symbols)` + `await ensure_started(session)` instead of building its own `FinnhubClient`/`_demo_feed` and spawning its own `run_monitor_loop`. Drop `StocksTicker.update()`, `_client`, `_demo_feed`, `_quotes`, `_state_ref` (the cache owns them).
- `_StockStory.draw`: read `QuoteCache.get(self.sym)` (and `QuoteCache.state()`) instead of `self.quotes[...]`/`self.state_ref[...]`. The dashboard watch column reads neighbors via `QuoteCache.get` too. Container-refresh still holds (stories re-read the live cache each pass).
- The **token env-only security** (Phase 1) moves into the cache (`os.getenv("FINNHUB_API_TOKEN")`); no config path to the token. The **flash** (Phase 3) still works — the cache stamps `flash_t`; stories read it.
- `validate_config` on the widget is unchanged.

## 6. Testing

- **QuoteCache** (unit, no network): `register` dedups; `update()` mutates cached quotes in place + stamps `flash_t` on change; CLOSED skips fetches (frozen); demo path steps the feed; `ensure_started` is idempotent and spawns exactly one loop; rate `effective_interval` math. Use `reset()` between tests (hermetic).
- **StockSource**: `validate_config` (symbol required, FX rejected, format dry-run for unknown fields + bad specs); `update()` reads the cache and renders `format` (default `{price}`, and a rich custom format); no-data → placeholder; lazy `_used_fields`.
- **Widget refactor**: the Phase-1/2/3 widget tests migrate to construct via the cache path — assert stories render live cache data, the flash still fires (cache stamps flash_t), the dashboard watch column reads neighbors from the cache, and no regression in the layouts. Keep them green.
- **Integration**: a config with the ticker + two `:stocks.*:` tokens over an overlapping symbol → the cache fetches each unique symbol once (assert the client is called once per symbol per cycle, not per consumer).
- **Demo**: no token → tokens resolve to a moving synthesized price; headless render of a `[[source]]`-in-message config shows a non-placeholder value.

## 7. Phasing (for the plan)

1. **`QuoteCache`** — the shared singleton + poll loop + demo + market-state + flash stamping + `reset()`; unit-tested against a mocked client.
2. **Widget refactor onto the cache** — migrate `StocksTicker`/`_StockStory`; keep all Phase 1–3 widget/render tests green.
3. **`StockSource`** — the `PolledDataSource` + fields + `validate_config` + registration; unit + integration (dedup) tests.
4. **Docs + example + release** — README (the `[[source]]` block, the field table, the token-color caveat), `examples/` config using a price token, `stocks-v0.4.0`.

## 8. Out of scope
- Indices/FX; the non-canonical layout variants; per-token independent color; sparkline/history in a token (a token is a scalar string). Change-field flash on tokens (tokens are plain text).
