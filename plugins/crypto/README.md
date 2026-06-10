# led-ticker-crypto

A cryptocurrency price ticker **widget** for [led-ticker](https://github.com/JamesAwesome/led-ticker), backed by the free CoinGecko v3 API — no API key required. It's a led-ticker **plugin** — installing this package contributes a `crypto.coingecko` widget you reference in your led-ticker config.

It displays the coin symbol, current price (formatted to 4 decimal places), and 24-hour percent change in a single scrolling line. The change value is trend-colored: green for positive, red for negative, gray for neutral — readable at a glance on any panel.

## Prerequisites

- A working [led-ticker](https://github.com/JamesAwesome/led-ticker) install.
- Internet access on the Pi (the widget calls the CoinGecko public API; no API key needed).

## Install

The widget auto-registers via the `led_ticker.plugins` entry point — once the package is installed, no `[plugins]` config change is needed.

**Into a containerized led-ticker (recommended):** add this package to `config/requirements-plugins.txt` (copy it from `config/requirements-plugins.example.txt`, which already lists it), then rebuild:

```bash
# in your led-ticker checkout
cp config/requirements-plugins.example.txt config/requirements-plugins.txt
docker compose up -d --build
```

That example file lists every first-party plugin — trim the live copy to just the ones you want. The crypto line is:

```text
git+https://github.com/JamesAwesome/led-ticker-crypto.git@main
```

**Standalone (a venv that already has led-ticker):**

```bash
pip install "git+https://github.com/JamesAwesome/led-ticker-crypto.git@main"
```

led-ticker isn't on PyPI, so this path only works where led-ticker is already installed. See the led-ticker [Plugins docs](https://docs.ledticker.dev/plugins/) for the constraint-based install the Docker image uses.

## Configuration

Reference the widget in a playlist section by `type = "crypto.coingecko"`:

```toml
[[playlist.section.widget]]
type = "crypto.coingecko"
symbol = "BTC"
symbol_id = "bitcoin"
currency = "USD"
```

New to led-ticker configs? The [first-config tutorial](https://docs.ledticker.dev/tutorial/02-first-config/) walks through the overall structure — the block above shows just the crypto-specific keys.

### Finding `symbol_id`

`symbol_id` is CoinGecko's internal coin identifier — it's the `id` field in CoinGecko's `/coins/list` endpoint (e.g. `"bitcoin"`, `"ethereum"`, `"solana"`, `"dogecoin"`). The `symbol` field (e.g. `"BTC"`) is only used for the on-panel label; `symbol_id` is what the API actually queries. If you're unsure of the id, browse [coingecko.com](https://www.coingecko.com) — the coin's page URL contains the id (`coingecko.com/en/coins/<id>`).

### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `symbol` | string | required | Ticker label shown on the panel (e.g. `"BTC"`, `"ETH"`). |
| `symbol_id` | string | required | CoinGecko coin id (e.g. `"bitcoin"`, `"ethereum"`). This is how the API identifies the coin. |
| `currency` | string | required | Fiat currency code (e.g. `"USD"`, `"EUR"`). |
| `center` | bool | `true` | Center the ticker on the canvas when it fits; scroll when it overflows. |
| `padding` | int | `6` | Horizontal spacing (logical px) between the symbol, price, and change segments. |
| `hold_time` | float | `0.0` | Seconds to hold the widget before transitioning. |
| `bg_color` | `[r,g,b]` | none | Background fill behind the ticker. |
| `font_color` | `[r,g,b]` / string / table | yellow `(255,255,0)` | Color for the symbol and price. Accepts any led-ticker color provider (e.g. `"rainbow"`, `{style="shimmer", ...}`). The 24h change color is always trend-colored and ignores this field. |
| `update_interval` | int | `300` | Seconds between CoinGecko fetches (5 min default). |

## Development

led-ticker isn't on PyPI, so this plugin resolves it from a sibling checkout. Clone both side by side:

```
~/projects/.../led-ticker
~/projects/.../led-ticker-crypto
```

```bash
uv sync --extra dev      # resolves led-ticker from ../led-ticker
uv run pytest -q
uv run ruff check src tests
```

> **Note:** led-ticker's `graphics` surface works headless via its bundled stub, but the full `RGBMatrix`/canvas test stub lives in led-ticker's `tests/stubs/` and isn't shipped. This repo's tests put it on the path via `pyproject.toml`'s `[tool.pytest.ini_options] pythonpath = ["../led-ticker/tests/stubs"]`.

The plugin imports only the public `led_ticker.plugin` surface — `tests/test_import_purity.py` enforces it. `tools/compare_render.py` verifies the renderer is pixel-identical to the original coinbase renderer that was ported from led-ticker core.

## Links

- [led-ticker](https://github.com/JamesAwesome/led-ticker) — the core project
- [Docs site](https://docs.ledticker.dev) · [Plugin system](https://docs.ledticker.dev/plugins/)
