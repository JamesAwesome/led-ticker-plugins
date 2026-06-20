# CLAUDE.md

Guidance for Claude Code when working in **led-ticker-calendar**, an external plugin for
[led-ticker](https://github.com/JamesAwesome/led-ticker).

`README.md` is the source of truth for the user-facing surface (widget options, layouts, install).
This file keeps the **load-bearing invariants** a contributor must respect, plus navigation aids.
When a fact here and the README disagree about *how a feature works*, the README wins; this file
is the source of truth for *how to keep it working*.

## Overview

This plugin contributes, via the `led_ticker.plugins` entry point, a calendar feature set that
used to live in led-ticker core (`type = "calendar"`):

- `calendar.events` — upcoming events from any `.ics` feed; three layouts (`agenda`, `next`,
  `two_row`). Always a Container: a background task polls the feed and populates `feed_stories`;
  the display loop re-reads the list on every pass, so updates surface within one cycle without
  restarting.

The entry-point name `calendar` is the plugin namespace, so the config `type` is `calendar.events`
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

Python **3.14+** only.

## Package layout

```
src/led_ticker_calendar/
  __init__.py   # register(api) entry point — the only place names are registered
  calendar.py   # calendar.events widget (Calendar); all three layouts live here
```

`calendar.py` was moved **verbatim** from led-ticker core and its imports rewritten to use only
`led_ticker.plugin`. Splitting it into separate `ics_fetch.py` / `format.py` / `render.py`
modules is a deferred follow-up — do not split it as a side-effect of unrelated changes.

`register(api)` (in `__init__.py`):

```python
def register(api):
    api.widget("events")(Calendar)
```

## Load-bearing invariants

Each rule must hold when modifying the named area.

**Import only the public surface** — every `led_ticker` import MUST come from `led_ticker.plugin`,
never `led_ticker.<internal>`. Enforced by `tests/test_import_purity.py`, which AST-walks every
source file (catches `from`-imports *and* `import led_ticker.x` forms, not just a text grep).
Intra-package imports (`from led_ticker_calendar.calendar import …`) are fine. If you need a core
symbol that isn't on `led_ticker.plugin.__all__`, that's a core API change — raise it upstream,
don't reach around the surface.

**Python 3.14 / PEP 649** — no `from __future__ import annotations` anywhere (same rule as core).
Bare `tuple[int, int, int]` annotations are fine.

**`validate_config()` contract** (`Calendar.validate_config`, `calendar.py`) — a classmethod run
pre-coercion by the engine's `validate_widget_cfg`. It **returns `list[str]`** (does NOT raise);
the engine turns any returned message into a pre-flight `ValueError`. It validates:

1. `ics_url` — required, non-empty string; placeholder-detection (`PASTE`/`YOUR_`/`_HERE`
   tokens) catches unfilled template values with an actionable error.
2. `layout` — must be `"agenda"`, `"next"`, or `"two_row"`.
3. `timezone` — must be a valid IANA name (checked via `ZoneInfo()`).
4. `filter` / `highlight` — must be lists of strings.
5. `max_events` / `lookahead_days` — non-negative integers; `lookahead_days` capped at 366.
6. `time_format` — string; either `"12h"`, `"24h"`, or a `strftime` template containing `%`.
7. `top_row_height` — positive integer when set.
8. `top_text_y_offset` / `bottom_text_y_offset` — integers when set.

**`validate_config_warnings()` contract** — a classmethod returning advisory warning strings;
never raises. Requires core API version ≥ (1, 1) for the `ValidationContext` argument. The three
checks are:

1. **Local `.ics` path existence** — warns when a `file://` or bare-path `ics_url` doesn't
   exist on disk at validate time (network feeds are never path-checked).
2. **Two-row font-fit** — warns when the font's logical line-height exceeds the per-row band
   height. In core these were hard ERRORS; here they are WARNINGS. The runtime
   `TwoRowMessage.draw` still hard-raises on a bad fit, so correctness is preserved.
3. **Two-row held-top overflow** — warns when the widest possible day+time string would overflow
   the logical canvas width. Only checked for `"12h"` and `"24h"` formats; custom `strftime`
   templates are skipped (unknown width).

These warnings are surfaced by `led-ticker validate` and do not block startup.

**Container invariant** — `Calendar.feed_stories: list[Widget]` is rebuilt by the background
`update()` task. The engine pushes the widget AS ITSELF into `Ticker.monitors` (not pre-expanded)
and re-reads `feed_stories` via `_expand_sources` on every pass. Never snapshot or cache
`feed_stories` at section-build time — that was the longboi stale-display bug.

**`two_row` font substitution** — at runtime, when `layout = "two_row"` and the resolved font is
`FONT_DEFAULT` (6×12), the widget silently substitutes `FONT_SMALL` (5×8) because 6×12 is too
tall for any split-row band. `validate_config_warnings._warn_two_row_band_fit` mirrors this
substitution so validate matches runtime. Don't remove the substitution without updating both.

## Sharp edges / Gotchas

**`strftime` time formats bypass the overflow warning** — `_warn_two_row_held_top_overflow` only
runs for `"12h"` / `"24h"` (known worst-case widths). Custom `strftime` templates are skipped
with an early return. If a user sets a pathologically wide format (e.g. a full weekday name),
validate will not warn — the runtime display will clip silently.

**Local `file://` paths and Docker** — the `.ics` file must be present inside the container at
the path given. Mount it in `compose.yaml` (e.g. `./cal.ics:/code/cal.ics:ro`) and set
`ics_url = "file:///code/cal.ics"`. The validate warning about a missing path is a build-time
check against the host path; the Docker-mounted path is only visible at container runtime.

**`ics_url` is the credential** — for Google and iCloud, the secret address IS the access
credential. `config/config.toml` is gitignored for exactly this reason; do not commit it to a
public repo.

## Tests / CI

`uv run pytest -q` runs the suite (`tests/`):

- `test_import_purity.py` — AST tripwire (public-surface-only). Treat a failure as a contract
  violation, not a test to relax.
- `test_smoke.py` — loads the plugin through led-ticker's real plugin loader and asserts
  `calendar.events` registers under the `calendar.*` namespace (entry-point wiring guard).
- `test_calendar.py` / `test_calendar_validate.py` / `test_calendar_next_selection.py` /
  `test_calendar_tz_invariant.py` / `test_calendar_recurrence_cost.py` /
  `test_calendar_corpus.py` — behavior, rendering, and validation coverage.

CI (`.github/workflows/ci.yml`): checks out this repo + led-ticker as siblings (deploy key),
Python 3.14, `uv sync --extra dev`, then `ruff check src tests` and `pytest -q`.

## Adding to the plugin

Register the class in `register()` in `__init__.py` (`api.widget`); it becomes `calendar.<name>`.
Import any core dependency from `led_ticker.plugin` only, and keep the import-purity test green.
