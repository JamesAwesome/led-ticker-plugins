# CLAUDE.md

Guidance for Claude Code when working in **led-ticker-weather**, an external plugin for
[led-ticker](https://github.com/JamesAwesome/led-ticker).

`README.md` is the source of truth for the user-facing surface (config options, install).
This file keeps the **load-bearing invariants** a contributor must respect.

## Overview

This plugin contributes, via the `led_ticker.plugins` entry point, two widgets and one
source:

- `weather.current` — a current-conditions widget backed by `WeatherWidget`
  (`src/led_ticker_weather/weather.py`). It fetches current conditions from
  [WeatherAPI.com](https://www.weatherapi.com/) (key via the `WEATHERAPI_KEY` env var) and
  draws the location label, temperature, and a condition icon.
- `weather.forecast` — a held multi-day forecast card backed by `ForecastWidget`
  (`src/led_ticker_weather/forecast.py`). It fetches
  `WeatherAPI.com`'s `/v1/forecast.json?days=7` endpoint and renders one of three
  per-sign layouts, auto-detected via `resolve_forecast_layout` (`"strip"` on scale-1
  signs, `"big"` on hi-res panels under 400px physical width, `"long"` on wider hi-res
  panels — e.g. longboi). Supports `demo = true` for offline/preview rendering.
- `weather.current` (source form) — `WeatherSource` (`src/led_ticker_weather/source.py`),
  a `PolledDataSource` exposing current-conditions fields as a value token (e.g.
  `:weather.nyc:`), rendered through a `format` string.

The entry-point name `weather` is the plugin namespace, so the config `type` is
`weather.current` / `weather.forecast`, and the value-token source name is
`weather.current` too (widgets and sources are separate registries). `register()` in
`__init__.py` calls `api.widget("current")(WeatherWidget)`,
`api.widget("forecast")(ForecastWidget)`, and `api.source("current")(WeatherSource)`.

This package split out of `led-ticker-feeds` (was `feeds.weather`); history is preserved.

## Load-bearing invariants

- **Public surface only:** `weather.py` imports ONLY from `led_ticker.plugin` (plus stdlib +
  `aiohttp` + `attrs`). Never reach into `led_ticker.<internal>`. Enforced by
  `tests/test_import_purity.py` (AST scan of `src/led_ticker_weather`).
- **Deps:** `aiohttp` only (no `feedparser` — that is an rss-only dep).
- **Condition → icon mapping:** `_match_condition(condition) -> slug` is the icon resolver
  (sun / cloud / rain / snow / thunder / fog; unknown defaults to sun). `test_weather_icons.py`
  is the per-branch tripwire; `test_weather.py` asserts every slug it can return exists in both
  the lowres and hires emoji registries.
- **`WEATHERAPI_KEY`:** `test_weather.py` provides it via an autouse `monkeypatch.setenv`
  fixture — never hardcode a real key. `test_weather_icons.py` calls the pure resolver and
  needs no key.
- **No `from __future__ import annotations`** (Python 3.14 / PEP 649 rule, same as core).

## Forecast invariants

The handoff at `plugins/weather/design/` (README.md + `led-engine-bundle.js`) is
NORMATIVE for forecast geometry and color — a contributor changing layout math or
palette values should be reading it, not guessing.

- **Geometry via `js_round`, never bare `round()`** — the handoff was authored against JS
  `Math.round` (half-up), which differs from Python's banker's-rounding `round()` at `.5`
  boundaries; `paint.js_round` is the port.
- **Hires text y-targets are visual cap-top** — the design engine crops its text masks to
  visible ink, so a handoff `y` must go through `paint.cap_top` before `hires()`, never
  passed raw.
- **Hires text is never exact-pinned in tests** — freetype rendering varies across
  platforms, so `test_forecast_layouts.py` asserts hires text shape-level only; lowres
  emoji blits and dotted dividers ARE exact SetPixel math and may be pinned.
- **Strip icons are curated-lowres-only** — `render_strip_small` passes
  `max_emoji_height=8`; the hires gate it relies on is `is_scaled(canvas)`, NOT
  `scale > 1`, so a scale=1/2 `ScaledCanvas` still renders lowres (tripwire:
  `test_strip_icons_stay_lowres_through_scale1_wrapper`).
- **Held-cursor returns the wrapper's LOGICAL width** — `ForecastWidget.draw` returns
  `canvas.width` (never `unwrap_to_real(canvas).width`); the engine compares the cursor
  against the wrapper's width, and the real width would wrongly route through the scroll
  branch.
- **`KIND_SLUGS`'s lowres column must stay curated-both-registries** — every lowres slug
  in the table must exist in both the lowres and hires curated emoji registries; pack
  (standard-pack) slugs are hires/hero-only and never appear in the lowres column
  (tripwires in `test_forecast_data.py`).
- **Numeric payload fields are `float()`-coerced at parse** — `parse_forecast_payload`
  coerces every numeric WeatherAPI field at parse time, so bad/missing data fails loudly
  in `update()` (surfaced via the monitor loop's error path) rather than silently at draw
  time.
- **`run_monitor_loop(..., immediate=widget._data is None)`** — guards the boot-race
  blindness where a failed eager fetch would otherwise leave the widget hidden
  (`should_display() == False`) for a full `update_interval` (~3h default) before the
  background loop's first retry (the F1 fix).

## Commands

`led-ticker-core` resolves from PyPI (`>=4.27`); no sibling checkout or
`[tool.uv.sources]`. The floor is 4.27, not merely "whatever ships the forecast hero's
standard-pack emoji slugs" — `sun_behind_large_cloud` / `sun_behind_rain_cloud` (used by
the "big"/"long" hero layouts) only exist in core >= 4.21, and `draw_emoji_at` on an older
core raises `KeyError` for them; 4.27 is the version this suite actually validates
against. Tests obtain a canvas via `HeadlessBackend(...).create_canvas()` from
`led_ticker.plugin` (shipped in led-ticker-core ≥ 2.1); no rgbmatrix stub on the path. Run
tooling from the repo root:

```bash
uv sync --extra dev
uv run pytest plugins/weather
uv run ruff check plugins/weather
uv run pyright plugins/weather/src
```

Python **3.14+** only.

## Package layout

```
src/led_ticker_weather/
  __init__.py          # register(api) → api.widget("current")(WeatherWidget),
                        #   api.widget("forecast")(ForecastWidget)
  weather.py           # WeatherWidget + _match_condition icon resolver
  source.py            # WeatherSource — weather.current value-token PolledDataSource
  forecast.py          # ForecastWidget + resolve_forecast_layout (per-sign dispatch)
  forecast_data.py     # WeatherAPI fetch/parse, cond_kind mapping, KIND_SLUGS, DEMO_DATA
  forecast_layouts.py  # render_strip_small / render_hero_big / render_hero_long
  paint.py             # hi-res paint helpers (js_round, cap_top, phys_wrap) ported from baseball
  palette.py           # semantic RGB palette from design/README.md Design Tokens
tests/
  test_weather.py                 # widget behavior (autouse WEATHERAPI_KEY fixture)
  test_weather_icons.py           # _match_condition per-branch tripwire
  test_import_purity.py           # AST: only led_ticker.plugin imports
  test_smoke.py                   # entry-point registers weather.current / weather.forecast
  test_source.py                  # WeatherSource format-token behavior
  test_forecast_widget.py         # ForecastWidget draw/update/start/validate_config
  test_forecast_data.py           # cond_kind per-code-band tripwires + KIND_SLUGS registry checks
  test_forecast_layouts.py        # per-sign renderers (shape-level hires, exact-pinned lowres/dividers)
  test_paint.py                   # js_round / cap_top ported-formula tripwires
  test_resolve_forecast_layout.py # resolve_forecast_layout parametrized matrix
  conftest.py                     # shared canvas / make_widget fixtures
```
