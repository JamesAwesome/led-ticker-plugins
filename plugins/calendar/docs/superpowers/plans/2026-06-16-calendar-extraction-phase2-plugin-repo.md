# Calendar Extraction — Phase 2: led-ticker-calendar Plugin Repo — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the `led-ticker-calendar` plugin repo — scaffolded like `led-ticker-baseball`, with the calendar widget moved verbatim, its tests/fixtures ported, and its validation re-homed into `validate_config` (errors) + `validate_config_warnings` (advisory, using the Phase-1 `ValidationContext` channel) — green in CI, coexisting with core's `calendar` (the namespaced `calendar.events` type does not collide; core removal is Phase 3).

**Architecture:** A new uv/hatchling package `led_ticker_calendar` contributing one widget via the `led_ticker.plugins` entry point (namespace `calendar`, widget `events` → TOML `type = "calendar.events"`). Source imports ONLY from `led_ticker.plugin`. The widget module is moved verbatim from core (1162 lines) with import lines rewritten and the `@register` decorator dropped. Validation re-homes: field/type errors stay in the existing `validate_config`; the three core `validate.py` calendar rules (ics-path existence, held-top-overflow, two_row font-fit) move into a new `validate_config_warnings(cls, cfg, ctx)` — all emitted as warnings (the font-fit one downgrades from a core error to a warning; runtime `TwoRowMessage.draw` still hard-raises, so correctness is preserved).

**Tech Stack:** Python 3.14, uv, hatchling, pytest (`asyncio_mode=auto`, `pythonpath=["../led-ticker/tests/stubs"]`), ruff, pyright. Depends on `led-ticker` ≥ API (1,1) (Phase 1, merged to core `main`).

---

## Prerequisites

- Phase 1 (PR #222) is **merged to led-ticker `main`** — `led_ticker.plugin.ValidationContext`, `API_VERSION == (1,1)`, and the `validate_config_warnings` channel exist. Confirmed before starting.
- The sibling checkout `/Users/james/projects/github/jamesawesome/led-ticker` is on `main` with Phase 1 (so `[tool.uv.sources] led-ticker = {path="../led-ticker", editable=true}` resolves with the new surface).
- Work on branch `feat/extract-calendar-plugin` in `/Users/james/projects/github/jamesawesome/led-ticker-calendar`. NEVER commit to `main`.
- The `LED_TICKER_DEPLOY_KEY` secret already exists on the GitHub repo (CI sibling-checkout of private led-ticker).

## Reference sources (read, don't guess)

The model to mirror is `/Users/james/projects/github/jamesawesome/led-ticker-baseball` (sibling). The widget + tests + validation rules to move live in `/Users/james/projects/github/jamesawesome/led-ticker` (core, on `main`):
- Widget: `src/led_ticker/widgets/calendar.py`
- Tests: `tests/test_widgets/test_calendar*.py` (6 files) + `tests/fixtures/calendar_sample.ics` + `tests/fixtures/calendar_corpus/*.ics` (10 files)
- Core validation rules to re-home: `_check_calendar_ics_paths` (rule 54), and the `wtype == "calendar"` branches inside `_check_band_layout` (rule 22) and `_check_held_top_text_overflow` in `src/led_ticker/validate.py`.

## File Structure (target)

```
led-ticker-calendar/
  pyproject.toml          .gitignore   .pre-commit-config.yaml   Makefile
  .github/workflows/ci.yml   .github/dependabot.yml
  README.md   CLAUDE.md
  config/config.calendar_smoketest.toml
  src/led_ticker_calendar/__init__.py     # register(api): api.widget("events")(Calendar)
  src/led_ticker_calendar/calendar.py     # verbatim widget; imports -> led_ticker.plugin
  tests/conftest.py  tests/test_smoke.py  tests/test_import_purity.py
  tests/test_calendar*.py (ported)   tests/fixtures/...
```

---

### Task 1: Scaffold the package (mirror baseball)

**Files (all create):** `pyproject.toml`, `.gitignore`, `.pre-commit-config.yaml`, `Makefile`, `.github/workflows/ci.yml`, `.github/dependabot.yml`, `src/led_ticker_calendar/__init__.py`.

- [ ] **Step 1: Copy baseball's scaffold files, adapting names.** Read each baseball file and write the calendar equivalent:
  - `pyproject.toml`: identical to baseball's EXCEPT — `name = "led-ticker-calendar"`; `description = "Calendar (.ics) agenda/next/two_row widget for led-ticker."`; `dependencies = ["led-ticker", "aiohttp", "icalendar>=6.1", "recurring-ical-events>=3.0"]` (NOT pillow); `[project.entry-points."led_ticker.plugins"]` → `calendar = "led_ticker_calendar:register"`; `[tool.hatch.build.targets.wheel] packages = ["src/led_ticker_calendar"]`; keep baseball's `[tool.uv.sources]`, `[tool.pytest.ini_options]` (asyncio_mode=auto, pythonpath=["../led-ticker/tests/stubs"]), ruff, pyright (extraPaths=["../led-ticker/tests/stubs"]), `[tool.coverage.report] fail_under = 90` verbatim.
  - `.gitignore`, `.pre-commit-config.yaml`, `.github/dependabot.yml`: copy baseball's verbatim.
  - `Makefile`: copy baseball's verbatim (dev/test/lint/format/typecheck targets).
  - `.github/workflows/ci.yml`: copy baseball's verbatim but replace every `led-ticker-baseball` path/label with `led-ticker-calendar`.

- [ ] **Step 2: Write the `register` entry point.** Create `src/led_ticker_calendar/__init__.py`:

```python
"""led-ticker-calendar: calendar (.ics) agenda/next/two_row widget, contributed
via the ``led_ticker.plugins`` entry point.

The entry-point name ``calendar`` is the plugin namespace, so the widget is
``type = "calendar.events"`` in config.toml.
"""

from led_ticker_calendar.calendar import Calendar


def register(api):
    api.widget("events")(Calendar)
```

(This will not import cleanly until Task 2 creates `calendar.py`; that's fine — Task 2 makes it importable.)

- [ ] **Step 3: Verify the environment resolves.** Run from the repo root:

Run: `uv sync --extra dev`
Expected: resolves and installs (led-ticker editable from ../led-ticker, plus icalendar / recurring-ical-events). If it fails to find the new `ValidationContext` surface, STOP — the sibling led-ticker is not on a Phase-1 `main`; report BLOCKED.

- [ ] **Step 4: Commit.**

```bash
git add -A && git commit --no-verify -m "chore: scaffold led-ticker-calendar package (mirror baseball)"
```

---

### Task 2: Move the widget verbatim + rewrite imports

**Files:**
- Create: `src/led_ticker_calendar/calendar.py` (copied from core)

- [ ] **Step 1: Copy the widget file verbatim.**

Run: `cp /Users/james/projects/github/jamesawesome/led-ticker/src/led_ticker/widgets/calendar.py /Users/james/projects/github/jamesawesome/led-ticker-calendar/src/led_ticker_calendar/calendar.py`

- [ ] **Step 2: Rewrite the `led_ticker.*` import block to `led_ticker.plugin`.** The current core import block (lines ~23–34) is:

```python
from led_ticker._types import Canvas, DrawResult, Font
from led_ticker.color_providers import ColorProvider, as_color_provider
from led_ticker.colors import DEFAULT_COLOR, make_color
from led_ticker.drawing import compute_baseline, compute_cursor
from led_ticker.fonts import FONT_DEFAULT, FONT_SMALL
from led_ticker.pixel_emoji import count_text_chars, draw_with_emoji, measure_width
from led_ticker.widget import Widget, run_monitor_loop, spawn_tracked
from led_ticker.widgets import register
from led_ticker.widgets._frame_aware import FrameAwareBase
from led_ticker.widgets.clock import format_clock
from led_ticker.widgets.message import TickerMessage
from led_ticker.widgets.two_row import TwoRowMessage
```

Replace that ENTIRE block with the following (all names are on the public surface; `DEFAULT_COLOR` is reached via the public `colors` module since it is not a top-level export; `register` is dropped):

```python
from led_ticker.plugin import (
    Canvas,
    ColorProvider,
    DrawResult,
    FONT_DEFAULT,
    FONT_SMALL,
    Font,
    FrameAwareBase,
    TickerMessage,
    TwoRowMessage,
    Widget,
    as_color_provider,
    colors,
    compute_baseline,
    compute_cursor,
    count_text_chars,
    draw_with_emoji,
    format_clock,
    make_color,
    measure_width,
    run_monitor_loop,
    spawn_tracked,
)

DEFAULT_COLOR = colors.DEFAULT_COLOR
```

> If `from led_ticker.plugin import colors` then `colors.DEFAULT_COLOR` does not resolve (inspect `led_ticker/plugin.py` `colors` export), instead `from led_ticker.plugin import colors` and replace each in-file use of `DEFAULT_COLOR` with `colors.DEFAULT_COLOR` and drop the module-level alias. Verify `make_color`, `as_color_provider`, `format_clock`, `count_text_chars`, `measure_width`, `draw_with_emoji`, `compute_baseline`, `compute_cursor`, `FrameAwareBase`, `TickerMessage`, `TwoRowMessage`, `run_monitor_loop`, `spawn_tracked`, `Canvas`, `DrawResult`, `Font`, `FONT_DEFAULT`, `FONT_SMALL` are all in `led_ticker.plugin.__all__` (they are, per the Phase-1 surface) — if any is missing, report BLOCKED naming it.

- [ ] **Step 3: Remove the `@register("calendar")` decorator.** Find the decorator line directly above `class Calendar:` and delete it. (Registration now happens via `api.widget("events")` in `__init__.py`.) Leave the `class Calendar:` definition otherwise untouched.

- [ ] **Step 4: Confirm the package imports + registers.**

Run: `uv run python -c "import led_ticker_calendar; from led_ticker_calendar.calendar import Calendar; print(Calendar.__name__)"`
Expected: prints `Calendar`, no ImportError.

Run: `uv run --extra dev ruff check src/led_ticker_calendar` and fix any unused-import lint (e.g. if a name in the rewritten block is genuinely unused, drop it).
Run: `uv run pyright src/led_ticker_calendar` — expect clean (or only pre-existing-style notes; report any hard errors).

- [ ] **Step 5: Commit.**

```bash
git add -A && git commit --no-verify -m "feat: move calendar widget verbatim into the plugin (imports via led_ticker.plugin)"
```

---

### Task 3: Add smoke + import-purity tests

**Files (create):** `tests/conftest.py`, `tests/test_import_purity.py`, `tests/test_smoke.py`.

- [ ] **Step 1: conftest.py** — copy baseball's `tests/conftest.py` verbatim (the `canvas` + `make_widget` mock fixtures; the calendar tests use `canvas`).

- [ ] **Step 2: test_import_purity.py** — copy baseball's `tests/test_import_purity.py` verbatim but change `SRC = ... / "led_ticker_baseball"` to `"led_ticker_calendar"`. (Asserts every `led_ticker.*` import in `src/` is exactly `led_ticker.plugin`.)

- [ ] **Step 3: test_smoke.py** — adapt baseball's to the calendar surface:

```python
from led_ticker import _plugin_loader as L


def test_entry_point_registers_calendar_namespace():
    L.reset_plugins()
    try:
        result = L.load_plugins(None, entry_points_enabled=True)
        loaded = {info.namespace for info in result.loaded}
        assert "calendar" in loaded, f"calendar plugin not discovered: {result}"

        from led_ticker.widgets import get_widget_class

        assert get_widget_class("calendar.events") is not None
    finally:
        L.reset_plugins()
```

- [ ] **Step 4: Run the three new tests.**

Run: `PYTHONPATH=../led-ticker/tests/stubs uv run pytest tests/test_smoke.py tests/test_import_purity.py -q`
Expected: PASS. (test_import_purity confirms the Task-2 import rewrite left no `led_ticker.<internal>` reach; test_smoke confirms the entry point registers `calendar.events`.)

> If `test_import_purity` fails, a Task-2 import was missed — fix the offending import in `src/led_ticker_calendar/calendar.py` to come from `led_ticker.plugin`, then re-run.

- [ ] **Step 5: Commit.**

```bash
git add -A && git commit --no-verify -m "test: smoke + import-purity tripwires"
```

---

### Task 4: Port the widget-logic tests + fixtures

These test the widget's pure logic (parsing, selection, formatting, tz, recurrence, corpus, next-selection, two-tone). They import widget internals and must be re-pointed at `led_ticker_calendar.calendar`.

**Files:**
- Create (copy + edit): `tests/test_calendar.py`, `tests/test_calendar_corpus.py`, `tests/test_calendar_next_selection.py`, `tests/test_calendar_recurrence_cost.py`, `tests/test_calendar_tz_invariant.py`
- Create (copy): `tests/fixtures/calendar_sample.ics`, `tests/fixtures/calendar_corpus/*.ics` (10 files)

(NOTE: `test_calendar_validate_contract.py` is handled in Task 5, not here — it tests validation.)

- [ ] **Step 1: Copy the fixtures.**

```bash
mkdir -p tests/fixtures/calendar_corpus
cp /Users/james/projects/github/jamesawesome/led-ticker/tests/fixtures/calendar_sample.ics tests/fixtures/
cp /Users/james/projects/github/jamesawesome/led-ticker/tests/fixtures/calendar_corpus/*.ics tests/fixtures/calendar_corpus/
```

- [ ] **Step 2: Copy the 5 logic test files and rewrite their imports.** For each of the five files, copy it from `../led-ticker/tests/test_widgets/<name>` to `tests/<name>`, then:
  - Replace `from led_ticker.widgets.calendar import ...` → `from led_ticker_calendar.calendar import ...`.
  - Leave imports of OTHER core modules as-is (e.g. `from led_ticker.widgets.two_row import TwoRowMessage`, `from led_ticker.fonts import ...`) — test code is not bound by import purity, and those are stable core APIs.
  - Fix any fixture path references: if a test reads `tests/fixtures/...` via a path relative to the core repo, ensure it resolves relative to THIS repo's `tests/fixtures/` (most use `Path(__file__).parent / "fixtures" / ...` which is portable; if any hardcodes `test_widgets/`, adjust).
  - Do NOT change `type = "calendar"` strings that appear ONLY as inputs to `Calendar(...)` / `Calendar.validate_config(...)` direct calls — those construct the class directly and don't go through the registry (the `type` key is ignored by the constructor). Only registry-driven lookups need `calendar.events`, and those live in Task 5 / test_smoke.

- [ ] **Step 3: Run the ported logic tests.**

Run: `PYTHONPATH=../led-ticker/tests/stubs uv run pytest tests/test_calendar.py tests/test_calendar_corpus.py tests/test_calendar_next_selection.py tests/test_calendar_recurrence_cost.py tests/test_calendar_tz_invariant.py -q`
Expected: PASS (same count as in core). 

> If a test fails on a registry lookup (`get_widget_class("calendar")`) or a core-static-validator call, it belongs in Task 5 (validation) — note it and move that specific test there rather than forcing it green here. If it fails on a fixture path, fix the path. If it fails importing a name no longer at `led_ticker_calendar.calendar`, that name was dropped in the Task-2 rewrite — restore it.

- [ ] **Step 4: Commit.**

```bash
git add -A && git commit --no-verify -m "test: port calendar widget-logic tests + fixtures"
```

---

### Task 5: Re-home validation (errors stay; warnings via the Phase-1 channel)

The widget's `validate_config` (field/type errors) already moved with the widget in Task 2 — confirm it's intact. This task ADDS `validate_config_warnings` porting the three core rules as warnings, and ports the validation-contract test.

**Files:**
- Modify: `src/led_ticker_calendar/calendar.py` (add `validate_config_warnings` classmethod on `Calendar`)
- Create: `tests/test_calendar_validate.py` (ported + adapted from core's `test_calendar_validate_contract.py`)

- [ ] **Step 1: Confirm `validate_config` is intact** in the moved widget (it validates `ics_url` required/placeholder, `layout`, `timezone`, `filter`/`highlight`, `max_events`/`lookahead_days`, `time_format`, two_row knobs). No change needed; just verify it survived the move.

- [ ] **Step 2: Add `validate_config_warnings`.** Read these three functions in `../led-ticker/src/led_ticker/validate.py` and port their calendar-specific logic into a single new classmethod on `Calendar`:
  1. `_check_calendar_ics_paths` (rule 54) — local-file existence of `ics_url` resolved against `ctx.config_dir` (skip `http(s)`/`webcal(s)` schemes; handle `file://` and `~`). Emit a warning string if the resolved path is missing.
  2. The `wtype == "calendar"` branch of `_check_band_layout` (rule 22) — for `layout == "two_row"`, mirror the FONT_DEFAULT→FONT_SMALL substitution and the band-fit check; emit a warning string if an explicitly-configured font's line-height exceeds the resolved band height. (Downgraded from core's error to a warning — runtime still hard-raises.)
  3. The `wtype == "calendar"` branch of `_check_held_top_text_overflow` — for `layout == "two_row"`, measure the representative widest held-row phrase (`"Tomorrow 23:59"` for 24h, `"Tomorrow 12:00 PM"` for 12h; skip custom `%`-format), and emit a warning string if it exceeds the logical canvas width derived from `ctx`.

  The classmethod signature and shape:

```python
@classmethod
def validate_config_warnings(cls, cfg, ctx):
    """Advisory preflight warnings (surfaced by ``led-ticker validate``).

    ``ctx`` is a ``led_ticker.plugin.ValidationContext`` (scale, content_height,
    panel_width, panel_height, config_dir). Returns a list of warning strings;
    never raises (the core runner is error-isolated regardless).
    """
    warnings = []
    # 1. ics_url local-file existence (ported from core rule 54)
    # 2. two_row font-fit (ported from core _check_band_layout calendar branch)
    # 3. two_row held-top overflow (ported from _check_held_top_text_overflow)
    return warnings
```

  Use the public helpers from `led_ticker.plugin` for geometry/measurement: `resolve_font`, `FONT_DEFAULT`, `FONT_SMALL`, `get_text_width` (or `measure_width`), `resolve_band_heights`, `ScaledCanvas`/`is_scaled` as needed (confirm each is in `led_ticker.plugin.__all__`; the Phase-1 surface includes `get_text_width`, `resolve_font`, `resolve_band_heights`, `ScaledCanvas`, `measure_width`, `FONT_DEFAULT`, `FONT_SMALL`). For the canvas-width derivation, build a `ScaledCanvas(SimpleNamespace(width=ctx.panel_width, height=ctx.panel_height), scale=ctx.scale, content_height=ctx.content_height)` exactly as the core `_check_held_top_text_overflow` does. Keep `from led_ticker.plugin import ...` (no internal reach — import-purity tripwire will catch a slip).

- [ ] **Step 3: Write the validation tests.** Adapt core's `test_calendar_validate_contract.py` into `tests/test_calendar_validate.py`:
  - Keep the direct `Calendar.validate_config({...})` error assertions (they test the classmethod directly — port verbatim, repointing the import to `led_ticker_calendar.calendar`).
  - ADD tests for `validate_config_warnings`: construct a `led_ticker.plugin.ValidationContext` (e.g. a narrow bigsign-like `scale=4, content_height=16, panel_width=256, panel_height=64`) and assert the expected warning fires for (a) a missing local `ics_url` path, (b) a too-tall explicit font on `layout="two_row"`, (c) a held-row overflow on a narrow logical canvas; and assert NO warning for the clean default case and for `http(s)` urls.
  - Drop any core test that asserted on core's static-validator `ValidationIssue` objects / rule numbers for calendar (those rules live in core only until Phase 3 removal; the plugin's contract is the returned warning strings, not core's `ValidationIssue`).

- [ ] **Step 4: Run validation tests.**

Run: `PYTHONPATH=../led-ticker/tests/stubs uv run pytest tests/test_calendar_validate.py -q`
Expected: PASS.

- [ ] **Step 5: Run the FULL plugin suite + lint + typecheck.**

Run: `PYTHONPATH=../led-ticker/tests/stubs uv run pytest --cov=src --cov-report=term-missing -q`
Expected: PASS, coverage ≥ 90% (the `fail_under` gate).
Run: `uv run --extra dev ruff check src tests` → clean.
Run: `uv run pyright src` → clean.

> If coverage < 90%, identify the uncovered widget branches (likely a formatting or error-path branch) and add targeted tests — do not lower `fail_under`.

- [ ] **Step 6: Commit.**

```bash
git add -A && git commit --no-verify -m "feat: re-home calendar validation (errors + validate_config_warnings)"
```

---

### Task 6: README, CLAUDE.md, example config

**Files (create):** `README.md`, `CLAUDE.md`, `config/config.calendar_smoketest.toml`.

- [ ] **Step 1: README.md** — user-facing. Mirror baseball's README structure (title, what it provides, install via `requirements-plugins.txt`, a config example using `type = "calendar.events"`, the field table for `ics_url`/`layout`/`max_events`/`lookahead_days`/`time_format`/`filter`/`highlight`/`timezone`/two_row knobs/colors, a Development section explaining the `../led-ticker` editable sibling + `PYTHONPATH` for tests). Pull field semantics from core's docs page `../led-ticker/docs/content-source/widgets/calendar.md` and the widget's `validate_config`.

- [ ] **Step 2: CLAUDE.md** — contributor invariants. Mirror baseball's CLAUDE.md: import-purity rule (`led_ticker.plugin` only), entry-point namespace (`calendar` → `calendar.events`), the `validate_config` (errors) vs `validate_config_warnings` (advisory, needs API ≥ (1,1)) split, the "verbatim move — splitting calendar.py is a deferred follow-up" note, test invocation (`PYTHONPATH=../led-ticker/tests/stubs`), and the Python-3.14/no-`from __future__` rule.

- [ ] **Step 3: config/config.calendar_smoketest.toml** — copy `../led-ticker/config/config.calendar_smoketest.toml` and change `type = "calendar"` → `type = "calendar.events"`. (Used for manual render/smoke checks.)

- [ ] **Step 4: Commit.**

```bash
git add -A && git commit --no-verify -m "docs: README + CLAUDE.md + smoketest config"
```

---

### Task 7: Push + open PR; verify CI green

- [ ] **Step 1: Push the branch.**

```bash
git push --no-verify -u origin feat/extract-calendar-plugin
```

- [ ] **Step 2: Open the PR** against `main` of `JamesAwesome/led-ticker-calendar` with a summary (scaffold + verbatim widget + ported tests + re-homed validation; coexists with core calendar; core removal is Phase 3) and a Test Plan checklist (pytest ≥90% cov, ruff, pyright, smoke registers `calendar.events`, import-purity).

- [ ] **Step 3: Watch CI to green.** CI checks out led-ticker `main` as the sibling (needs Phase 1 — merged). Confirm lint / typecheck / test all pass. If `test` fails on a missing `led_ticker.plugin` name, Phase 1 is not on the led-ticker default branch CI resolves — investigate before merging.

- [ ] **Step 4: STOP — do not merge.** Report the PR URL and CI status to the controller. Per project rule, merge only on explicit user go-ahead.

---

## Self-Review

**Spec coverage (Phase-2 portion of the design doc):**
- New plugin repo mirroring baseball, namespace `calendar`, type `calendar.events` → Tasks 1–2, 6. ✓
- Verbatim widget move, imports → `led_ticker.plugin`, drop `@register` → Task 2. ✓
- Move all tests + fixtures → Tasks 3 (smoke/purity), 4 (logic), 5 (validation). ✓
- Re-home validation: errors in `validate_config`, advisory in `validate_config_warnings` → Task 5. ✓ (Documented downgrade of the font-fit rule from error→warning, in Architecture + Task 5 Step 2.)
- icalendar + recurring-ical-events as plugin deps (not core) → Task 1. ✓
- CI sibling-checkout w/ deploy key, ≥90% cov → Tasks 1, 5, 7. ✓
- Coexists with core calendar (no collision) → stated; core removal explicitly deferred to Phase 3. ✓

**Placeholder scan:** The `>` callouts are verification/triage instructions with concrete fallbacks (confirm a name is on the public surface; move a registry-dependent test to Task 5; fix a fixture path), not unfinished work. Task 5 Step 2 intentionally references the core source to port rather than re-pasting ~150 lines — the source is available in the sibling checkout and the transformation (config-walk→ctx, ValidationIssue→warning string, error→warning) is specified.

**Type/name consistency:** Entry point `calendar = "led_ticker_calendar:register"`; `register(api)` calls `api.widget("events")(Calendar)`; TOML type `calendar.events`; package `led_ticker_calendar`; module `led_ticker_calendar.calendar`; class `Calendar`. `validate_config` (errors) and `validate_config_warnings(cls, cfg, ctx)` (warnings, ctx = `led_ticker.plugin.ValidationContext`) are consistent across Tasks 2, 5 and the Phase-1 channel.
