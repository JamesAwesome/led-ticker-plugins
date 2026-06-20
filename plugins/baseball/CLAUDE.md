# CLAUDE.md

Guidance for Claude Code when working in **led-ticker-baseball**, an external plugin for
[led-ticker](https://github.com/JamesAwesome/led-ticker).

`README.md` is the source of truth for the user-facing surface (widget options, team codes,
transition variants, install). This file keeps the **load-bearing invariants** a contributor
must respect, plus navigation aids. When a fact here and the README disagree about *how a
feature works*, the README wins; this file is the source of truth for *how to keep it working*.

## Overview

This plugin contributes, via the `led_ticker.plugins` entry point, an MLB feature set that
used to live in led-ticker core (`type = "mlb"`):

- `baseball.scores` — live/final/preview scores; `ticker`, `scoreboard`, or `two_row` layout.
- `baseball.standings` — scrolling division standings (top-N + tracked teams), offseason-aware.
- `baseball.promotions` — upcoming home-game promotions (giveaways/theme nights); today-first with highlight/filter/limit knobs and offseason-aware fallbacks.
- `baseball.statcast` — daily Statcast superlatives (longest HR, hardest hit,
  fastest/slowest pitch), league-wide or scoped to one team's players via an
  optional `team`; from Baseball Savant's day CSV, schedule-gated.
- `baseball.attendance` — ballpark attendance: league-wide daily superlatives
  (biggest/smallest crowd, fullest/emptiest park) or one team's game
  (attendance + fill % + venue + weather); schedule-gated.
- `baseball.roll` / `baseball.roll_reverse` / `baseball.roll_alternating` — a rolling-baseball
  sprite transition (lo-res 4-frame; procedural hi-res on the bigsign).
- `:baseball.ball:` — inline emoji (8×8 lo-res + 32×32 procedural hi-res).

The entry-point name `baseball` is the plugin namespace, so config `type`/transition/emoji
names are all `baseball.<name>` (see `register()` in `__init__.py`).

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
src/led_ticker_baseball/
  __init__.py     # register(api) entry point — the only place names are registered
  emoji.py        # :baseball.ball: — lo-res 8×8 (BALL) + procedural hi-res 32×32 (BALL_HIRES)
  teams.py        # shared MLB team colors/names/abbr tables, lazy palette, async resolve_team_id()
  scores.py       # baseball.scores widget (MLBScoreMonitor); ticker/scoreboard/two_row; game-state machine
  standings.py    # baseball.standings widget (MLBStandingsMonitor); top-N + tracked teams; offseason awareness
  promotions.py   # baseball.promotions widget (MLBPromotionsMonitor); home-game promos; today-first + fallback states
  statcast.py     # baseball.statcast widget (MLBStatcastMonitor); Savant day-CSV superlatives; schedule-gated
  attendance.py   # baseball.attendance widget (MLBAttendanceMonitor); league superlatives + team mode; schedule-gated
  transition.py   # baseball.roll* family; lo-res 4-frame + procedural hi-res rotation
```

All five widget modules import the shared tables from `teams.py` (no widget reaches into
another widget). `transition.py` reuses the hi-res sprite generator from
`emoji.py`. These sibling intra-package imports are allowed; see the import contract below.

`register(api)` (in `__init__.py`):

```python
def register(api):
    api.widget("scores")(MLBScoreMonitor)
    api.widget("standings")(MLBStandingsMonitor)
    api.widget("promotions")(MLBPromotionsMonitor)
    api.widget("statcast")(MLBStatcastMonitor)
    api.widget("attendance")(MLBAttendanceMonitor)
    api.transition("roll")(Baseball)
    api.transition("roll_reverse")(BaseballReverse)
    api.transition("roll_alternating")(BaseballAlternating)
    api.emoji("ball", BALL)
    api.hires_emoji("ball", BALL_HIRES)
```

## Load-bearing invariants

Each rule must hold when modifying the named area.

**Import only the public surface** — every `led_ticker` import MUST come from `led_ticker.plugin`,
never `led_ticker.<internal>`. Enforced by `tests/test_import_purity.py`, which AST-walks every
source file (catches `from`-imports *and* `import led_ticker.x` forms, not just a text grep).
Intra-package imports (`from led_ticker_baseball.teams import …`) are fine. If you need a core
symbol that isn't on `led_ticker.plugin.__all__`, that's a core API change — raise it upstream,
don't reach around the surface.

**Python 3.14 / PEP 649** — no `from __future__ import annotations` anywhere (same rule as core).
Bare `tuple[int, int, int]` annotations are fine. `ColorTuple` is defined locally in `teams.py`
because it isn't on the public surface.

**`validate_config()` contract** (`MLBScoreMonitor.validate_config`, `scores.py`) — a classmethod
run pre-coercion by the engine's `validate_widget_cfg`. It **returns `list[str]`** (does NOT raise);
the engine turns any returned message into a pre-flight `ValueError`. It reproduces the two
guardrails core formerly applied to `type = "mlb"`: (1) `layout` must be in
`("ticker", "scoreboard", "two_row")` (`_MLB_VALID_LAYOUTS`); (2) the per-row `top_*` knobs
(`_TWO_ROW_ONLY`) are rejected by name when `layout != "two_row"` — named, not silently ignored,
so stale configs surface.

**`teams.py` lazy palette is PEP 562** — module-level `__getattr__` exports the named colors
(`WIN_COLOR`/`LOSS_COLOR`/`LIVE_COLOR`/`CHALLENGE_COLOR`) so external code can
`from led_ticker_baseball.teams import WIN_COLOR`. **In-module use must call `_team_palette(name)`
directly** — PEP 562 `__getattr__` does NOT fire for bare-name lookups within the defining module.

**Team color lifting** (`_lift_color`, `teams.py`) — dark team colors are scaled so the peak RGB
channel is ≥ 120, keeping them legible on-panel at low brightness; hue/saturation are preserved
and already-bright teams are unchanged. Don't bypass it when adding team colors.

**Hi-res transition dispatch** — the `baseball.roll*` classes set `scale_switch_at = SNAP_THRESHOLD`
and branch on `is_scaled(canvas)` (bigsign / `ScaledCanvas`). The hi-res path paints physical LEDs
via `unwrap_to_real(canvas)` and snaps to incoming at `SNAP_THRESHOLD`. Sprite frames are 8
rotations at 45° (90° reads as alternating; 22.5° reads chaotic on small panels) and are
`@functools.cache`'d — geometry is deterministic. `is_scaled` / `unwrap_to_real` / `snap_reset` /
`SNAP_THRESHOLD` all come from `led_ticker.plugin`; don't hand-copy them back in.

**emoji ↔ transition coupling** — `transition.py` imports `_generate_baseball_hires` from
`emoji.py` **inside a function**, not at module top, to avoid a circular import. Keep it lazy.

## Tests / CI

`uv run pytest -q` runs the suite (`tests/`):

- `test_import_purity.py` — the AST tripwire (public-surface-only). Treat a failure as a contract
  violation, not a test to relax.
- `test_smoke.py` — loads the plugin through led-ticker's real plugin loader and asserts the
  widgets/transitions/emoji register under the `baseball.*` namespace (entry-point wiring guard).
- `test_scores.py` / `test_scoreboard.py` / `test_standings.py` / `test_promotions.py` /
  `test_statcast.py` / `test_attendance.py` / `test_transition.py` / `test_emoji.py` / `test_lazy_palette.py` — behavior + rendering coverage.

CI (`.github/workflows/ci.yml`): checks out this repo + led-ticker as siblings (deploy key),
Python 3.14, `uv sync --extra dev`, then `ruff check src tests` and `pytest -q`.

## Adding to the plugin

Register the class in `register()` in `__init__.py` (`api.widget` / `api.transition` /
`api.emoji` / `api.hires_emoji`); it becomes `baseball.<name>`. Import any core dependency from
`led_ticker.plugin` only, and keep the import-purity test green.
