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
- **`description = "append"` is opt-in and title-only is the default.**
  `fold_description(title, html, skip_patterns=..., max_chars=...)` is the ONE place
  description HTML becomes headline text (stdlib `HTMLParser`; block tags split paragraphs;
  `<script>`/`<style>`/`<textarea>` contents and `<img>` contribute nothing; a literal
  `<![CDATA[` is kept as text; a `text/plain` declared type — from `summary_detail`, or
  from `content[0]` when feedparser filled `summary` from `<content>` and left
  `summary_detail` unset — bypasses the parser as one paragraph). Title dedup is TOKEN-based, deliberately NOT
  substring containment and NOT a char-length floor (both were tried and failed review:
  substring ate one-word notes, an 8-char floor leaked "Nov 11"): `_restates_title` drops
  a paragraph only when its alnum words are a CONTIGUOUS run of ≥ `_DEDUP_MIN_TOKENS` (2)
  title words, or equal the whole title — both sides of that boundary are pinned
  (`test_short_restated_date_is_dropped`, `test_short_paragraph_echoing_a_title_word_is_kept`,
  `test_title_words_out_of_order_are_not_a_restatement`). The source field is feedparser
  `summary`, which falls back to `content:encoded` / Atom `<content>` (full body) — hence
  `description_max_chars` (default 200, 0 = uncapped; the cap INCLUDES the ellipsis and
  never ends on a dangling `·`) on the folded part only. A title-less item renders its
  folded text alone; any item whose text resolves to `""` is skipped BEFORE the
  `max_stories` islice (the old `item["title"]` KeyError'd the whole update).
  `_LIST_FIELD_HINTS` carries the three knobs for `--list-fields rss.feed`. The feed `<title>` (`feed_title`) is never
  folded. `validate_config` rejects unknown `description` values, non-list / invalid-regex
  `description_skip`, and non-int / negative `description_max_chars` (bool excluded);
  `description_skip` without `append` is ADVISORY via `validate_config_warnings`, not an
  error. Tripwires: `tests/test_description.py` (incl. an engine-path test through core's
  `validate_widget_cfg`).

## Commands

`led-ticker-core` resolves from PyPI (`>=2.1`); no sibling checkout or `[tool.uv.sources]`.
Tests use `make_color` from `led_ticker.plugin` (led-ticker-core ≥ 2.1);
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
  rss.py        # RSSFeedMonitor (Container): update() pulls + parses the feed;
                #   fold_description() for the `description = "append"` knob
tests/
  test_rss.py            # widget behavior
  test_description.py    # description knob + fold_description + validate_config
  test_import_purity.py  # AST: only led_ticker.plugin imports
  test_smoke.py          # entry-point registers rss.feed
  conftest.py            # shared canvas / make_widget fixtures
```
