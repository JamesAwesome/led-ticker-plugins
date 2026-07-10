# CLAUDE.md

Guidance for Claude Code when working in **led-ticker-storefront**, an external plugin for
[led-ticker](https://github.com/JamesAwesome/led-ticker).

`README.md` (and the docs-site [storefront page](https://docs.ledticker.dev/plugins/storefront/))
is the source of truth for the user-facing surface (config options, schedule syntax, install).
This file keeps the **load-bearing invariants** a contributor must respect.

## Overview

This plugin contributes, via the `led_ticker.plugins` entry point, one **overlay** — not a
playlist widget. `register(api)` in `__init__.py` wires:

- `api.on_startup(overlay.startup)` — reads the `[storefront]` block, parses + validates the
  schedule, does an eager first evaluation, then spawns a background poll loop
  (`spawn_tracked`) that re-evaluates every `POLL_INTERVAL_S` (30s).
- `api.overlay(overlay.paint)` — paints the active badge (OPEN or CLOSED) on the real canvas
  every frame, before the hardware swap.

The entry-point name `storefront` is both the plugin namespace and the config block —
there's no `type = "x.y"` widget string, since this is a config-block overlay, the same
pattern as core's `busy_light`.

## Load-bearing invariants

- **`paint()` stays paint-only; all state lives in the poller.** `StorefrontOverlay.paint`
  (`overlay.py`) only reads `self.state` and calls `draw_badge` — no clock reads, no schedule
  evaluation, no I/O. All of that lives in `StorefrontOverlay.startup` / `_poll`, which run on
  their own 30s cadence via `spawn_tracked`. `api.overlay` is exception-guarded (a raise
  disables the hook and logs once), but a slow or blocking `paint` still stutters every
  frame — never move schedule/clock work into it.

- **The overnight-wrap rule (`schedule.py:evaluate`).** A day's range whose `end <= start`
  wraps past midnight and belongs to its **start** day. `evaluate(schedule, now)` checks (1)
  today's non-wrapping ranges, then (2) today's wrapping ranges from `start` to midnight, then
  (3) **yesterday's** wrapping ranges from midnight to `end`. So `fri = "18:00-02:00"` reports
  OPEN at Saturday 00:30 — the calendar date rolling over does not flip the badge; the wrap
  is still Friday's range. This is the single most-relitigated design decision here — if you
  touch `evaluate`, re-run `tests/test_schedule.py`'s boundary cases (23:00 on the start day,
  00:30 and 02:30 on the next calendar day, a fully-closed day) before assuming a "fix."

- **Corner / orientation fall back from per-state to shared.** `config.py:_badge` resolves
  `[storefront.open].corner` (or `.orientation`) if present, else the shared
  `[storefront].corner` (or `.orientation`). Only `background`, `padding`, `font`,
  `font_size`, and `timezone` are shared-only with no per-state override (a documented
  future). Don't add a per-state default that silently ignores the shared value, or a shared
  field that silently ignores a per-state override — `_badge`'s `.get(key, shared_value)`
  pattern is the one place this fallback happens; keep new per-state fields going through it.

- **`plugin_config_block` is the core dependency for reading our own TOML.** Overlays get
  `StartupContext.config` (the parsed `AppConfig`), but there is no public way to read a
  plugin's own top-level block off it directly — `StorefrontOverlay.startup` calls
  `plugin_config_block(ctx.config, "storefront")` (from `led_ticker.plugin`, added as a core
  seam specifically for this plugin) rather than reaching into `AppConfig` internals. Needs
  `led-ticker-core` new enough to export it (see the version floor in `pyproject.toml` — bump
  it, don't work around a missing accessor).

- **Import purity:** every module under `src/led_ticker_storefront/` imports ONLY from
  `led_ticker.plugin` (plus stdlib, `attrs`, `zoneinfo`). Never reach into
  `led_ticker.<internal>`. Enforced by `tests/test_import_purity.py` (AST scan).

- **Badge geometry raises loudly, never silently corrupts.** `render.py:draw_badge` computes
  the badge's bounding box before drawing and, if it doesn't fit the panel (a common trap:
  vertical orientation + a large `font_size` + a BDF font on a 64px-tall bigsign), logs a
  warning and skips the draw entirely rather than drawing a clipped/garbled badge. Use a
  hi-res font (`font = "..."`) for a large vertical badge — hi-res isn't bound by the
  BDF cell-height block-scale math.

- **Validation happens at startup, not via `led-ticker validate`.** `validate` only checks
  playlist widgets; a plugin overlay's config is validated inline during `parse_config` /
  `parse_schedule` at startup. A malformed `[storefront]` block (bad time string, unknown
  corner/orientation/weekday, oversized badge) raises there; plugin-load isolation catches it
  (logged, badge disabled, panel keeps running) — this is by design, not a gap to "fix" by
  reaching for `validate`.

- **Not covered by config hot-reload.** `StorefrontOverlay.startup` reads `[storefront]` exactly once, at process startup — there is no re-parse on a hot-reload. A user editing the schedule, badge text/color, corner, or font while the display is running sees no change until the process restarts; core reports this block as restart-required. Don't add a "the config reloaded, why didn't the badge change" bug report to the confusion pile — point at a restart.

- **Exception precedence — specific > recurring > weekly; REPLACES, never merges.**
  `schedule.py:ranges_for` checks `(year, month, day)` in `exceptions` first, then
  `(None, month, day)`, then falls back to the weekly `schedule[DAYS[d.weekday()]]` lookup. A
  matching exception's ranges (including `[]` for `"closed"`) replace the day's ranges outright
  — there is no merge with the weekly schedule underneath a matched exception key.

- **Wrap-belongs-to-start-day generalizes to exception days.** `evaluate` derives "yesterday"
  by calendar date, not weekday — `ranges_for(schedule, exceptions, today - timedelta(days=1))`
  — so a range that wraps past midnight still covers the early hours of the next calendar date
  even when that next date is itself an exception (e.g. `"closed"`). This is the same
  most-relitigated wrap rule from v1, now proven to hold across the exception boundary too.
  Tripwires: `test_wrap_belongs_to_start_day_into_closed_exception` (a weekly Friday
  `18:00-02:00` wrap carries into a `"closed"` Saturday exception) and
  `test_exception_day_wrap_carries_into_next_day` (an NYE exception's wrap carries into a
  `"closed"` Jan 1 exception). If you touch `ranges_for` or `evaluate`, re-run both before
  assuming a "fix."

- **`next_change` is a deliberate brute-force minute scan — do not "optimize" it.**
  `schedule.py:next_change` calls `is_open` once per minute for up to 48 hours (2880 calls of
  pure int arithmetic) until the open/closed state flips, then returns that instant. This is
  intentional, not a placeholder: a minute scan matches `evaluate`'s semantics by construction,
  with no separate boundary-derivation formula that can drift out of sync with `evaluate` as
  the exception/wrap rules evolve. It only runs inside `state.refresh`'s `if changed:` branch —
  i.e. once per real state flip, not once per 30s poll tick — so the cost is bounded. Resist
  rewriting this as a closed-form "find the next range boundary" calculation unless it is
  proven to produce byte-identical results to `evaluate` across every wrap/exception case in
  `test_schedule.py`.

- **`ExcKey` shape: `tuple[int | None, int, int]` = `(year, month, day)`.** `year=None` marks a
  recurring `"MM-DD"` key; a concrete int marks a specific `"YYYY-MM-DD"` key. Both key shapes
  are validated as real calendar dates at parse time (`_validate_calendar_date` in
  `schedule.py`) — recurring `"02-29"` is allowed because the validation probes a hardcoded
  leap year (2024); at evaluation time it then only matches during actual leap years
  (`test_recurring_feb29_matches_leap_years_only`).

- **No `from __future__ import annotations`** (Python 3.14 / PEP 649 rule, same as core).

## Commands

`led-ticker-core` resolves from PyPI (version floor in `pyproject.toml`); no sibling checkout
or `[tool.uv.sources]`. Tests obtain a canvas via `HeadlessCanvas` from `led_ticker.plugin`
(see `tests/conftest.py`); no rgbmatrix stub on the path. Run tooling from the repo root:

```bash
uv sync --extra dev
uv run pytest plugins/storefront
uv run ruff check plugins/storefront
uv run pyright plugins/storefront/src
```

Python **3.14+** only.

## Package layout

```
src/led_ticker_storefront/
  __init__.py   # register(api) -> api.on_startup(overlay.startup) + api.overlay(overlay.paint)
  overlay.py    # StorefrontOverlay: lifecycle glue (startup/poll/paint); paint-only paint()
  state.py      # StorefrontState: shared mutable state (is_open, frame counter) + refresh()
                #   + the diagnostic log line (startup + every state flip)
  schedule.py   # pure schedule parsing/evaluation: parse_time, parse_day, parse_schedule,
                #   evaluate (the overnight-wrap rule), is_open, fmt_range
  config.py     # StorefrontConfig / BadgeSpec: parses [storefront] into typed specs,
                #   corner/orientation shared->per-state fallback, color provider coercion
  render.py     # draw_badge: corner anchor, horizontal/vertical layout, opaque/transparent
                #   background, BDF block-scale vs hi-res, overflow guard
tests/
  test_schedule.py       # parser + evaluator, including overnight-wrap boundary cases
  test_state.py          # refresh() + diagnostic log behavior
  test_config.py         # parse_config, per-state fallback, color coercion
  test_render.py         # geometry per corner x orientation, overflow, color paths
  test_overlay.py        # startup/poll/paint wiring
  test_import_purity.py  # AST: only led_ticker.plugin imports
  test_smoke.py           # entry-point registers the overlay
  conftest.py             # HeadlessCanvas fixtures (real_canvas 256x64, small_canvas 160x16)
examples/
  config.storefront-open-smoke.bigsign.toml    # forces all-day OPEN, vertical shimmer badge
  config.storefront-closed-smoke.bigsign.toml  # forces all-day CLOSED, horizontal red badge
  # simplified single-canvas [display] block for render-demo GIFs — NOT a hardware wiring
  # reference; see config/config.bigsign.example.toml in the core repo for the real 8-panel
  # chain + pixel_mapper_config.
```
