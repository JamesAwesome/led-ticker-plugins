# led-ticker-stocks

A stock / equities ticker **plugin** for [led-ticker](https://github.com/JamesAwesome/led-ticker), backed by the [Finnhub](https://finnhub.io/) API. It contributes a `stocks.ticker` **Container widget** that cycles one scrolling price line per configured symbol: `SYM  price  ▲/▼ change change%`, trend-colored green/red and dimmed by market state (full brightness while the market is open, dimmed while pre/post-market, dimmest while closed).

**Phase 1 scope:** US equities only, one layout (`crawl`, sized for the smallsign). FX/forex, the bigsign `card` layout, and the longboi `dashboard` layout are not implemented yet — see [Roadmap](#roadmap).

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

See the led-ticker [Plugins docs](https://docs.ledticker.dev/plugins/) for the constraint-based install the Docker image uses, and pin production signs to an exact version (`led-ticker-stocks==0.1.0`) so a restart doesn't silently pick up a new release.

## Configuration

Reference the widget in a playlist section by `type = "stocks.ticker"`:

```toml
[[playlist.section]]
mode = "ticker"

[[playlist.section.widget]]
type = "stocks.ticker"
symbols = ["AAPL", "MSFT", "NVDA", "TSLA"]
```

`mode = "ticker"` (continuous side-by-side crawl) is the **recommended** section mode for this widget — the crawl layout is a single scrolling line per symbol, the same shape as the built-in `crypto.coingecko` / `rss.feed` tickers. `slideshow` also works (one symbol held per visit) but the crawl text is designed to keep moving.

New to led-ticker configs? The [first-config tutorial](https://docs.ledticker.dev/tutorial/02-first-config/) walks through the overall structure — the block above shows just the stocks-specific keys.

### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `symbols` | list of strings | — | **Required.** Ticker symbols (e.g. `["AAPL", "MSFT"]`). US equities only — a symbol containing `/` (e.g. `"EUR/USD"`) fails validation with a message pointing at the FX limitation below. |
| `layout` | string | auto | Force a specific render layout. Phase 1 registers only `"crawl"` — omit this field and let the widget auto-select (it currently always resolves to `crawl` on a ≤160px-wide canvas and raises `NotImplementedError` on anything wider, since `card`/`dashboard` aren't shipped yet). |
| `demo` | bool | `false` | Run against a seeded, offline random-walk feed instead of Finnhub — no token, no network call. See [Demo mode](#demo-mode-no-token-required). |
| `update_interval` | int | `60` | Seconds between Finnhub polls. The widget silently raises this to `len(symbols) + 1` if you set it lower — see [Rate limits](#rate-limits--api-token) below. |
| `padding` | int | `6` | Horizontal spacing (logical px) after each symbol's segment, before the next symbol. |
| `green_up` | bool | `true` | Set `false` to flip the up/down colors (green-down/red-up) for non-US market conventions. |

At least `symbols` must be a non-empty list — the widget fails at config validation otherwise (`led-ticker validate` catches this before boot).

### Demo mode (no token required)

Set `demo = true` (or simply omit `FINNHUB_API_TOKEN` from the environment — an unset token silently routes to the same demo feed, it is not an error) to drive the widget from a deterministic, seeded random-walk price generator instead of live Finnhub data. Useful for previewing the widget, `render-demo` GIFs, or a sign that doesn't have a Finnhub token yet. See [`docs/demo.toml`](docs/demo.toml) for a runnable example.

### Smoke-test configs (per sign)

Ready-to-run hardware smoke configs live in [`examples/`](examples/), one per sign form factor — each with a token-free demo section plus a live section, and a "what to look for" header:

| File | Sign | Notes |
|---|---|---|
| [`config.stocks-smoke.smallsign.toml`](examples/config.stocks-smoke.smallsign.toml) | 160×16 | crawl auto-selected (native Phase-1 target) |
| [`config.stocks-smoke.bigsign.toml`](examples/config.stocks-smoke.bigsign.toml) | 256×64 | `layout = "crawl"` forced (card is Phase 2) |
| [`config.stocks-smoke.longboi.toml`](examples/config.stocks-smoke.longboi.toml) | 512×64 | `layout = "crawl"` forced (dashboard is Phase 2) |

Copy one to `config/config.toml` on the sign, `led-ticker validate` it, then `make restart`.

### Rate limits & API token

Get a free API token at [finnhub.io/register](https://finnhub.io/register) and supply it via the `FINNHUB_API_TOKEN` environment variable — **never** put it in `config.toml`; secrets are env-only in led-ticker (see the [Plugins docs](https://docs.ledticker.dev/plugins/)):

```bash
export FINNHUB_API_TOKEN="your-token-here"
```

Finnhub's free tier allows **60 requests per minute, per API key** — not per widget. Every poll cycle costs `len(symbols) + 1` requests (one market-status call plus one quote call per symbol; the widget skips the quote calls entirely while the market is closed, holding last prices instead). The widget enforces `effective_interval = max(update_interval, len(symbols) + 1)` automatically, so a single `stocks.ticker` on its own can't blow the budget — but the 60/min ceiling is shared across **everything** using that token: two signs pointed at the same Finnhub key, or another Finnhub-backed widget/script on the same key, split the same 60 requests. Give each sign (or each concurrent consumer) its own free Finnhub account/token if you're running more than one.

### Equities only — FX requires a paid tier

Finnhub's free tier returns HTTP 403 on forex (`/forex/*`) endpoints. This plugin's v1 only implements the equities `/quote` + `/stock/market-status` endpoints — FX pairs are out of scope until a paid-tier client ships (not planned for Phase 1/2). `validate_config` rejects any symbol containing `/` (the conventional FX pair separator, e.g. `"EUR/USD"`) at config-load time with a message explaining why, rather than letting it fail opaquely at runtime.

### `layout` override

Phase 1 ships exactly one registered layout, `"crawl"` (built for the smallsign, 160px-wide canvas). `resolve_layout` auto-selects `crawl` whenever the canvas is ≤160px wide; on a wider canvas (bigsign/longboi) it raises `NotImplementedError` naming the missing `card`/`dashboard` layouts rather than silently rendering wrong. Setting `layout = "crawl"` explicitly is accepted but has no effect beyond skipping the geometry check — there's nothing else to choose from yet.

## Roadmap

- **Phase 2:** `card` (bigsign) + `dashboard` (longboi) hi-res layouts; sparkline + day-range rendering; paging dots; watch column; geometry auto-select across scale-4 widths.
- **Phase 3:** price-flash on update, sparkline/state pulses, global state dim on the held layouts, abstract per-symbol brand chips, `font_color`/`border` styling knobs.
- **Phase 4:** docs-site page, catalog `provides` entry, demo GIFs, `stocks-v0.1.0` release.

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
