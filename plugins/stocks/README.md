# led-ticker-stocks

A stock / equities ticker **plugin** for [led-ticker](https://github.com/JamesAwesome/led-ticker), backed by the [Finnhub](https://finnhub.io/) API. It contributes a `stocks.ticker` **Container widget** that cycles one price view per configured symbol, trend-colored green/red and dimmed by market state (full brightness while the market is open, dimmed while pre/post-market, dimmest while closed). Three layouts are registered and auto-selected by panel geometry — see [Layouts](#layouts):

- `crawl` (smallsign, ~160px) — a single scrolling line: `SYM  price  ▲/▼ change change%`.
- `card` (bigsign, ~256px) — a held hero card: symbol + price + change, a brand chip, a sparkline, a state-chip label, and paging dots.
- `dashboard` (longboi, ~512px) — a held trading dashboard: the same hero block plus a watch column showing the next symbols and a bigger sparkline.

All three layouts animate: the price line pops white on a change and settles back to amber (Bloomberg-style flash), the LIVE state chip breathes while the market is open, and the sparkline's tip pulses. **Scope:** US equities only. FX/forex is out of scope — see [Equities only](#equities-only--fx-requires-a-paid-tier).

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

Set `demo = true` (or simply omit `FINNHUB_API_TOKEN` from the environment — an unset token silently routes to the same demo feed, it is not an error) to drive the widget from a deterministic, seeded random-walk price generator instead of live Finnhub data. Useful for previewing the widget, `render-demo` GIFs, or a sign that doesn't have a Finnhub token yet. See [`docs/demo.toml`](docs/demo.toml) for a runnable example.

Demo mode moves the price every step, so the price-flash animation fires continuously (a real Finnhub feed only flashes when a poll observes an actual price change) — it's a good way to preview the flash without waiting for a live tick.

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

Finnhub's free tier allows **60 requests per minute, per API key** — not per widget. Every poll cycle costs `len(symbols) + 1` requests (one market-status call plus one quote call per symbol; the widget skips the quote calls entirely while the market is closed, holding last prices instead). The widget enforces `effective_interval = max(update_interval, len(symbols) + 1)` automatically, so a single `stocks.ticker` on its own can't blow the budget — but the 60/min ceiling is shared across **everything** using that token: two signs pointed at the same Finnhub key, or another Finnhub-backed widget/script on the same key, split the same 60 requests. Give each sign (or each concurrent consumer) its own free Finnhub account/token if you're running more than one.

### Equities only — FX requires a paid tier

Finnhub's free tier returns HTTP 403 on forex (`/forex/*`) endpoints. This plugin only implements the equities `/quote` + `/stock/market-status` endpoints — FX pairs are out of scope until a paid-tier client ships (not on the current roadmap). `validate_config` rejects any symbol containing `/` (the conventional FX pair separator, e.g. `"EUR/USD"`) at config-load time with a message explaining why, rather than letting it fail opaquely at runtime.

### `layout` override

All three layouts (`"crawl"`, `"card"`, `"dashboard"`) are registered — `layout =` selects among them explicitly. Omit the field and `resolve_layout` picks by real panel width (see [Layouts](#layouts)): ≤160px → `crawl`, ~160–400px → `card`, ≥400px → `dashboard`. An unrecognized `layout` value fails config validation naming the registered set.

## Roadmap

Phase 3 (price-flash on update, sparkline/state-chip pulses) is shipping as `stocks-v0.3.0` — this is now the final planned phase for the three canonical layouts (the `crawl` layout shipped in v0.1.0, `card`/`dashboard` in v0.2.0). Deferred / out of scope: new layouts or widgets, indices/FX, a change-field flash, and `font_color`/`border`/rainbow-gradient styling knobs on these layouts.

- **Release:** docs-site page, catalog `provides` entry, demo GIFs, `stocks-v0.3.0` release.

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
