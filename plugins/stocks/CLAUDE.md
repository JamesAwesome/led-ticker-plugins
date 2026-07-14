# CLAUDE.md

Guidance for Claude Code when working in **led-ticker-stocks**, an external plugin for
[led-ticker](https://github.com/JamesAwesome/led-ticker).

`README.md` is the source of truth for the user-facing surface (config options, install,
rate limits, FX limitation, demo mode). This file keeps the **load-bearing invariants** a
contributor must respect, plus navigation aids. When a fact here and the README disagree
about *how a feature works*, the README wins; this file is the source of truth for *how to
keep it working*.

## Overview

This plugin contributes, via the `led_ticker.plugins` entry point, a single widget:

- `stocks.ticker` — live equity price Container from the Finnhub REST API. Cycles one
  `_StockStory` "story" per configured symbol (the engine reads `feed_stories` via
  `_expand_sources` on every pass). Shows `SYM  price  ▲/▼ change change%`, trend-colored
  green/red, dimmed by market state. Phase 1 ships exactly one layout (`crawl`, smallsign
  geometry) — see the README's Roadmap for `card`/`dashboard`.

The entry-point name `stocks` is the plugin namespace, so the config `type` is
`stocks.ticker` (see `register()` in `__init__.py`).

## Commands

`led-ticker-core` resolves from PyPI (`>=4.9`) like any other dependency — no sibling
checkout, no `[tool.uv.sources]`, no deploy key. Tests that need a headless canvas obtain
one via `HeadlessBackend(...).create_canvas()` from `led_ticker.plugin` — no rgbmatrix stub
on the path.

```bash
uv sync --extra dev                          # install deps (led-ticker-core from PyPI)
uv run pytest --cov=led_ticker_stocks -q     # full suite, coverage gate fail_under = 90
uv run ruff check src/ tests/                # or: make lint (monorepo root)
uv run ruff format --check src/ tests/
uv run pyright src
```

Python **3.14+** only.

## Package layout

```
src/led_ticker_stocks/
  __init__.py         # register(api) → api.widget("ticker")(StocksTicker)
  ticker.py            # StocksTicker (Container): validate_config(), start(), update();
                       #   _StockStory: per-symbol story reading the shared quote dict
  finnhub.py           # FinnhubClient (quote + market-status GETs); parse_quote()
  model.py             # SymbolQuote + format_price/format_change/format_pct
  state.py             # MarketState enum + STATE_META (dim/label/color/pulses) +
                       #   state_from_status() (Finnhub) + state_from_clock() (fallback, unused
                       #   by the live path today — kept for a future no-status-endpoint path)
  demo.py              # DemoFeed: seeded offline random-walk feed for demo=true / no-token
  _palette.py           # Semantic RGB palette (SYM/PRICE/UP/DOWN/FLAT/LABEL) + dim()
  layouts/
    __init__.py         # LAYOUTS registry ({"crawl": draw_crawl_story}) + resolve_layout()
    crawl.py             # draw_crawl_story(): the one Phase-1 render function
```

`register(api)` (in `__init__.py`):

```python
def register(api):
    api.widget("ticker")(StocksTicker)
```

## Load-bearing invariants

Each rule must hold when modifying the named files.

**Import only the public surface** — every `led_ticker` import MUST come from
`led_ticker.plugin`, never `led_ticker.<internal>`. Enforced by `tests/test_import_purity.py`,
which AST-walks every source file. Intra-package imports
(`from led_ticker_stocks._palette import …`) are fine.

**Python 3.14 / PEP 649** — no `from __future__ import annotations` anywhere (same rule as
core). Bare `dict[str, SymbolQuote]` / `tuple` annotations are fine.

**`StocksTicker` is a Container** — it exposes `feed_stories: list[_StockStory]` (one story
per symbol), all reading a SHARED `self._quotes: dict[str, SymbolQuote]` mutated in place by
`update()`. The engine reads `feed_stories` via `_expand_sources` on every pass, so a price
update surfaces within at most one cycle. **Never** snapshot `feed_stories` into a cycle
iterator, and never give each `_StockStory` its own copy of a quote — that was the longboi
stale-display pattern (a container that updates correctly in the background but a frozen
snapshot never sees it). `_StockStory.quotes` and `state_ref` are the SAME dict/list object
handed to every story and mutated by `StocksTicker.update()`; a story never owns its data.

**Token is env-only, never a `start()` parameter** — `StocksTicker.start()` deliberately does
NOT declare a `token` parameter. Core's widget factory unions a Container's `start()` keyword
signature into the set of config keys it will bind, so if `token` were a `start()` parameter,
a user's `token = "..."` in `config.toml` would silently override the env secret and flow
straight into Finnhub HTTP requests — exactly the leak `resolve_secret_token` /
"secrets belong in `.env`" is meant to prevent. `start()` always resolves
`os.getenv("FINNHUB_API_TOKEN", "")` itself. Defense in depth: even if a stray `token` arrives
via `start(**kwargs)` (e.g. a future config field collision), it is explicitly filtered out of
the `cls(...)` call (`k != "token"`) before the resolved env value is applied last, so a
config-supplied value can never win. Tripwires: `test_config_token_is_ignored`,
`test_config_token_is_ignored_no_env` (`tests/test_ticker.py`).

**Empty token silently routes to demo, not an error** — `__attrs_post_init__` treats
`self.demo or not self.token` as one condition: `demo = true` OR a missing/empty
`FINNHUB_API_TOKEN` both land on the exact same `DemoFeed` path. This is intentional (a sign
that forgot to set the env var boots with a visible, moving placeholder rather than a
dead/erroring widget) — do not turn "no token" into a hard failure without updating the
README's demo-mode section, which documents this fallback as the recommended smoke-test path.

**Rate rule: `effective_interval = max(update_interval, len(symbols) + 1)`** — computed once
in `start()` before construction and stored as `self.update_interval` (passed to
`run_monitor_loop`). Each `update()` costs `len(symbols) + 1` Finnhub requests (1 status +
1-per-symbol quote) while the market is open, or exactly **1** while closed (see the no-quote-
calls-when-closed rule below). Finnhub's free tier is 60 req/min **per API key**, not per
widget instance — the README's rate-limit section documents that two signs or two
Finnhub-backed widgets sharing one token divide the same budget; this code cannot see or
enforce that cross-widget sharing, only the single-widget floor.

**No quote calls while the market is closed** — `update()` always fetches market status
first; if `state_from_status(...)` resolves to `MarketState.CLOSED` it returns immediately
without calling `fetch_quote` for any symbol (comment: "frozen when closed — hold last
prices"). This is both a rate-budget optimization (1 request instead of `N+1`) and the
correct product behavior (equity prices don't change when the exchange is shut). Don't add a
"keep polling anyway" mode without updating the rate-rule math above.

**No-data guard: `pc == 0` (or `c == 0`) never divides** — `SymbolQuote.has_data` is
`self.prev != 0 and self.price != 0`; `change`/`pct` both return `None` — never attempt
`(price - prev) / prev` — whenever `has_data` is false. `parse_quote` maps a missing/zero
Finnhub `c`/`pc` straight through (`float(payload.get("c") or 0.0)`), which is exactly the
shape Finnhub returns for an unrecognized symbol or a not-yet-fetched initial placeholder
(`{"c": 0, "pc": 0}`, set in `__attrs_post_init__` before the first live fetch completes).
`draw_crawl_story` checks `quote.has_data` and short-circuits to an em-dash placeholder row
before touching `format_price`/`format_change`/`format_pct` — do not reorder the has_data
check to run after any arithmetic on `price`/`prev`. Tripwire:
`test_no_data_placeholder_renders_without_raising` (`tests/test_render_smoke.py`).

**Market-state mapping: `closed = not isOpen`, else map `session`** —
`state_from_status(payload)` treats ANY falsy `isOpen` (including a missing key) as
`MarketState.CLOSED` — this correctly covers holidays and weekends where Finnhub's `session`
key may be null or absent, without a separate holiday calendar. Only when `isOpen` is truthy
does the code look at `session` (`"pre-market"` → `PRE`, `"regular"` → `OPEN`,
`"post-market"` → `AFTER`; an unrecognized/missing session string while `isOpen` is true
defaults to `OPEN`, not `CLOSED` — don't flip that default). `state_from_clock()` is a
US/Eastern wall-clock fallback that exists in `state.py` but has **no live call site** today
(`update()` always calls the Finnhub status endpoint) — it's retained for a future
"status endpoint unreachable" fallback path; don't delete it as dead code without checking
for that use case first.

**`STATE_META` drives both label and dim, keep them paired** — `StateMeta.dim` (`0.45` CLSD /
`0.85` PRE/AFTER / `1.0` OPEN) is applied via `_palette.dim(color, factor)` in
`draw_crawl_story`, and `chip_label` (`CLSD`/`PRE`/`AH`/`LIVE`) + `chip_rgb` are wired for a
future state chip (not drawn in Phase 1's crawl — the crawl row has no room for a chip; it's
consumed by `dim` only today). Don't repurpose `dim` for anything else without checking the
README's "dims visibly lower when CLSD" claim, which is validated by
`test_state_dimming_lowers_total_brightness` (`tests/test_render_smoke.py`).

**Geometry auto-select happens in `draw()`, not `validate_config`** — `resolve_layout(canvas,
override)` needs a real `canvas.width`, which does not exist at config-validation time
(`validate_config` only sees the raw TOML dict, no canvas). `validate_config` can only check
that an explicit `layout` STRING names a registered layout (`LAYOUTS` membership); the actual
width-based auto-select / `NotImplementedError` for non-`crawl`-sized canvases fires lazily
inside `_StockStory.draw()` on first draw (cached to `self._resolved` so it only resolves
once per story, not once per frame). Do not try to move the width check into
`validate_config` — there's nothing to check it against yet.

**`green_up` is plumbed but currently a no-op** — `StocksTicker.green_up` /
`_StockStory.green_up` are threaded from config through construction, but
`draw_crawl_story` does not read it (colors are hardcoded green-for-positive /
red-for-negative). It's reserved for a future "invert colors" knob. Don't document it as a
working option in the README until `crawl.py` actually consumes it.

**`_StockStory` is `FrameAwareBase`** — it calls `self.frame_for("crawl")` and passes the
result to `draw_crawl_story` as `frame=`, but Phase 1's renderer doesn't yet do anything
frame-dependent with it (no animated color/border on this widget yet — see the README's
Phase 3 roadmap for price-flash / pulses). The plumbing is there so Phase 3 doesn't need a
widget-shape change, only a `layouts/crawl.py` behavior change.

**One INFO log per successful `update()`** — the Container contract: a silent log stream
after startup signals the background task died. Demo mode logs
`"stocks.ticker demo tick: N symbols"`; live mode logs `"stocks.ticker updated: N/M symbols"`
(or `"market closed — holding last prices"` when it short-circuits). Never log the raw
Finnhub response body (it doesn't contain secrets, but keep the convention consistent with
other first-party plugins).

**Initial fetch failure is tolerated, not fatal** — `start()` wraps its first `update()` call
in `try/except Exception`, logs a warning, and still constructs + starts the monitor loop on
failure (e.g. Finnhub rate-limited or unreachable at boot). The widget always renders
something (last-known or placeholder prices) rather than being dropped from the section for
the whole session.

## Tests / CI

`uv run pytest --cov=led_ticker_stocks -q` runs the suite (`tests/`), coverage gate 90%:

- `test_import_purity.py` — AST tripwire (public-surface-only). Treat a failure as a contract
  violation, not a test to relax.
- `test_smoke.py` — loads the plugin through led-ticker's real plugin loader and asserts
  `stocks.ticker` registers under the `stocks` namespace (entry-point wiring guard).
- `test_ticker.py` — `StocksTicker`/`_StockStory` behavior: `validate_config` (empty symbols,
  FX rejection, unknown layout), shared-quote story draw, demo-mode `start()`, live `update()`,
  and the token-leak-prevention pair above.
- `test_finnhub.py` — `FinnhubClient` request shaping + `parse_quote`.
- `test_model.py` — `SymbolQuote.has_data`/`change`/`pct` no-data guard + formatting.
- `test_state.py` — `state_from_status` mapping (isOpen/session) + `state_from_clock` fallback.
- `test_demo.py` — `DemoFeed` deterministic seeding + `step()`.
- `test_palette.py` — `dim()` scaling.
- `test_crawl.py` — Mock-canvas `draw_crawl_story` cursor-arithmetic coverage.
- `test_render_smoke.py` — REAL `HeadlessBackend` canvas pixel assertions (state dimming
  actually lowers brightness, up/down colors actually flip, no-data placeholder actually
  lights pixels) — the class of bug a Mock-canvas test structurally cannot catch.

CI is the monorepo's single root path-filtered per-member matrix (`.github/workflows/ci.yml`):
Python 3.14, `uv sync --extra dev` (led-ticker-core from PyPI), then runs ruff check,
ruff format --check, pyright, and pytest for the changed member.

## Adding to the plugin

Register the class in `register()` in `__init__.py` (`api.widget`); it becomes
`stocks.<name>`. Import any core dependency from `led_ticker.plugin` only, and keep the
import-purity test green. A new layout goes in `layouts/`, registered in `LAYOUTS`
(`layouts/__init__.py`) with the same signature as `draw_crawl_story` (see its docstring in
`ticker.py`'s `_StockStory.draw` for the exact call shape:
`renderer(canvas, quote, state, cursor_pos, frame=..., y_offset=..., end_padding=...)`).
