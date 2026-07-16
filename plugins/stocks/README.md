# led-ticker-stocks

A stock / equities ticker **plugin** for [led-ticker](https://github.com/JamesAwesome/led-ticker), backed by the [Finnhub](https://finnhub.io/) API. It contributes a `stocks.ticker` **Container widget** that cycles one price view per configured symbol, trend-colored green/red and dimmed by market state (full brightness while the market is open, dimmed while pre/post-market, dimmest while closed). Three layouts are registered and auto-selected by panel geometry — see [Layouts](#layouts):

- `crawl` (smallsign, ~160px) — a single scrolling line: `SYM  price  ▲/▼ change change%`.
- `card` (bigsign, ~256px) — a held hero card: symbol + price + change, a brand chip, a sparkline, a state-chip label, and paging dots.
- `dashboard` (longboi, ~512px) — a held trading dashboard: the same hero block plus a watch column showing the next symbols and a bigger sparkline.

All three layouts animate: the price line pops white on a change and settles back to amber (Bloomberg-style flash), the LIVE state chip breathes while the market is open, and the sparkline's tip pulses. It also contributes a `stocks.quote` **source** — a live `:id:` price token you can weave into any other widget's text (a headline, a two-row detail line, a clock/date composite) — see [Inline price tokens](#inline-price-tokens) — and a `stocks.trend` **color provider** that tints any text widget green/red/neutral by a symbol's day change, independent of which widget is doing the drawing — see [Trend color](#trend-color). **Scope:** Finnhub (the default provider) is US equities only; forex and crypto are available via `provider = "twelvedata"` — see [Multi-asset via Twelve Data](#multi-asset-via-twelve-data).

## Prerequisites

- A working [led-ticker](https://github.com/JamesAwesome/led-ticker) install.
- Internet access on the Pi (the widget calls the Finnhub REST API).
- A free [Finnhub](https://finnhub.io/register) account and API token — **or** run in `demo = true` mode with no token at all (see [Demo mode](#demo-mode-no-token-required)).

## Install

The widget auto-registers via the `led_ticker.plugins` entry point — once the package is installed, no `[plugins]` config change is needed.

**Into a containerized led-ticker (recommended):** add this package to `config/requirements-plugins.txt` (copy it from `config/requirements-plugins.example.txt`), then restart:

```bash
# in your led-ticker checkout
cp config/requirements-plugins.example.txt config/requirements-plugins.txt
# add the line below to config/requirements-plugins.txt, then:
docker compose restart
```

```text
led-ticker-stocks
```

**Standalone (a venv that already has led-ticker):**

```bash
pip install led-ticker-stocks
```

See the led-ticker [Plugins docs](https://docs.ledticker.dev/plugins/) for the constraint-based install the Docker image uses, and pin production signs to an exact version (`led-ticker-stocks==0.3.0`) so a restart doesn't silently pick up a new release.

## Configuration

Reference the widget in a playlist section by `type = "stocks.ticker"`:

```toml
[[playlist.section]]
mode = "ticker"

[[playlist.section.widget]]
type = "stocks.ticker"
symbols = ["AAPL", "MSFT", "NVDA", "TSLA"]
```

The **recommended** section `mode` depends on which layout your panel will auto-select (see [Layouts](#layouts) below):

- `crawl` (smallsign) wants `mode = "ticker"` (continuous side-by-side scroll) — the same shape as the built-in `crypto.coingecko` / `rss.feed` tickers. The crawl text is designed to keep moving; `slideshow` also works but holds each symbol still with nothing to look at until the next transition.
- `card` / `dashboard` (bigsign / longboi) are **held** layouts — they paint a full static view per symbol and don't scroll. Use `mode = "slideshow"` with a `hold_time` long enough to read (the smoke configs in `examples/` use `5.2`).

New to led-ticker configs? The [first-config tutorial](https://docs.ledticker.dev/tutorial/02-first-config/) walks through the overall structure — the block above shows just the stocks-specific keys.

### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `symbols` | list of strings | — | **Required.** Ticker symbols (e.g. `["AAPL", "MSFT"]`). US equities only — a symbol containing `/` (e.g. `"EUR/USD"`) fails validation with a message pointing at the FX limitation below. |
| `layout` | string | auto | Force a specific render layout (`"crawl"`, `"card"`, or `"dashboard"`). Omit this field and let the widget auto-select by real panel width — see [Layouts](#layouts). |
| `demo` | bool | `false` | Run against a seeded, offline random-walk feed instead of Finnhub — no token, no network call. See [Demo mode](#demo-mode-no-token-required). |
| `update_interval` | int | `60` | Seconds between Finnhub polls. The widget silently raises this to `len(symbols) + 1` if you set it lower — see [Rate limits](#rate-limits--api-token) below. |
| `padding` | int | `6` | Horizontal spacing (logical px) after each symbol's segment, before the next symbol. Crawl layout only — `card`/`dashboard` use a fixed layout grid instead. |
| `green_up` | bool | `true` | Set `false` to flip the up/down colors (green-down/red-up) for non-US market conventions. Applies to all three layouts. |

At least `symbols` must be a non-empty list — the widget fails at config validation otherwise (`led-ticker validate` catches this before boot).

### Layouts

`resolve_layout` auto-selects one of three registered layouts by the REAL (physical) panel width — a `layout =` override always wins if set:

| Layout | Auto-selected at | Built for | Shape |
|---|---|---|---|
| `crawl` | ≤160px wide | smallsign (160×16) | Single scrolling line per symbol: `SYM  price  ▲/▼ change change%`. |
| `card` | ~160–400px wide | bigsign (256×64) | Held hero card: brand chip + symbol + price + change line, a sparkline, a state-chip label, and paging dots showing position in the symbol list. |
| `dashboard` | ≥400px wide | longboi (512×64) | Held trading dashboard: the same hero block (chip + symbol + price + change + a "PREV" reference price) plus a bigger sparkline and a **watch column** listing the next 3 symbols with their percent change, and paging dots. |

`card` and `dashboard` are both **held** — they paint a complete static frame per symbol rather than scrolling (see the `mode` guidance above). Every symbol renders a brand chip: an abstract two-tone diagonal block, deterministically colored from a hash of the symbol (trademark-safe — never a logo or wordmark); `chip_colors` on `SymbolQuote` lets a future data source override the pair per-symbol.

The dashboard's watch column reads the widget's own full `symbols` list — it shows the neighbors of the currently-focused symbol, not anything from another widget. **Give the stocks widget its own section** (no sibling widgets) on longboi so the watch column always reflects this widget's symbol rotation.

Both held layouts animate: the price flashes white then settles back to amber on a change, the LIVE state chip breathes while the market is open, and the sparkline's tip pulses continuously.

### Demo mode (no token required)

Set `demo = true` (or simply omit `FINNHUB_API_TOKEN` from the environment — an unset token silently routes to the same demo feed, it is not an error) to drive prices from a deterministic, seeded random-walk generator instead of live Finnhub data. Useful for previewing the widget, `render-demo` GIFs, or a sign that doesn't have a Finnhub token yet. See [`docs/demo.toml`](docs/demo.toml) for a runnable example.

Demo mode moves the price every step, so the price-flash animation fires continuously (a real Finnhub feed only flashes when a poll observes an actual price change) — it's a good way to preview the flash without waiting for a live tick.

**Demo is a process-wide setting, not a per-widget one.** Every `stocks.ticker` widget and `stocks.quote` [inline token](#inline-price-tokens) in the same process shares one `QuoteCache` (see [Rate limits](#rate-limits--api-token)), and that cache is single-mode: the FIRST consumer to actually start it (widget `start()` or a token's first `update()` tick) decides live vs. demo for *everything* reading it that session. `demo = true` on one widget forces the whole cache into demo — but only if that widget wins the race to start it first; a config that mixes a `demo = true` widget with a plain live widget/token resolves to whichever one starts first, which isn't something the config file controls. In practice this rarely matters: no `FINNHUB_API_TOKEN` in the environment already routes everyone to demo regardless of start order, so `demo = true` is mostly useful for forcing demo output even when a real token IS configured (e.g. a `render-demo` GIF run against a sign that also has a live token in `.env`).

### Smoke-test configs (per sign)

Ready-to-run hardware smoke configs live in [`examples/`](examples/), one per sign form factor — each with a token-free demo section plus a live section, and a "what to look for" header:

| File | Sign | Notes |
|---|---|---|
| [`config.stocks-smoke.smallsign.toml`](examples/config.stocks-smoke.smallsign.toml) | 160×16 | `crawl` auto-selected, `mode = "ticker"` |
| [`config.stocks-smoke.bigsign.toml`](examples/config.stocks-smoke.bigsign.toml) | 256×64 | `card` auto-selected, `mode = "slideshow"` |
| [`config.stocks-smoke.longboi.toml`](examples/config.stocks-smoke.longboi.toml) | 512×64 | `dashboard` auto-selected, `mode = "slideshow"` (widget alone in its section — see [Layouts](#layouts)) |

Copy one to `config/config.toml` on the sign, `led-ticker validate` it, then `make restart`.

### Rate limits & API token

Get a free API token at [finnhub.io/register](https://finnhub.io/register) and supply it via the `FINNHUB_API_TOKEN` environment variable — **never** put it in `config.toml`; secrets are env-only in led-ticker (see the [Plugins docs](https://docs.ledticker.dev/plugins/)):

```bash
export FINNHUB_API_TOKEN="your-token-here"
```

Finnhub's free tier allows **60 requests per minute, per API key** — not per widget. All `stocks.ticker` widgets and `stocks.quote` [inline tokens](#inline-price-tokens) in one process share a single poll loop and a single deduplicated symbol set (registering `"AAPL"` from three different widgets/tokens still costs one `AAPL` fetch per cycle, not three — see the field's own [Inline price tokens](#inline-price-tokens) section). Every poll cycle costs `len(symbols) + 1` requests, where `symbols` is the UNION of every symbol registered process-wide (one market-status call plus one quote call per distinct symbol). While the market is **closed**, a symbol is fetched only until it holds a price — Finnhub returns the last close even when the exchange is shut, so a sign booted after hours still shows the close (and inline tokens still resolve); once warm, closed cycles freeze it and cost just the one market-status call. The cadence self-widens to `max(update_interval, len(symbols) + 1)`, recomputed every cycle so it reacts to late registrants (a token added after boot, a second widget in another section) — so a single sign's stocks usage on its own can't blow the budget. The `update_interval` floor itself is set by whichever consumer starts the cache first: `ensure_started` is a no-op after the first call, so in a mixed config a widget's `update_interval` and a token's `interval` don't average — the first one to boot wins, and the loser's value is ignored (same first-started-wins rule as demo mode). Give overlapping consumers the same interval if you care which one applies. The 60/min ceiling is still shared across **everything** using that token, though: two signs pointed at the same Finnhub key, or another Finnhub-backed widget/script on the same key, split the same 60 requests. Give each sign (or each concurrent consumer) its own free Finnhub account/token if you're running more than one.

### Finnhub is equities-only (use Twelve Data for FX/crypto)

Finnhub's free tier returns HTTP 403 on forex (`/forex/*`) endpoints, and this plugin's Finnhub path only implements the equities `/quote` + `/stock/market-status` endpoints — FX and crypto pairs aren't supported under `provider = "finnhub"` (the default). For forex or crypto symbols, set `provider = "twelvedata"` instead — see [Multi-asset via Twelve Data](#multi-asset-via-twelve-data). `validate_config` rejects any symbol containing `/` (the conventional FX pair separator, e.g. `"EUR/USD"`) under the Finnhub provider at config-load time with a message pointing at `provider = "twelvedata"`, rather than letting it fail opaquely at runtime.

### `layout` override

All three layouts (`"crawl"`, `"card"`, `"dashboard"`) are registered — `layout =` selects among them explicitly. Omit the field and `resolve_layout` picks by real panel width (see [Layouts](#layouts)): ≤160px → `crawl`, ~160–400px → `card`, ≥400px → `dashboard`. An unrecognized `layout` value fails config validation naming the registered set.

## Inline price tokens

Besides the `stocks.ticker` **widget**, this plugin registers a `stocks.quote` **source** — a live price value you embed in any *other* widget's text with a `:id:` token (led-ticker's [value tokens](https://docs.ledticker.dev/concepts/value-tokens/) mechanism, requires led-ticker-core `>= 4.9`). Declare it as a `[[source]]` block, give it an `id`, and reference `:id:` anywhere text is drawn:

```toml
[[source]]
id = "stocks.aapl"
type = "stocks.quote"
symbol = "AAPL"
format = "{price}"          # optional; this is the default
# placeholder = "…"         # optional; shown until the first fetch

[[playlist.section.widget]]
type = "message"
text = "AAPL :stocks.aapl:"   # -> "AAPL 317.31", updating live
```

### Fields

`format` is a plain [`str.format`](https://docs.python.org/3/library/string.html#format-string-syntax) string over these named fields — reference only the ones you need, the rest are never computed (lazy, weather-style):

| Field | Example | Description |
|---|---|---|
| `price` | `317.31` | Last price, decimal-formatted. |
| `change` | `+1.99` | Signed absolute change vs. previous close. |
| `pct` | `+0.63%` | Signed percent change vs. previous close. |
| `arrow` | `▲` | `▲` up / `▼` down / `·` flat — plain text, not colored (see the caveat below). |
| `symbol` | `AAPL` | The configured ticker symbol. |
| `prev` | `315.32` | Previous close. |
| `high` | `320.00` | Session high (em dash `—` if not yet known). |
| `low` | `310.50` | Session low (em dash `—` if not yet known). |
| `day_range` | `310.50–320.00` | `{low}–{high}` combined. |

A symbol containing `/` (e.g. `"EUR/USD"`) fails validation under `provider = "finnhub"` (the default) — same FX restriction as the widget, see [Finnhub is equities-only](#finnhub-is-equities-only-use-twelve-data-for-fxcrypto). Use `provider = "twelvedata"` on the source for forex/crypto — see [Multi-asset via Twelve Data](#multi-asset-via-twelve-data).

### Token color is inherited, not per-token

A price token renders as part of the HOST widget's text — it takes whatever `font_color` (or per-char provider, e.g. `rainbow`) that widget already has. Unlike the `stocks.ticker` **widget**, which independently colors its change line green/red per `green_up`, a `▲`/`▼` produced by `{arrow}` inside a token **cannot** be independently colored green or red — it's just another character in the string. If you need the widget's colored up/down semantics, use `stocks.ticker` directly; use the token when you want a compact price reference woven into other text (a headline, a two-row detail line, a clock/date composite) and don't need per-direction coloring.

### Shared cache, one poll loop

Every `stocks.quote` token and every `stocks.ticker` widget in the same process reads the SAME `QuoteCache` — see [Rate limits](#rate-limits--api-token). Registering `AAPL` via a token and via a widget (or via three separate tokens) still only fetches `AAPL` **once** per poll cycle; the cache dedups by symbol, not by consumer. A token-only config (no `stocks.ticker` widget anywhere) still works — the first `:id:` token to draw self-starts the shared poll loop.

### Demo behavior

With no `FINNHUB_API_TOKEN` set (or `demo = true` on any `stocks.ticker` widget sharing the process — see [Demo mode](#demo-mode-no-token-required) for the first-started-wins nuance), tokens show a moving, synthesized price instead of the `…` placeholder — useful for previewing a token-driven config or a `render-demo` GIF with no Finnhub account at all. [`examples/config.stocks-token.smallsign.toml`](examples/config.stocks-token.smallsign.toml) is a ready-to-run, token-free example.

## Trend color

Besides the `stocks.ticker` widget and the `stocks.quote` source, this plugin registers a `stocks.trend` **color provider** — set it as `font_color` on any text widget to tint the text green/red/neutral by a symbol's day change, without switching to the `stocks.ticker` widget:

```toml
[[playlist.section.widget]]
type = "message"
text = "AAPL :stocks.aapl:"
font_color = {style = "stocks.trend", symbol = "AAPL"}
```

This tints the **whole message** — it's a whole-string provider (like `color_cycle`), not a per-character one (like `rainbow`): the entire string turns green when the symbol's day change is positive, red when negative, and neutral gray when flat or before the first quote lands. There's no way to color just the price segment of a token differently from the surrounding label text (that's deferred future work, tracked separately from this plugin). Pairing it with an [inline price token](#inline-price-tokens), as in the example above, gives a compact "SYM price" line that tints by direction; it also works on any other text widget's `font_color`.

### Fields

| Option | Type | Default | Description |
|---|---|---|---|
| `symbol` | string | — | **Required.** The ticker symbol to track (e.g. `"AAPL"`). Same FX restriction as the widget/source — a symbol containing `/` fails validation. |
| `up` | `[r, g, b]` | `[60, 220, 60]` (green) | Color when the symbol's day change is positive. |
| `down` | `[r, g, b]` | `[255, 60, 60]` (red) | Color when the symbol's day change is negative. |
| `flat` | `[r, g, b]` | `[150, 150, 150]` (neutral gray) | Color when the change is exactly zero, or when no quote has landed for the symbol yet. |
| `green_up` | bool | `true` | Set `false` to swap `up`/`down` (same convention as the widget's own `green_up`). |

### Feeding requirement

`stocks.trend` **reads** the shared `QuoteCache`; it does not start it. The symbol must be fed by a `stocks.quote` [source](#inline-price-tokens) or a `stocks.ticker` widget somewhere in the same config — something has to actually start the cache's poll loop and register a real quote for the symbol. The natural pairing above already has a feeder: the `[[source]]` block behind `:stocks.aapl:` is what starts the cache. If nothing in the config feeds the symbol, the cache never starts and the widget renders the `flat` color forever — not an error, just a steady neutral gray.

See [`examples/config.stocks-trend.smallsign.toml`](examples/config.stocks-trend.smallsign.toml) for a ready-to-run, token-free demo.

## Multi-asset via Twelve Data

Finnhub (the default) is US equities only — set `provider = "twelvedata"` on `stocks.ticker` **or** `stocks.quote` to poll [Twelve Data](https://twelvedata.com/) instead, which additionally covers forex and crypto:

```toml
[[playlist.section.widget]]
type = "stocks.ticker"
provider = "twelvedata"
symbols = ["AAPL", "EUR/USD", "BTC/USD"]
```

- **Provider is effectively process-global, not per-widget.** `provider` is a field on both `stocks.ticker` and `stocks.quote`, but every widget/source shares one `QuoteCache`, and `ensure_started` resolves ONE `_provider` on the first call — the first widget/source to start the shared cache picks the provider for every symbol in the process (same first-started-wins caveat as `demo`/`interval`, see [Rate limits & API token](#rate-limits--api-token)). A Finnhub widget and a Twelve Data source in the same config route the TD symbol through whichever provider wins the start race, which means Finnhub → 403 on forex/crypto if Finnhub starts first. Use ONE provider across all `stocks.*` blocks in a given config; each provider still needs its own token in the environment (see below).
- **Symbol formats route the asset class, no exchange prefix:** a bare ticker (`"AAPL"`) is a stock, a slash-separated pair (`"EUR/USD"`) is forex, and a slash-separated pair against a fiat/stable (`"BTC/USD"`) is crypto. Twelve Data infers the asset class from the symbol shape alone.
- **Finnhub stays the default** and remains equities-only — a `/` in a symbol under `provider = "finnhub"` (or the field omitted) fails validation pointing at `provider = "twelvedata"`, same as today. Forex and crypto symbols always require the Twelve Data provider.
- **Get a free key** at [twelvedata.com/pricing](https://twelvedata.com/pricing) and put it in `.env` as `TWELVEDATA_API_KEY` — **never** in `config.toml` (same env-only convention as `FINNHUB_API_TOKEN`; see [Rate limits & API token](#rate-limits--api-token)).
- **Data is delayed** ~1–15 minutes on the free tier. That's fine at sign cadence — nobody is day-trading off an LED panel — but don't expect tick-by-tick accuracy.
- **Auto-formatting needs no config:** prices pick their decimal places from magnitude — forex pairs (~1.15) render at 4 decimals, equities and larger crypto values render at 2 decimals with thousands separators (`65,432.10`). `decimals` on `stocks.quote` still overrides this per source if you want something else.
- **Credit budget:** the free tier is ~800 credits/day (1 credit per symbol per poll). Unlike the Finnhub path, Twelve Data symbols are **not** frozen while their market is closed — each polls every cycle — so pick `update_interval` (widget) / `interval` (source) to stay in budget: roughly `interval ≥ 108 × symbol_count` seconds keeps you under 800/day. Example: 3 symbols → `interval = 360` (720/day).

See [`examples/config.stocks-multiasset.bigsign.toml`](examples/config.stocks-multiasset.bigsign.toml) for a ready-to-run bigsign example: a `card` layout cycling a stock/forex/crypto trio plus a mixed-color inline `:eurusd:` token in its own section.

## Roadmap

Shipped so far: `crawl` (v0.1.0), `card`/`dashboard` (v0.2.0), the price-flash/pulse animation layer (v0.3.0), the `stocks.quote` inline price token + shared `QuoteCache` (v0.4.0), the `stocks.trend` color provider (v0.5.0), and [multi-asset Twelve Data support](#multi-asset-via-twelve-data) — forex + crypto via `provider = "twelvedata"` (v0.6.0). Deferred / out of scope: **per-token color** (coloring just the price segment within a mixed-color message — a core-side value-token change), stock indices, sparkline/history in a token, a change-field flash on tokens, new layouts or widgets, and `font_color`/`border`/rainbow-gradient styling knobs on the three canonical widget layouts.

- **Release:** docs-site page, catalog `provides` entry, demo GIFs, `stocks-v0.5.0` release.

## Development

Install dev deps and run the checks:

```bash
uv sync --extra dev      # resolves led-ticker-core from PyPI
uv run pytest -q
uv run ruff check src tests
```

> **Note:** tests that need a headless canvas obtain one via `HeadlessBackend(...).create_canvas()` from `led_ticker.plugin` — the software backend shipped in led-ticker-core. No rgbmatrix test stub or `PYTHONPATH` plumbing is required.

The plugin imports only the public `led_ticker.plugin` surface — `tests/test_import_purity.py` enforces it.

## Links

- [led-ticker](https://github.com/JamesAwesome/led-ticker) — the core project
- [Docs site](https://docs.ledticker.dev) · [Plugin system](https://docs.ledticker.dev/plugins/)
