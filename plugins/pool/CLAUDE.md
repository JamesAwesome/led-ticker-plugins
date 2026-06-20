# CLAUDE.md

Guidance for Claude Code when working in **led-ticker-pool**, an external plugin for
[led-ticker](https://github.com/JamesAwesome/led-ticker).

`README.md` is the source of truth for the user-facing surface (config options, temperature
zones, layouts, InfluxDB setup). This file keeps the **load-bearing invariants** a contributor
must respect, plus navigation aids. When a fact here and the README disagree about *how a
feature works*, the README wins; this file is the source of truth for *how to keep it working*.

## Overview

This plugin contributes, via the `led_ticker.plugins` entry point, a single widget:

- `pool.monitor` — pool water-temperature from an InfluxDB v2 server (Flux queries). Cycles a
  title card + today's temp (trend arrow), 7-day mean (hi/lo), and season hi/lo, zone-colored by
  temperature. Two layouts: `ticker` (default, single-row segmented; smallsign-friendly) and
  `two_row` (label-on-top / big-number-on-bottom; bigsign/longboi).

The entry-point name `pool` is the plugin namespace, so the config `type` is `pool.monitor`
(see `register()` in `__init__.py`).

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

Python **3.14+** only. Running the widget needs `INFLUXDB_TOKEN` set (see below).

## Package layout

```
src/led_ticker_pool/
  __init__.py     # register(api) → api.widget("monitor")(PoolMonitor)
  monitor.py      # PoolMonitor: async InfluxDB Flux fetch, dual-layout screen building,
                  #   config validation, zone coloring, trend arrows, staleness dimming
```

`register(api)` (in `__init__.py`):

```python
def register(api):
    api.widget("monitor")(PoolMonitor)
```

## Load-bearing invariants

Each rule must hold when modifying `monitor.py`.

**Import only the public surface** — every `led_ticker` import MUST come from `led_ticker.plugin`,
never `led_ticker.<internal>`. Enforced by `tests/test_import_purity.py`, which AST-walks every
source file. If you need a core symbol that isn't on `led_ticker.plugin.__all__`, that's a core
API change — raise it upstream, don't reach around the surface.

**Python 3.14 / PEP 649** — no `from __future__ import annotations` (same rule as core).

**`validate_config()` contract** (`PoolMonitor.validate_config`, a classmethod run pre-coercion by
the engine) — this widget **raises `ValueError`** directly on a bad config (unlike some plugins
that return message strings). It rejects: a `current_window` that isn't a negative Flux duration
(`^-(\d+(ns|us|ms|s|m|h|d|w))+$`); a `sensor_id` outside `[A-Za-z0-9_-]+` (the value is interpolated
into Flux, so this is an injection-safety gate); a `layout` not in `("ticker", "two_row")`; and any
of the two-row-only fields (`top_font`/`bottom_font`/`top_row_height`/the per-row size+threshold
knobs) when `layout != "two_row"` — named, not silently ignored.

**Flux `group()` before aggregation** — multi-sensor buckets MUST `group()` before `last`/`mean`/
`min`/`max`, otherwise the CSV parser picks the first series in tag-sort order and season HI/LO
diverges from today/7-day (the real bug: "season HI 37°F but pool app shows 90°F"). Tripwire:
`test_inserts_group_before_aggregation` in `tests/test_monitor.py`.

**Thread `font` and `label_color` everywhere** — the configured `font` and `label_color` must reach
every `SegmentMessage` / `TwoRowMessage` the widget builds (title + all three stories + the
placeholder). Miss one and the config knob silently no-ops (the "chunky text misplaced" / "label
color ignored" class of bug).

**`current_window` vs `stale_after` are decoupled** — `current_window` is a hard cutoff: no reading
inside it → display `--`. `stale_after` only controls the dim-gray coloring; a reading older than
`stale_after` still displays, dimmed. Don't collapse them.

**No degree symbol in temperatures** — `_fmt_temp` emits bare `F`/`C`, never `°F`/`°C`, because the
hires Inter font rasterized small drops U+00B0 to `?` (consistent with the weather widget).

**`INFLUXDB_TOKEN` is required, never logged** — the widget raises `ValueError` in `start()` (before
entering the monitor loop) if the token is missing, so it surfaces immediately in logs. The token
must never appear in any log line.

**One INFO log per successful `update()`** — the Container contract: a silent log stream after
startup signals the background task died. Each successful update emits exactly one INFO line
(including the current temp, never the token).

**Zone color is always evaluated in °F** regardless of the display unit, so thresholds stay
consistent across imperial/metric. `PoolMonitor` is an `attrs.define` class with several
`kw_only=True` fields (`font`, `layout`, `label_color`, `top_font`, `bottom_font`, `top_row_height`)
— construct with named args for those.

## Tests / CI

`uv run pytest -q` runs the suite (`tests/`):

- `test_import_purity.py` — AST tripwire (public-surface-only). A failure is a contract violation.
- `test_smoke.py` — loads the plugin through led-ticker's real loader; asserts `pool.monitor`
  registers under the `pool` namespace.
- `test_monitor.py` — zone coloring, trend arrows, unit conversion, CSV parsing, Flux query
  building (incl. the `group()` tripwire), both layouts' screen building, `validate_config`, and the
  token/staleness/logging contracts.

CI (`.github/workflows/ci.yml`): checks out this repo + led-ticker as siblings (deploy key),
Python 3.14, `uv sync --extra dev`, then `ruff check src tests` and `pytest -q`.

## Adding to the plugin

Register the class in `register()` in `__init__.py` (`api.widget`); it becomes `pool.<name>`.
Import any core dependency from `led_ticker.plugin` only, and keep the import-purity test green.
