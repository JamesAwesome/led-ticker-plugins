# Stocks plugin: Twelve Data provider mode (multi-asset) — Design

**Date:** 2026-07-15
**Plugin:** `led-ticker-stocks` (monorepo `plugins/stocks/`)
**Ships as:** `stocks-v0.6.0`
**Status:** Approved — ready for implementation plan

## Goal

Let one free Twelve Data API key drive **stocks + forex + crypto + indices** on the
sign, by adding a `provider = "twelvedata"` mode to the existing stocks plugin. The
Finnhub path stays the default and is unchanged. The existing `stocks.ticker` widget,
its layouts, the `stocks.trend` color provider, and the `:stocks.x:` inline value token
all keep working against whichever provider is selected — only the data source swaps.

## Motivation

Finnhub's free tier is equities-only: forex and crypto return HTTP 403 (paid). This was
verified live (`/quote?symbol=OANDA:EUR_USD` → 403; `/quote?symbol=DKS` → 200). Twelve
Data's free tier (~800 credits/day, 8 req/min, ~1–15 min delayed) covers all asset
classes through **one uniform `/quote` endpoint**, verified live with the public `demo`
key:

| Symbol    | Asset  | `/quote` HTTP | `is_market_open` | Shape |
|-----------|--------|---------------|------------------|-------|
| `AAPL`    | stock  | 200           | `false` (wknd)   | open/high/low/close, previous_close, change, percent_change |
| `EUR/USD` | forex  | 200           | `true`           | *identical* |
| `BTC/USD` | crypto | 200           | *(24/7)*         | *identical* + rolling_1d/7d change |

Key properties Twelve Data gives us that Finnhub does not:
- **The symbol routes the asset class** on TD's side (`AAPL`→stock, `EUR/USD`→forex,
  `BTC/USD`→crypto). No asset-class config field is needed.
- **Per-symbol `is_market_open`** is baked into every quote — no separate market-status
  call, and mixed-asset configs get correct per-symbol state.
- Response maps 1:1 onto the existing `SymbolQuote`: `close`→`price`,
  `previous_close`→`prev`, and TD hands us `change` and `percent_change` directly.

## Non-goals (explicit scope boundaries)

- **Streaming / websockets.** Poll-only, same as today.
- **TD pre-market / post-market sessions.** TD `/quote` reports only open/closed;
  `PRE`/`AFTER` remain Finnhub-only states.
- **Indices-specific formatting** beyond the shared auto-decimals rule.
- **Symbol auto-discovery / search.** The user supplies exact symbols.
- **Mixing providers within one process.** The shared `QuoteCache` is single-mode
  (first consumer to start wins). A config that sets `provider = "finnhub"` on one
  source and `provider = "twelvedata"` on another resolves to whichever starts the
  cache first — a pre-existing property of the shared-cache design, documented, not
  newly introduced. (See "Open question / accepted limitation" below.)

## Architecture

### 1. Provider seam (`_cache.py`, new `providers/` or `twelvedata.py`)

Today `QuoteCache` hardcodes `FinnhubClient`, `parse_quote`, and `fetch_market_status`.
Introduce a small provider abstraction with two responsibilities: **fetch a quote** and
**supply market state**. The seam accommodates the Finnhub/TD asymmetry (Finnhub = one
global status call per cycle; TD = per-symbol state embedded in each quote).

Provider surface (informal protocol — the plan pins exact signatures):
- `async fetch_quote(sym) -> SymbolQuote` — fetch + parse folded together, so each
  provider owns its own payload→`SymbolQuote` mapping (including per-symbol state and
  auto-decimals; see §3).
- A market-state contribution: Finnhub fetches one global status per cycle and stamps
  the same `MarketState` onto every quote; Twelve Data derives each quote's state from
  its own `is_market_open`. The provider encapsulates which of these happens.

`QuoteCache.ensure_started` resolves the provider from the config `provider` value:
- `"finnhub"` (default): build `FinnhubClient`, token from `FINNHUB_API_TOKEN`.
  Behavior byte-identical to today.
- `"twelvedata"`: build `TwelveDataClient`, token from `TWELVEDATA_API_KEY`.

Token resolution stays **env-only** for both providers (CLAUDE.md: "Secrets belong in
`.env`, not `config.toml`"). No token / `force_demo` still routes to the offline
`DemoFeed`, unchanged.

`TwelveDataClient`:
- `GET https://api.twelvedata.com/quote?symbol=<sym>&apikey=<key>` (one credit/symbol).
  Auth via the `apikey` query param (TD also accepts an `Authorization: apikey <key>`
  header; query param is simplest and matches the verified calls).
- Parse TD's string-valued numeric fields (`close`, `previous_close`, `change`,
  `percent_change`, `high`, `low`) with float coercion tolerant of missing keys
  (mirrors `finnhub.parse_quote`'s `or 0.0` guards).
- Map `is_market_open` (bool) → `MarketState.OPEN` / `MarketState.CLOSED` on the quote.
- Non-200 (e.g. 401 bad key, 429 rate-limited) logs a warning and raises, matching
  `FinnhubClient._get` — the supervised poll loop already tolerates a raised cycle.

The `update()` cycle in `QuoteCache` dispatches through the provider so the closed-freeze
logic (`_attempted`, fetch-cold-once-then-hold) is preserved for both providers. For TD,
"closed" is evaluated per symbol from the quote's own state rather than a single global
flag; the freeze rule is unchanged in shape (cold symbol → always fetch once; warm
closed symbol → hold last value).

### 2. Per-symbol market state (`model.py`, `state.py`, `ticker.py`, layouts)

Add `state: MarketState = MarketState.CLOSED` to `SymbolQuote`.

- **Finnhub** `update()`: fetch the one global status (as today), then stamp that same
  `MarketState` onto every symbol's quote. Net rendering identical to today.
- **Twelve Data** `update()`: each quote carries its own state from `is_market_open`.
- `QuoteCache.state()` is retained for back-compat but the widget stories switch to
  reading `quote.state` (the focused symbol's state) for the market chip, so a mixed
  config shows the correct per-symbol chip (`LIVE` on `BTC/USD`, `CLSD` on `AAPL`).
- `state_from_status` / `state_from_clock` (Finnhub + fallback) are untouched.

This is the one genuine refactor. It removes the "one global market state" assumption
that was only ever correct for a single-exchange (US equities) provider.

### 3. Auto-format by magnitude (`model.py`)

`SymbolQuote.dp_decimals` already exists and `format_price` already emits thousands
separators (`f"{v:,.{decimals}f}"`). Auto-format = choose `dp_decimals` from the price
magnitude at parse time:

| `abs(price)` | decimals | example |
|--------------|----------|---------|
| `< 1`        | 5        | `0.00042` |
| `< 10`       | 4        | `EUR/USD → 1.14669` |
| `>= 10`      | 2        | `AAPL → 208.89`, `BTC/USD → 64,906.62` |

Finnhub quotes get the same magnitude rule applied (equity prices are all `>= 10` in
practice → 2 decimals → unchanged). This keeps one code path for both providers.

**Optional override (source only, v1):**
- `decimals: int` on `stocks.quote` — force a fixed decimal count (overrides the
  magnitude rule); applied in the source's `_field_value`. Cheap, non-redundant.

**Deferred (YAGNI trim, 2026-07-15):** widget-level `prefix` / `suffix` / `decimals`.
The auto-magnitude rule already renders forex/crypto correctly on the widget layouts with
zero config, and threading `prefix`/`suffix` through all three layouts (card/crawl/
dashboard) and their right-alignment math is invasive for cosmetic polish. On the token,
`prefix`/`suffix` are already covered by the `format` string (`format = "${price} USD"`).
Widget-level overrides are noted as a future pass, not v1 scope.

### 4. Provider-aware validation (`source.py`, `ticker.py`)

Both `StockSource.validate_config` and `StocksTicker.validate_config` currently reject a
`/` in a symbol ("FX requires a paid Finnhub tier"). Change: read `provider` from the
config (default `"finnhub"`) and apply the `/`-rejection **only for finnhub**. For
`twelvedata`, `/` symbols validate. Add validation that `provider` is one of the known
values (`finnhub`, `twelvedata`) with a clear message otherwise.

### 5. Demo mode

`DemoFeed` synthesizes data over whatever symbols are registered, so `demo = true` (or no
token) already works for FX/crypto symbols — the synthesized walk is provider-agnostic.
One check: the demo-seeded placeholder quote should get a sensible `dp_decimals` /
`state` so a demo `EUR/USD` renders with 4 decimals and a `LIVE` chip. The plan seeds
demo quotes through the same magnitude rule and marks them `OPEN` (demo is always "open").

### 6. Smoke config + docs

- New smoke config demonstrating multi-asset via Twelve Data (a stock, a forex pair, a
  crypto pair) using `provider = "twelvedata"`, hi-res Inter-Bold, and a mixed-color
  inline token line, mirroring the existing DKS smoke configs. Install pin bumped to
  `led-ticker-stocks==0.6.0`; header notes `TWELVEDATA_API_KEY` in `.env`.
- Docs: the stocks widget page (`docs/site/.../widgets/stocks.mdx` in the **core** repo)
  gains a "Multi-asset via Twelve Data" section — the `provider` knob, symbol formats
  (`EUR/USD`, `BTC/USD`), the free-key note (env-only), and the delayed-data caveat. The
  plugin README gains the same. (Docs live in the core/docs repos, not this monorepo — a
  follow-up docs PR, tracked, not part of the plugin PR's merge gate.)

## Data flow (unchanged in shape)

1. `stocks.quote` source or `stocks.ticker` widget registers its symbols with the shared
   `QuoteCache` and calls `ensure_started` (idempotent).
2. `ensure_started` resolves the provider (finnhub/twelvedata/demo) once, from the first
   consumer to start.
3. The single poll loop calls `QuoteCache.update()` each cycle → provider fetches quotes,
   parses to `SymbolQuote` (with per-symbol `state` + auto `dp_decimals`), applies the
   closed-freeze.
4. Widget stories and token sources read live `SymbolQuote`s each draw/tick; the
   `stocks.trend` color provider reads `.change`; formatting applies `dp_decimals` +
   overrides.

## Testing strategy

- **`TwelveDataClient` + parse:** unit tests against captured TD `/quote` payloads
  (stock/forex/crypto), asserting `SymbolQuote` fields, per-symbol `state` from
  `is_market_open`, and auto-`dp_decimals` by magnitude. Include a 401/429 payload → the
  client raises, the poll loop survives.
- **Provider resolution:** `ensure_started` builds the right client for
  `provider="twelvedata"` from `TWELVEDATA_API_KEY`; falls back to demo with no key;
  finnhub default path unchanged (existing tests stay green).
- **Per-symbol state:** a mixed config (one open, one closed symbol) renders two
  different chip states; Finnhub path still stamps one global state onto all quotes
  (regression: existing chip tests green).
- **Auto-format:** `decimals_for(price)` magnitude table (`1.14669` / `64,906.62` /
  `208.89`); source `decimals` override in `_field_value`.
- **Validation:** `/` symbol rejected for finnhub, accepted for twelvedata; unknown
  `provider` value rejected; existing finnhub validation tests unchanged.
- **Demo:** `demo = true` with `EUR/USD` synthesizes data, 4-decimal render, `LIVE` chip.
- **Token-leak / env-only regressions:** existing `test_config_token_is_ignored*` stay
  green; no provider token is ever read from config.

## Open question / accepted limitation

The shared `QuoteCache` is single-mode: `provider` is resolved once, by the first
consumer to start the cache. Two sources in one process requesting different providers is
therefore unsupported (last-writer-loses on which provider wins the start race). This
matches the existing `demo`-vs-live single-mode behavior and is documented as a
limitation. A future multi-provider cache (keyed by provider) is out of scope here.
