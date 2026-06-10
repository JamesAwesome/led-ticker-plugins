# CLAUDE.md

Guidance for Claude Code when working in **led-ticker-crypto**, an external plugin for
[led-ticker](https://github.com/JamesAwesome/led-ticker).

`README.md` is the source of truth for the user-facing surface (config options, install,
`symbol_id` lookup). This file keeps the **load-bearing invariants** a contributor must
respect, plus navigation aids. When a fact here and the README disagree about *how a
feature works*, the README wins; this file is the source of truth for *how to keep it working*.

## Overview

This plugin contributes, via the `led_ticker.plugins` entry point, a single widget:

- `crypto.coingecko` — live crypto price ticker from the CoinGecko v3 public API (no key
  required). Shows symbol + price (4 decimal places) + 24h change, trend-colored green/red/gray.
  Centered when it fits the canvas; scrolling when it overflows.

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
  __init__.py         # register(api) → api.widget("coingecko")(CoinGeckoPriceMonitor)
  coingecko.py        # CoinGeckoPriceMonitor: async CoinGecko fetch, draw() dispatch,
                      #   start() factory; accepts font_color as a ColorProvider
  _ticker_render.py   # draw_price_ticker(): shared price-ticker renderer ported from core's
                      #   coinbase widget; also defines _ConstantColor and make_default_font_color
  _colors.py          # UP_TREND_COLOR / DOWN_TREND_COLOR / NEUTRAL_TREND_COLOR via lazy_palette
```

`register(api)` (in `__init__.py`):

```python
def register(api):
    api.widget("coingecko")(CoinGeckoPriceMonitor)
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

**This is a faithful port of core's CoinGecko renderer** — `_ticker_render.draw_price_ticker`
was ported from `led_ticker.widgets.crypto.coinbase._draw_price_ticker` (coinbase was removed
from core; the renderer traveled with this plugin). `tools/compare_render.py` proves the renderer
is pixel-identical to the original. Do not change rendering logic in `_ticker_render.py` without
re-running that comparison tool and confirming the diff is intentional.

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

**`font_color` plumbing in `coingecko.py`** — `__attrs_post_init__` normalises the raw config
value: `None` → `make_default_font_color()` (yellow `_ConstantColor`); a plain `Color` (not a
`ColorProvider`) → `_ConstantColor(color)`. After `__attrs_post_init__`, `self.font_color` is
always a `ColorProvider`. `draw()` passes `frame_for("font_color")` so animated providers
(rainbow, shimmer) animate across engine ticks. The 24h change segment uses `_get_change_color`
and ignores `font_color`; this is intentional — change is always trend-colored.

**One INFO log per successful `update()`** — the Container contract: a silent log stream after
startup signals the background task died. `update()` emits one INFO line per call (coin symbol,
never the raw response).

**`start()` accepts `update_interval`** — this parameter is consumed by `start()` before the
`attrs` constructor, so it does NOT appear in `attrs.fields(cls)` and is filtered out of the
`**kwargs` forwarding. Any future parameter that belongs to the monitor lifecycle (not the widget
state) should follow the same pattern: accept in `start()`, don't pass through to `cls(...)`.

## Tests / CI

`uv run pytest -q` runs the suite (`tests/`):

- `test_import_purity.py` — AST tripwire (public-surface-only). Treat a failure as a contract
  violation, not a test to relax.
- `test_smoke.py` — loads the plugin through led-ticker's real plugin loader and asserts
  `crypto.coingecko` registers under the `crypto` namespace (entry-point wiring guard).
- `test_coingecko.py` — behavior coverage: price formatting, change coloring, `font_color`
  normalization, `draw()` routing, `update()` logging contract.

`tools/compare_render.py` — standalone comparison tool (not part of pytest). Renders a fixed
price ticker with both the ported renderer and a reference snapshot and asserts pixel identity.
Re-run it whenever `_ticker_render.py` changes.

CI (`.github/workflows/ci.yml`): checks out this repo + led-ticker as siblings (deploy key),
Python 3.14, `uv sync --extra dev`, then `ruff check src tests` and `pytest -q`.

## Adding to the plugin

Register the class in `register()` in `__init__.py` (`api.widget`); it becomes `crypto.<name>`.
Import any core dependency from `led_ticker.plugin` only, and keep the import-purity test green.
If the new widget shares the price-ticker layout (symbol + price + change), reuse
`_ticker_render.draw_price_ticker` rather than duplicating the draw logic.
