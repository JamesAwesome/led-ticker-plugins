# CLAUDE.md

Guidance for Claude Code when working in **led-ticker-rss**, an external plugin for
[led-ticker](https://github.com/JamesAwesome/led-ticker).

`README.md` is the source of truth for the user-facing surface (config options, install).
This file keeps the **load-bearing invariants** a contributor must respect.

## Overview

This plugin contributes, via the `led_ticker.plugins` entry point, a single widget:

- `rss.feed` — an RSS/Atom headline Container backed by `RSSFeedMonitor`
  (`src/led_ticker_rss/rss.py`). It polls a feed URL in the background and expands each
  story into its own scrolling `TickerMessage`; the engine re-reads `feed_stories` on every
  pass so live updates surface within one cycle.

The entry-point name `rss` is the plugin namespace, so the config `type` is `rss.feed`.
`register()` in `__init__.py` calls `api.widget("feed")(RSSFeedMonitor)`.

This package split out of `led-ticker-feeds` (was `feeds.rss`); history is preserved.

## Load-bearing invariants

- **Public surface only:** `rss.py` imports ONLY from `led_ticker.plugin` (plus stdlib +
  `aiohttp` + `attrs` + `feedparser`). Never reach into `led_ticker.<internal>`. Enforced by
  `tests/test_import_purity.py` (AST scan of `src/led_ticker_rss`).
- **Deps:** `aiohttp` (fetch) and `feedparser>=6.0` (parse). `feedparser` is rss-only — it is
  NOT a weather dep.
- **No `from __future__ import annotations`** (Python 3.14 / PEP 649 rule, same as core).

## Commands

led-ticker is **not on PyPI**; it resolves from a sibling checkout via the monorepo root
`[tool.uv.sources]`. Tests use `make_color` from `led_ticker.plugin` (led-ticker-core ≥ 2.1);
no rgbmatrix stub on the import path. Run tooling from the repo root:

```bash
uv sync --extra dev
uv run pytest plugins/rss
uv run ruff check plugins/rss
uv run pyright plugins/rss/src
```

Python **3.14+** only.

## Package layout

```
src/led_ticker_rss/
  __init__.py   # register(api) → api.widget("feed")(RSSFeedMonitor)
  rss.py        # RSSFeedMonitor (Container): update() pulls + parses the feed
tests/
  test_rss.py            # widget behavior
  test_import_purity.py  # AST: only led_ticker.plugin imports
  test_smoke.py          # entry-point registers rss.feed
  conftest.py            # shared canvas / make_widget fixtures
```
