# `stocks.trend` color provider — design spec

**Date:** 2026-07-15
**Status:** approved (brainstorm) — pending user review before planning
**Home:** `led-ticker-plugins` monorepo, `plugins/stocks/` (branch `feat/stocks-trend-color`)
**Builds on:** Phase 4 (`stocks-v0.4.0` — shared `QuoteCache`). Ships as **v0.5.0**.
**Context:** Phase-1 of the "source token supports colors" work. Phase 2 (per-token colored
value tokens in core) is deferred — see §7.

---

## 1. Summary

Register a plugin **color provider** `stocks.trend` so a message (or any text widget) can be
tinted **green (up) / red (down) / neutral (flat or no-data)** by a symbol's day change,
reading the shared `QuoteCache`. Set it as `font_color`:

```toml
[[playlist.section.widget]]
type = "message"
text = "AAPL :stocks.aapl:"
font_color = {style = "stocks.trend", symbol = "AAPL"}
# optional: up = [r,g,b], down = [r,g,b], flat = [r,g,b], green_up = true
```

This colors the WHOLE message by trend (the common ticker-line case). It is entirely
plugin-side — core already exposes `api.color_provider` (since v4.9.0, the plugin's existing
floor), and the coercion path instantiates a plugin provider from the `{style = "..."}` table
via `_build_plugin_style(cls, kwargs)`, validating the table's keys against the class
`__init__`.

## 2. Verified architecture (grounding)

- **Registration:** `api.color_provider("trend")(cls)` buffers as `stocks.trend`; the plugin
  loader merges the `color_providers` buffer into core's `_PROVIDER_REGISTRY`
  (`_plugin_loader.py`).
- **Coercion:** `font_color = {style = "stocks.trend", symbol = "AAPL", ...}` →
  `_coerce_color_provider` → `_provider_from_style("stocks.trend", kwargs)` → (namespaced ⇒)
  `_build_plugin_style(cls, kwargs, ...)`, which validates `kwargs` against `cls.__init__` and
  instantiates. So the `__init__` parameter names ARE the config surface, and an `__init__`
  that raises `ValueError` on bad input surfaces the error at config-load.
- **Contract:** `ColorProvider` requires `per_char: bool`, `frame_invariant: bool`,
  `color_for(frame, char_index, total_chars) -> Color`. Subclassing `ColorProviderBase`
  enforces an explicit `frame_invariant` at class-definition time.
- **Widget parity:** the widget's `chg_color` (`layouts/_common.py`) is
  `chg = quote.change or 0; UP if chg > 0 else DOWN if chg < 0 else FLAT`, with `green_up`
  flipping UP/DOWN. `quote.change` is `None` when `not has_data` (→ `or 0` → FLAT). The
  provider mirrors this exactly.

## 3. The provider — `StocksTrendColor`

New file `plugins/stocks/src/led_ticker_stocks/trend_color.py`.

- `class StocksTrendColor(ColorProviderBase)` with `per_char = False`,
  `frame_invariant = False` (color tracks live data — must be re-evaluated each draw so a
  trend flip shows promptly; matches Rainbow/ColorCycle).
- `__init__(self, symbol, up=None, down=None, flat=None, green_up=True)`:
  - `symbol` (str) required — raise `ValueError` (with a clear message) if missing/empty or
    not a str; reject an FX-looking `symbol` (`/`) with the forex-is-paid hint (mirrors the
    source's `validate_config`).
  - `up` / `down` / `flat`: optional `[r,g,b]` lists → validated (ints 0-255, reject bool) and
    converted to `graphics.Color`. Defaults: `up = pal.UP` (60,220,60), `down = pal.DOWN`
    (255,60,60), `flat = make_color(150,150,150)` (neutral gray). Reusing `pal.UP`/`pal.DOWN`
    keeps the provider's up/down in sync with the widget's arrow colors.
  - `green_up` (bool, default `True`) — flips UP/DOWN for non-US convention.
  - Registers the symbol into the shared cache: `get_cache().register([symbol])`. This joins
    the symbol to the cache's union so it rides the same poll loop a `:stocks.<id>:` token or
    `stocks.ticker` widget started (the Phase-4 late-registrant catch-up covers a provider
    constructed after the cache started). It does NOT start the cache — a color provider is
    not a data source and has no session/async context. See §5 (the feeding requirement).
- `color_for(self, frame, char_index, total_chars) -> Color`:
  `q = get_cache().get(self.symbol); chg = (q.change if q is not None else None) or 0;`
  `return up if chg > 0 else down if chg < 0 else flat` (with up/down swapped when
  `green_up` is False). No exceptions — a color provider must never raise into the render loop.

## 4. Registration + validation

- `__init__.py`: add `api.color_provider("trend")(StocksTrendColor)` alongside the existing
  `api.widget("ticker")` / `api.source("quote")`.
- Validation is at config-load via `__init__` raising `ValueError` (surfaced by the coercion
  path). There is no separate `validate_config` hook for providers.

## 5. The feeding requirement (documented sharp edge)

The provider READS the cache; it does not start polling. To actually color by trend, the
symbol must be fed by a `stocks.quote` source or a `stocks.ticker` widget in the same config
so the cache is started and the symbol polled. The natural usage —
`text = "AAPL :stocks.aapl:"` + `font_color = {style="stocks.trend", symbol="AAPL"}` — already
has one (the `:stocks.aapl:` source). A config that sets the trend provider for a symbol with
NO source/widget feeding it will render the `flat` color (the cache never starts). Document
this clearly in the README and CLAUDE.md; do NOT try to self-start the cache from a provider.

## 6. Testing

- **Unit** (`tests/test_trend_color.py`): `chg > 0` → up color; `chg < 0` → down color; `chg == 0`
  and no-data (`get` returns None, or a zeroed quote) → flat color; `green_up = False` swaps
  up/down; config `up`/`down`/`flat` overrides applied; missing/empty/non-str `symbol` raises;
  FX `symbol` raises; bad `[r,g,b]` (out of range, bool, wrong length) raises; construction
  registers the symbol into the cache; `per_char is False` and `frame_invariant is False`;
  `color_for` never raises even when the cache is empty. Use the cache `reset()` autouse
  fixture for hermeticity (mirror `tests/test_cache.py`).
- **Coercion integration:** `_coerce_color_provider({"style": "stocks.trend", "symbol": "AAPL"})`
  (with the plugin loaded) returns a `StocksTrendColor`; an unknown kwarg raises via
  `_build_plugin_style`. (If loading the plugin registry in a unit test is heavy, assert the
  registration wiring directly instead — `api.color_provider("trend")` is called in `register`.)
- **Visual GIF gate (required before merge):** render a message with a demo-backed token and
  `font_color = {style="stocks.trend", symbol="AAPL"}`; confirm the message tints green/red as
  the demo price walks up/down (the color tracks the trend, no garbage on flat/no-data).

## 7. Out of scope (Phase 2, deferred)

- **Per-token colored value tokens** (core change): label-white + price-green in ONE message.
  Requires core's value-token system to carry per-segment color and every token-rendering
  widget to apply it. Tracked as a separate future core effort.
- Flash-on-change in the token (the widget's Bloomberg flash) — steady trend color only here.
- Indices/FX colors; sparkline-in-a-token; per-char trend gradients.

## 8. Phasing (for the plan)

1. **`StocksTrendColor`** — the provider class + registration + unit tests.
2. **Docs + example + release** — README (the provider, config table, the feeding
   requirement, `green_up`), CLAUDE.md invariant, an `examples/` config, `stocks-v0.5.0`.
