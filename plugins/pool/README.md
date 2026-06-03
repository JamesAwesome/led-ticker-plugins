# led-ticker-pool

A pool water-temperature monitor **widget** for [led-ticker](https://github.com/JamesAwesome/led-ticker), backed by an InfluxDB v2 server. It's a led-ticker **plugin** — installing this package contributes a `pool.monitor` widget you reference in your led-ticker config:

```toml
[[playlist.section.widget]]
type = "pool.monitor"
title = "POOL TEMPS"
layout = "two_row"
```

The widget cycles current / today / 7-day / season water temperatures, fetched from InfluxDB (Flux queries over HTTP). Configure the server via env vars (`INFLUXDB_URL`, `INFLUXDB_ORG`, `INFLUXDB_BUCKET`, `INFLUXDB_TOKEN`) or widget fields.

## Install

```bash
pip install led-ticker-pool        # once published
```

The widget is discovered automatically via the `led_ticker.plugins` entry point — no `[plugins]` config needed. For a containerized led-ticker, add `led-ticker-pool` to your `config/requirements-plugins.txt` (or a `FROM led-ticker` image layer).

## Development

led-ticker is not yet on PyPI, so install it editable from a sibling checkout. This repo's `pyproject.toml` pins `led-ticker` to `../led-ticker` via `[tool.uv.sources]`:

```bash
git clone <led-ticker> ../led-ticker        # a checkout on the main branch
git clone <this repo> led-ticker-pool && cd led-ticker-pool
uv venv
uv pip install -e ../led-ticker -e ".[dev]"
uv run pytest -q
```

> **Note (plugin-author friction, captured for the led-ticker docs):** led-ticker's `graphics` (Color etc.) works headless via its bundled stub, but the full `RGBMatrix`/canvas test stub lives in led-ticker's `tests/stubs/` and is not shipped. This repo's tests put it on the path via `pyproject.toml`'s `[tool.pytest.ini_options] pythonpath = ["../led-ticker/tests/stubs"]`. Tests that only exercise data/screen-building logic (not real canvas rendering) don't need it.

## Status

Phase 2 scaffold: the entry-point channel is proven (`tests/test_smoke.py`). Phase 3 ports the real `PoolMonitor` (registered as `pool.monitor`).
