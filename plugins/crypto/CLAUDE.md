# CLAUDE.md

Guidance for Claude Code when working in **led-ticker-crypto**, an external plugin for
[led-ticker](https://github.com/JamesAwesome/led-ticker).

`README.md` is the source of truth for the user-facing surface (config options, install,
coin-spec styles, rate limits). This file keeps the **load-bearing invariants** a contributor
must respect, plus navigation aids. When a fact here and the README disagree about *how a
feature works*, the README wins; this file is the source of truth for *how to keep it working*.

## Overview

This plugin contributes, via the `led_ticker.plugins` entry point, a single widget:

- `crypto.coingecko` — live crypto price Container from the CoinGecko v3 API. Cycles one
  `_CoinTicker` "story" per configured coin (the engine reads `feed_stories` via
  `_expand_sources` on every pass). Shows symbol + price (adaptive precision) + 24h change,
  trend-colored green/red/gray. One batched `/simple/price` fetch per update interval.

The entry-point name `crypto` is the plugin namespace, so the config `type` is
`crypto.coingecko` (see `register()` in `__init__.py`).

## Commands

led-ticker is **not on PyPI**; it resolves from a sibling checkout via
`[tool.uv.sources] led-ticker = { path = "../led-ticker", editable = true }`. CI checks out
`led-ticker` next to this repo using a read-only deploy key (`LED_TICKER_DEPLOY_KEY`). The
sibling checkout matters at test time too: `pyproject.toml` puts `../led-ticker/tests/stubs`
on the pytest path so the rgbmatrix stub is importable headless.

```bash
uv sync --extra dev          # install deps (needs ../led-ticker checked out)
uv run pytest -q             # full suite (asyncio_mode = "auto")
uv run ruff check src tests  # lint — run before pushing
```

Python **3.14+** only.

## Package layout

```
src/led_ticker_crypto/
  __init__.py         # register(api) → api.widget("coingecko")(CoinGeckoMonitor)
  coingecko.py        # CoinGeckoMonitor (Container): start(), update(), _build_coins,
                      #   _resolve_symbols; _CoinTicker: per-coin story with draw()
  _ticker_render.py   # draw_price_ticker(): shared price-ticker renderer ported from core's
                      #   coinbase widget; _format_price(); _ConstantColor; make_default_font_color
  _colors.py          # UP_TREND_COLOR / DOWN_TREND_COLOR / NEUTRAL_TREND_COLOR via lazy_palette
```

`register(api)` (in `__init__.py`):

```python
def register(api):
    api.widget("coingecko")(CoinGeckoMonitor)
```

## Load-bearing invariants

Each rule must hold when modifying the named files.

**Import only the public surface** — every `led_ticker` import MUST come from `led_ticker.plugin`,
never `led_ticker.<internal>`. Enforced by `tests/test_import_purity.py`, which AST-walks every
source file (catches `from`-imports *and* `import led_ticker.x` forms, not just a text grep).
Intra-package imports (`from led_ticker_crypto._colors import …`) are fine. If you need a core
symbol that isn't on `led_ticker.plugin.__all__`, that's a core API change — raise it upstream,
don't reach around the surface.

**Python 3.14 / PEP 649** — no `from __future__ import annotations` anywhere (same rule as core).
Bare `tuple[int, int, int]` annotations are fine.

**`CoinGeckoMonitor` is a Container** — it exposes `feed_stories: list[_CoinTicker]` (one story
per coin). The engine reads `feed_stories` via `_expand_sources` on every pass through the
section, so live updates surface within at most one cycle. A single-coin config produces a
one-story container — the same code path, no special case. Never snapshot `feed_stories` into a
cycle iterator at section build time; that was the longboi stale-display pattern.

**`update()` uses ONE batched fetch with comma-joined ids** — multiple coin ids MUST be joined
into a single `ids` string (`ids=bitcoin,ethereum,dogecoin`). Passing a Python list would make
aiohttp emit repeated `ids=bitcoin&ids=ethereum` query parameters, which CoinGecko rejects for
more than one id. The comment in `update()` documents this constraint explicitly; do not change
the join to a list.

**Non-200 responses raise** — `update()` logs a warning (including `retry-after` if present),
then calls `response.raise_for_status()` so `run_monitor_loop`'s exponential backoff engages.
A 429 or any error body must NEVER be parsed as price data. This handles the CoinGecko free-tier
rate limit (~5 calls/min keyless) and any transient API error.

**`_format_price` adaptive precision** — coins ≥ $1 (or exactly $0) use the historical
`f"{value:,.4f}"` form (4 decimals, thousands-separated). Sub-dollar coins get extra decimals
computed as `min(12, max(4, 3 - floor(log10(abs(value)))))` so a coin at ~$0.0000046 renders
as `0.0000046` rather than collapsing to `0.0000`. Do not revert this to a fixed `.4f` format.

**`symbols` auto-lookup is unique-or-error** — `_resolve_symbols` queries the full
`/coins/list` response. For each requested symbol: exactly one match → `(symbol.upper(), id)`;
zero matches → `ValueError`; multiple matches → `ValueError` listing all candidate ids and
telling the user to set `symbol_id`/`symbol_ids` to disambiguate. Input order is preserved.
The `/coins/list` fetch only happens when `symbols` is non-empty; `symbol_ids`-only configs
skip it entirely.

**`_build_coins` assembles and deduplicates** — order is: legacy `symbol`+`symbol_id` → each
entry in `symbol_ids` → `symbols` (auto-resolved). Deduplication is by coin_id, keeping first
occurrence. Raises if the result is empty (the same message as `validate_config`).

**Optional `x-cg-demo-api-key` header** — `api_key` is sourced from the TOML field first, then
falls back to the `COINGECKO_API_KEY` environment variable (`os.getenv`). When non-empty, the
key is sent as `x-cg-demo-api-key` in all CoinGecko requests (both the `/coins/list` startup
fetch and the per-update `/simple/price` fetch). When empty, no key header is sent. No key is
required for a single low-frequency widget.

**`font_color` plumbing in `coingecko.py`** — `_CoinTicker.__attrs_post_init__` normalises the
raw config value: `None` → `make_default_font_color()` (yellow `_ConstantColor`); a plain
`Color` (not a `ColorProvider`) → `_ConstantColor(color)`. After `__attrs_post_init__`,
`self.font_color` is always a `ColorProvider`. `draw()` passes `frame_for("font_color")` so
animated providers (rainbow, shimmer) animate across engine ticks. The 24h change segment uses
`_get_change_color` and ignores `font_color`; this is intentional — change is always
trend-colored.

**One INFO log per successful `update()`** — the Container contract: a silent log stream after
startup signals the background task died. `update()` emits one INFO line per call showing
updated/total counts and the coin ids — never the raw API response.

**`start()` accepts `update_interval`** — this parameter is consumed by `start()` before the
`attrs` constructor, so it does NOT appear in `attrs.fields(cls)` and is filtered out of the
`**kwargs` forwarding. Any future parameter that belongs to the monitor lifecycle (not the
widget state) should follow the same pattern: accept in `start()`, don't pass through to
`cls(...)`.

**This is a faithful port of core's CoinGecko renderer** — `_ticker_render.draw_price_ticker`
was ported from `led_ticker.widgets.crypto.coinbase._draw_price_ticker` (coinbase was removed
from core; the renderer traveled with this plugin). Pixel-identity to the original was proven
during extraction (see PR history); `tools/compare_render.py` served that one-time validation
purpose and was retired after core's renderer was removed in led-ticker#188. Do not change
rendering logic in `_ticker_render.py` without confirming the diff is intentional.

**Port adaptations in `_ticker_render.py`** — these are deliberate, documented deviations from
how the original code was written that must NOT be reverted:

- `draw_text` is called in the public absolute-return form:
  `cursor_pos = draw_text(canvas, font, text, x, y, color)` — not the core-internal
  `cursor_pos += draw_text(...)` form. The result is pixel-identical for plain text.
- `compute_cursor`'s `center` parameter is keyword-only at the call site.
- The default `font_color` is yellow `(255, 255, 0)`, matching core's `DEFAULT_COLOR`.
- `_ConstantColor` is a local reproduction of core's private class (which is not on the public
  surface). It wraps a plain `Color` so a `font_color = [r,g,b]` config routes through the same
  `color_for` interface as effect providers.

**Font constants** — `FONT_LABEL` (`7x13`) and `FONT_DELTA` (`6x10`) are resolved once at import
via `resolve_font`. `FONT_VALUE` and `FONT_VALUE_SMALL` alias `FONT_DEFAULT` / `FONT_SMALL` from
`led_ticker.plugin` — these are BDF faces (`6x12` / `5x8`). The price font auto-downgrades to
`FONT_VALUE_SMALL` when the price string exceeds 10 characters (long decimals and large values).

**Trend palette is lazy** — `_colors.py` uses `colors.lazy_palette` (PEP 562 `__getattr__`),
so importing the module is a no-op against the rgbmatrix `graphics` library. In-module code
(e.g. inside `_ticker_render.py`) accesses them as module-level names
(`UP_TREND_COLOR`, `DOWN_TREND_COLOR`, `NEUTRAL_TREND_COLOR`), which triggers the lazy resolver
on first access. Do not call `_trend_palette(name)` directly from outside `_colors.py`.

## Tests / CI

`uv run pytest -q` runs the suite (`tests/`):

- `test_import_purity.py` — AST tripwire (public-surface-only). Treat a failure as a contract
  violation, not a test to relax.
- `test_smoke.py` — loads the plugin through led-ticker's real plugin loader and asserts
  `crypto.coingecko` registers under the `crypto` namespace (entry-point wiring guard).
- `test_coingecko.py` — behavior coverage: price formatting, change coloring, `font_color`
  normalization, `draw()` routing, `update()` logging contract, multi-coin batching, symbol
  resolution, rate-limit error handling.

`tools/compare_render.py` — standalone comparison tool used during extraction to assert pixel
identity between the ported renderer and core's original. Retired after core's renderer was
removed in led-ticker#188; see PR history for the comparison baseline.

CI (`.github/workflows/ci.yml`): checks out this repo + led-ticker as siblings (deploy key),
Python 3.14, `uv sync --extra dev`, then `ruff check src tests` and `pytest -q`.

## Adding to the plugin

Register the class in `register()` in `__init__.py` (`api.widget`); it becomes `crypto.<name>`.
Import any core dependency from `led_ticker.plugin` only, and keep the import-purity test green.
If the new widget shares the price-ticker layout (symbol + price + change), reuse
`_ticker_render.draw_price_ticker` rather than duplicating the draw logic.
