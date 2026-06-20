# CLAUDE.md

Guidance for Claude Code when working in **led-ticker-weather**, an external plugin for
[led-ticker](https://github.com/JamesAwesome/led-ticker).

`README.md` is the source of truth for the user-facing surface (config options, install).
This file keeps the **load-bearing invariants** a contributor must respect.

## Overview

This plugin contributes, via the `led_ticker.plugins` entry point, a single widget:

- `weather.current` — a current-conditions widget backed by `WeatherWidget`
  (`src/led_ticker_weather/weather.py`). It fetches current conditions from
  [WeatherAPI.com](https://www.weatherapi.com/) (key via the `WEATHERAPI_KEY` env var) and
  draws the location label, temperature, and a condition icon.

The entry-point name `weather` is the plugin namespace, so the config `type` is
`weather.current`. `register()` in `__init__.py` calls `api.widget("current")(WeatherWidget)`.

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

## Commands

led-ticker is **not on PyPI**; it resolves from a sibling checkout via the monorepo root
`[tool.uv.sources]`. The rgbmatrix stub is vendored at the monorepo root and put on the
import path by the **root** `pyproject.toml`. Run tooling from the repo root:

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
  __init__.py   # register(api) → api.widget("current")(WeatherWidget)
  weather.py    # WeatherWidget + _match_condition icon resolver
tests/
  test_weather.py        # widget behavior (autouse WEATHERAPI_KEY fixture)
  test_weather_icons.py  # _match_condition per-branch tripwire
  test_import_purity.py  # AST: only led_ticker.plugin imports
  test_smoke.py          # entry-point registers weather.current
  conftest.py            # shared canvas / make_widget fixtures
```
