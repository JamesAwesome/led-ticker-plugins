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

- `baseball.scores` — live/final/preview scores; `layout = "auto"` (default), `"ticker"`, `"scoreboard"`, or `"two_row"`. `auto` resolves per-sign (`layouts.resolve_layout`); explicit names mean what they say, with ONE width-fit guard: explicit `"scoreboard"` at scale>1 on a panel narrower than 400 physical px (bigsign) degrades to `"two_row"` instead — the physical scoreboard's hardcoded anchors assume >=400px and would otherwise silently clip the whole home side (see `layouts/resolve_layout`'s docstring). Scale 1 renders through the legacy text-glyph classes (`_scoreboard.py`, `_two_row.py`); scale>1 dispatches through `MLBGameCard` (`_card.py`) to the new physical (procedural pixel-art) renderers in `layouts/`.
- `baseball.standings` — MLB standings for the divisions of your tracked `teams`; `layout = "auto"` (default), `"ticker"`, or `"board"`. `ticker` is the original scrolling-rows behavior (top-N + tracked teams, everywhere); `auto`/`board` build one held physical division board per tracked division at scale>1, degrading to one legacy scrolling row per section visit at scale<=1 (same shape as `ticker`'s rows). Offseason-aware.
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

`led-ticker-core` resolves from PyPI (`>=2.1`) like any other dependency — no sibling
checkout, no `[tool.uv.sources]`, no deploy key. (To co-develop against an unreleased
engine, add it editable on top: `uv pip install -e ../../../led-ticker`, assuming led-ticker and led-ticker-plugins are checked out as siblings.) Tests
that need a real headless canvas obtain one via `HeadlessBackend(...).create_canvas()` from
`led_ticker.plugin` (the shipped headless backend in led-ticker-core ≥ 2.1); there is no
rgbmatrix stub on the pytest path anymore.

```bash
uv sync --extra dev          # install deps (led-ticker-core from PyPI)
uv run pytest -q             # full suite (asyncio_mode = "auto")
uv run ruff check src tests  # lint — run before pushing
```

Python **3.14+** only.

## Package layout

```
src/led_ticker_baseball/
  __init__.py     # register(api) entry point — the only place names are registered
  emoji.py        # :baseball.ball: — lo-res 8×8 (BALL) + procedural hi-res 32×32 (BALL_HIRES)
  teams.py        # shared MLB team colors/names/abbr tables, lazy palette, async resolve_team_id(),
                  #   MLB_TEAM_CHIPS (30-team two-tone chip colors, lifted)
  scores.py       # baseball.scores widget (MLBScoreMonitor); layout="auto"/ticker/scoreboard/two_row;
                  #   game-state machine; builds MLBGameCard stories (update())
  _card.py        # MLBGameCard — the scale-dispatching story: scale 1 delegates to the legacy
                  #   classes below, scale>1 dispatches to layouts/
  _scoreboard.py  # MLBScoreboardMessage (legacy scale-1 scoreboard text renderer) + _build_game_message
  _two_row.py     # legacy scale-1 two_row text renderer
  _models.py      # GameInfo / SeriesInfo dataclasses + shared formatting helpers
  _palette.py     # semantic design-handoff palette (0-255 Color constants); one hue per data field
  _paint.py       # physical-pixel hi-res paint helpers for layouts/ (phys_wrap, hires, js_round, …)
  _primitives.py  # procedural pixel-art primitives (chip/diamond/pip/dash/series_dashes), ported
                  #   coordinate-for-coordinate from design/…dc.html
  layouts/        # new physical (scale>1) renderers: resolve_layout + crawl.py/scoreboard.py/two_row.py/standings_board.py
  standings.py    # baseball.standings widget (MLBStandingsMonitor); layout="auto"/ticker/board;
                  #   builds MLBStandingsBoard stories per division (update())
  _standings_card.py  # MLBStandingsBoard — the scale-dispatching story: scale>1 dispatches to
                      #   layouts/standings_board.py, scale<=1 forwards one legacy_rows[idx] per visit
  promotions.py   # baseball.promotions widget (MLBPromotionsMonitor); home-game promos; today-first + fallback states
  statcast.py     # baseball.statcast widget (MLBStatcastMonitor); Savant day-CSV superlatives; schedule-gated
  attendance.py   # baseball.attendance widget (MLBAttendanceMonitor); league superlatives + team mode; schedule-gated
  transition.py   # baseball.roll* family; lo-res 4-frame + procedural hi-res rotation
```

All widget modules import the shared tables from `teams.py` (no widget reaches into
another widget's private internals). `transition.py` reuses the hi-res sprite generator from
`emoji.py`. `_card.py` and `layouts/` import from `_palette.py`/`_paint.py`/`_primitives.py`.
These sibling intra-package imports are allowed; see the import contract below.

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
`("auto", "ticker", "scoreboard", "two_row")` (`_MLB_VALID_LAYOUTS`) — `"auto"` is the default
since the design uplift; (2) the per-row `top_*` knobs (`_TWO_ROW_ONLY`) are rejected by name
when `layout` isn't in `_TWO_ROW_CAPABLE_LAYOUTS = ("two_row", "auto")` — named, not silently
ignored, so stale configs surface. `"auto"` stays two-row-capable because it can resolve TO
`two_row` at draw time (`layouts.resolve_layout`); the config-load-time check can't know the
canvas yet, so it admits the superset and lets the resolved-layout mismatch (if any) surface at
draw time instead.

**`MLBGameCard` scale-dispatch contract** (`_card.py`) — the one story `scores.py`'s `update()`
builds per game, for every layout. `draw()` resolves `(cfg_layout, scale, real_width)` via
`layouts.resolve_layout` fresh on every call (flight pattern — hot-reloads/canvas swaps always
re-resolve), then: **scale <= 1 delegates unconditionally to the legacy classes**
(`_build_scoreboard_message`/`_build_two_row_message`/`_build_game_message`, cached on
`self._legacy` after first build) — unchanged smallsign behavior, byte-for-byte. **scale > 1
dispatches to the physical renderers** in `layouts/` (`render_crawl`/`render_scoreboard`/
`render_two_row`) and NEVER touches the legacy classes — `MLBScoreboardMessage.draw()` (with its
`_MIN_LOGICAL_WIDTH` geometry guard) is scale<=1-only code post-uplift; a bigsign/longboi running
`layout = "scoreboard"` cannot reach that guard (though `resolve_layout` now degrades an explicit `"scoreboard"` below 400 phys px to `"two_row"` before the card ever dispatches there — see the layout-table entry above). **Physical held layouts (`scoreboard`, `two_row` at scale > 1) return `cursor = canvas.width`** — the WRAPPER's LOGICAL width (`real.width // scale`), NOT `real.width`. The engine's hold-vs-scroll decision (`cursor_pos > canvas.width`, core `ticker.py`) compares against the wrapper's logical width, so returning `real.width` (a final-review Finding-1 bug) always took the scroll branch — the panel showed a frozen card while the engine "scrolled" nowhere for the padding-to-real-width distance, then held a SECOND time. The `ticker` layout SCROLLS on every sign: at scale 1 the card forwards the legacy `SegmentMessage`'s scroll cursor unchanged (smallsign behavior is pre-uplift identical); at scale > 1 `render_crawl` treats `cursor_pos` as LOGICAL throughout (matching the engine's own units) — it paints at physical `x = cursor_pos * scale` and returns its advance ceil-divided back to logical (core's `get_text_width` hires convention) — and the card adds `self.padding` (also logical) on top for the engine's scroll loop. Mixing physical paint offsets with the engine's logical cursor arithmetic here was final-review Finding 2 (over-scrolled past flush-right by `real.width - logical.width`). Never 'fix' the legacy ticker to return `canvas.width`/`real.width` — that would freeze smallsign scrolling (scale 1 has no wrapper; its cursor contract is the legacy `SegmentMessage`'s own). Frame-aware hooks
(`advance_frame`/`pause_frame`/`resume_frame`/`reset_frame`) forward to the cached `_legacy`
story IN ADDITION TO the card's own base counters — don't drop either half when touching these.

**`MLBStandingsBoard` scale-dispatch contract** (`_standings_card.py`) — the one story
`standings.py`'s `update()` builds per tracked division, for `layout = "auto"`/`"board"`.
**scale > 1 is held**: dispatches to `layouts/standings_board.py`'s `render_standings_board` and
returns `cursor = canvas.width` — the WRAPPER's LOGICAL width, same held-cursor convention as
`MLBGameCard` (see above); returning `real.width` would take the scroll branch instead of holding.
**scale <= 1 forwards `legacy_rows[idx]` verbatim** — one pre-built legacy `SegmentMessage` per
division team (the same shape `_build_ticker_stories` builds), one row advance per SECTION VISIT.
Row cycling is **visit-idempotent** via a `_pending_row_advance` arm/consume flag gated on
`not self._frame_paused`: core calls `reset_frame()` TWICE per visit when a widget transition is
configured (`run_transition`'s `_reset_presenter` plus `_show_one`'s own visit-entry reset — core
documents this double reset as harmless), so a raw `+= 1` in `reset_frame` is the bug class that
was fixed here — it would advance by 2 per transitioned visit and stick on even-length
`legacy_rows`. `reset_frame` only ARMS the flag; the first UNPAUSED scale<=1 draw consumes it,
since paused draws are transition compositing and must neither advance nor burn the pending
advance. Never regress to a bare counter increment in `reset_frame`. Tripwire:
`test_scale1_row_cycling_survives_double_reset_per_visit`.

**Board renderer text conversion** (`layouts/standings_board.py`) — every text draw on the board
routes through the `_t`/`_cap_top` helper pair (same "dc.html visual-cap-top y" -> `_paint.hires`'s
ascent-box-top y formula as the scores physical renderers) so a row mixing multiple font sizes
(rank/abbr/record on one 10px pitch) doesn't bleed into its neighbor's band — see the module's
own docstring for the hardware-validated formula. Rows cap at 5 (`_MAX_ROWS`). `standingsLong`
(longboi, real width >= 400px) adds PCT and L10 columns and splits W/L into separate columns;
`standingsBig` (bigsign) has neither and shows a combined W-L record instead. The GB column on
both is `division_gb` (division games back), not the overall `games_back` the scrolling rows use.

**Empty-board fallback is load-bearing** (`standings.py`'s `update()`) — `_build_board_stories`
returning an empty list (a divisionless API response, `division_id == 0` everywhere, or team
names missing from `MLB_NAME_TO_ABBR`) falls back to `_build_ticker_stories` so the sign is never
blanked under the `auto` default; logs at INFO (`standings: no divisions resolved; falling back
to ticker rows`). Don't remove this fallback when touching `_build_board_stories`. Tripwire:
`test_auto_divisionless_falls_back_to_ticker_rows`.

**`DIVISION_NAMES` is a static id map** (`standings.py`) — MLB Stats API division IDs 200–205 are
stable constants (sportId=1, league 103/104), so labeling a division grouping doesn't need a
hydrate call. `_group_by_division` excludes `division_id == 0` (unknown/unset) — don't drop that
guard, since an ungrouped team would otherwise pollute a division's row list.

**`teams.py` lazy palette is PEP 562** — module-level `__getattr__` exports the named colors
(`WIN_COLOR`/`LOSS_COLOR`/`LIVE_COLOR`/`CHALLENGE_COLOR`) so external code can
`from led_ticker_baseball.teams import WIN_COLOR`. **In-module use must call `_team_palette(name)`
directly** — PEP 562 `__getattr__` does NOT fire for bare-name lookups within the defining module.

**Team color lifting** (`_lift_color`, `teams.py`) — dark team colors are scaled so the peak RGB
channel is ≥ 120, keeping them legible on-panel at low brightness; hue/saturation are preserved
and already-bright teams are unchanged. Don't bypass it when adding team colors.

**`MLB_TEAM_CHIPS` two-tone table must stay 30-complete and lifted** (`teams.py`) — one
`(c1, c2)` tuple per MLB team, keyed by abbreviation, feeding `_primitives.chip`'s two-tone
corner-radius chip render. `MLB_TEAM_CHIPS` is a derived dict comprehension over
`_RAW_TEAM_CHIPS` that runs every entry through `_lift_color` at import time — same lifting
rule as the rest of `teams.py` (don't add a raw, unlifted entry). `_primitives.chip` falls back
to a fixed grey pair for any team missing from the table, so a partial table degrades silently
instead of crashing — that makes an incomplete table easy to miss. If you touch this table,
verify all 30 clubs are still present (`tests/test_teams_chips.py` is the tripwire).

**`_paint`/`_palette`/`_primitives` are handoff ports — geometry changes need design review**
(`_paint.py`, `_palette.py`, `_primitives.py`). These are coordinate-for-coordinate and
color-for-color ports of the `design/…dc.html` prototype (see each module's docstring), consumed
by `layouts/` (the new scale>1 renderers). Treat a pixel offset, radius, or color constant here
as a design decision, not a refactor target — changing one changes the on-panel look of every
scale>1 layout that uses it. **`js_round` — never bare `round()`** (`_paint.py`): all handoff
geometry was authored against JS `Math.round` (half-up: `floor(v + 0.5)`), which differs from
Python's `round()` (banker's rounding, round-half-to-even) at exact `.5` boundaries. Any new
geometry math ported from the design prototype must use `js_round`, not `round()`, to stay
pixel-identical to the handoff at those boundaries.

**Hires text is never exact-pinned in tests** — freetype glyph rasterization is not
byte-identical across platforms (macOS vs. Linux CI), so tests over the `_paint.hires`/hi-res
crawl/scoreboard/two_row text output assert shape-level properties (non-empty, width ordering,
containing/not-overlapping bands) rather than exact pixel coordinates or exact glyph bitmaps.
The **procedural primitives** (`_primitives.py` — chips, diamonds, pips, dashes) ARE exact-pinned
in tests, since they're pure `SetPixel` math with no font-rasterizer variance.

**State-gated preview/postponed label, not tag-truthiness-gated** (`layouts/scoreboard.py`,
`layouts/two_row.py`, `layouts/crawl.py`) — `GameInfo.postpone_tag` DEFAULTS to `"PPD"` (the
parser sets some tag for every game, postponed or not), so `if game.postpone_tag:` would label
every ordinary preview game "PPD" instead of its start time — a recurring bug across the three
physical renderers before the pattern was fixed everywhere. The correct gate is
`game.state == "postponed" and game.postpone_tag`, checking `state` first. All three renderers
share this exact pattern; keep them in sync if `GameInfo`'s postponed-state fields change.

**`render_scoreboard` draws no paging dots** (`layouts/scoreboard.py`) — a deliberate omission,
not a missing feature: the prototype's dot position (`w - n*8 - 6, h - 10`) collides with the
home score's px34 glyph box on live/final games. `story_index`/`story_total` are still accepted
in the function signature (for the uniform layout-renderer contract that `two_row` and `crawl`
use) but are intentionally unused here. Don't "complete" this by adding dots back without
re-solving the collision first.

**`layouts/crawl.py` is engine-scrolled, not self-clocked** — the design prototype's
`tickerScores`/`buildTickerSegs` runs its own internal animation clock; `render_crawl` is
adapted to the engine's cursor contract instead (the stocks `draw_crawl_story` precedent): the
engine owns and advances `cursor_pos`, and `render_crawl` draws this game's segment run at
that offset and returns the segment's total content WIDTH (not an absolute end position) so the
engine can size its per-story advance without re-deriving it from cursor arithmetic. Don't
reintroduce a self-driven animation loop here — it would fight the engine's scroll cadence.

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
  `test_statcast.py` / `test_attendance.py` / `test_transition.py` / `test_emoji.py` / `test_lazy_palette.py` — behavior + rendering coverage. `test_scoreboard.py`'s `TestGeometryGuard` covers
  the legacy `MLBScoreboardMessage._MIN_LOGICAL_WIDTH` raise — that class is scale<=1-only
  post-uplift (see `MLBGameCard` scale-dispatch above), so these tests exercise a narrow
  scale-1 canvas directly, not a bigsign/longboi path. `test_standings.py` also covers
  `layout` validation, per-division board story building/dedup/fallback, and offseason states.
- `test_standings_card.py` / `test_layout_standings_board.py` — `MLBStandingsBoard`'s
  scale-dispatch (held cursor at scale>1, visit-idempotent `legacy_rows` cycling under the
  double-reset-per-visit contract at scale<=1) and the physical board renderer (`standingsBig`
  vs `standingsLong` column sets, row cap, cap-top text conversion).
- `test_resolve_layout.py` / `test_card_dispatch.py` — `layouts.resolve_layout`'s per-sign
  resolution table and `MLBGameCard`'s scale-1-vs-scale>1 dispatch (including the held-cursor /
  frame-hook-forwarding contracts above).
- `test_palette.py` / `test_paint.py` / `test_primitives.py` / `test_teams_chips.py` — the
  handoff-port foundation modules (palette constants, `js_round`, physical paint helpers,
  procedural primitives, and the 30-team chip table).
- `test_layout_crawl.py` / `test_layout_scoreboard.py` / `test_layout_two_row.py` — the three
  new physical (scale>1) renderers, including the state-gated postpone-label pattern.
- `tests/survey_layout_gaps.py` — NOT a pytest test (no `test_` prefix; run directly with
  `uv run python tests/survey_layout_gaps.py`). An instrumented survey harness that measures
  worst-case field extents on the legacy scale-1 scoreboard renderer and reports overlaps —
  the tool that established `_MIN_LOGICAL_WIDTH` empirically. Re-run it if you touch
  `_scoreboard.py`'s zone geometry; interpret its output against the render, not mechanically
  (see the module's own docstring for known by-design "overlaps").

CI (`.github/workflows/ci.yml`): checks out this repo, Python 3.14, `uv sync --extra dev`
(led-ticker-core from PyPI), then `ruff check src tests` and `pytest -q`.

## Adding to the plugin

Register the class in `register()` in `__init__.py` (`api.widget` / `api.transition` /
`api.emoji` / `api.hires_emoji`); it becomes `baseball.<name>`. Import any core dependency from
`led_ticker.plugin` only, and keep the import-purity test green.
