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
- `baseball.promotions` — upcoming home-game promotions (giveaways/theme nights); today-first with highlight/filter/limit knobs and offseason-aware fallbacks. `layout = "auto"` (default), `"ticker"`, or `"card"`. Scale 1 always renders the classic scrolling lines via the legacy `SegmentMessage`, regardless of `layout`. `auto` resolves at scale>1 (`layouts.resolve_promo_layout`): narrow (bigsign) holds a physical promo card, wide (longboi) runs a hires crawl; explicit `"card"`/`"ticker"` force one shape at any scale>1 width. `MLBPromoCard` (`_promo_card.py`) is the scale-dispatching story, same family as `MLBGameCard`/`MLBStandingsBoard`.
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
  layouts/        # new physical (scale>1) renderers: resolve_layout + crawl.py/scoreboard.py/two_row.py/
                  #   standings_board.py + resolve_promo_layout + promo_card.py/promo_crawl.py
  standings.py    # baseball.standings widget (MLBStandingsMonitor); layout="auto"/ticker/board;
                  #   builds MLBStandingsBoard stories per division (update())
  _standings_card.py  # MLBStandingsBoard — the scale-dispatching story: scale>1 dispatches to
                      #   layouts/standings_board.py, scale<=1 forwards one legacy_rows[idx] per visit
  promotions.py   # baseball.promotions widget (MLBPromotionsMonitor); layout="auto"/ticker/card; home-game
                  #   promos; today-first + fallback states; builds MLBPromoCard stories (update())
  _promo_card.py  # MLBPromoCard — the scale-dispatching story: scale 1 delegates to the pre-built
                  #   legacy SegmentMessage, scale>1 dispatches to layouts/promo_card.py or promo_crawl.py
  _mask.py        # TextMask/text_mask/blit_mask/mask_scroll — offscreen-rasterized clipped-scroll text,
                  #   the promo card's "scroll the name if it overflows its band" primitive
  statcast.py     # baseball.statcast widget (MLBStatcastMonitor); Savant day-CSV superlatives; schedule-gated
  attendance.py   # baseball.attendance widget (MLBAttendanceMonitor); league superlatives + team mode; schedule-gated
  transition.py   # baseball.roll* family; lo-res 4-frame + procedural hi-res rotation
```

All widget modules import the shared tables from `teams.py` (no widget reaches into
another widget's private internals). `transition.py` reuses the hi-res sprite generator from
`emoji.py`. `_card.py`, `_promo_card.py`, and `layouts/` import from `_palette.py`/`_paint.py`/`_primitives.py`;
`layouts/promo_card.py` also imports `_mask.py`. These sibling intra-package imports are allowed;
see the import contract below.

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

**`MLBPromoCard` scale-dispatch contract** (`_promo_card.py`) — the one story
`promotions.py`'s `update()` builds per displayed promo, for every `layout`. **scale <= 1
forwards unconditionally to `self.legacy`** — the pre-built `SegmentMessage` for this promo —
without even consulting `resolve_promo_layout` (unlike `MLBGameCard`, there's only one legacy
shape here, so it's built eagerly in `update()` and passed in, not lazily cached on first draw).
**scale > 1 resolves `(cfg_layout, scale, real.width)` via `layouts.resolve_promo_layout`** fresh
on every call (same flight pattern as `resolve_layout`) and dispatches to the held card
(`layouts.promo_card.render_promo_card`) or the hires crawl (`layouts.promo_crawl.render_promo_crawl`).
**Held layout returns `cursor = canvas.width`** — the WRAPPER's LOGICAL width, same held-cursor
convention as `MLBGameCard`/`MLBStandingsBoard` above; the crawl instead treats `cursor_pos` as
logical throughout and returns its advance ceil-divided back to logical, plus `self.padding`,
mirroring `render_crawl`'s own contract. **The per-card clock (`_clock_ticks`) is deliberately
NEVER reset** — advanced in `advance_frame` gated on `not self._frame_paused`, but there is no
`reset_frame` override for it. `reset_frame` still fires (possibly twice per visit, same
core double-reset as `MLBStandingsBoard` above) and the base `FrameAwareBase` counters reset
normally; only `_clock_ticks` survives, so the clipped name-scroll (`_mask.mask_scroll`, driven
by `_clock_ticks * ENGINE_TICK_MS`) keeps running smoothly across section re-entries instead of
snapping back to its start every visit — the same "clock survives visits" lesson as
`led_ticker_flight`'s per-card clock. `self.legacy.reset_frame()` is likewise not forwarded, and
that's harmless: `SegmentMessage._frame_count` only feeds a continuous `font_color` phase
(rainbow/color_cycle), never per-visit story-selection state — `MLBGameCard._legacy` is ALSO
whole-life cached (not per-visit-selected), same shape as `self.legacy` here. Real per-visit
selection state exists only in `MLBStandingsBoard` (`legacy_rows[idx]` cycling via
`_pending_row_advance`) — don't conflate the two patterns. `advance_frame`/`pause_frame`/
`resume_frame` DO forward to `self.legacy` (it's always present, unlike `MLBGameCard`'s
optional `_legacy`, so no `is not None` guard is needed).

**`resolve_promo_layout` lives in `layouts/__init__.py`, not `promotions.py`** — avoids an
import cycle: `_promo_card.py` needs it at draw time, but `promotions.py` imports `MLBPromoCard`
back (to build `feed_stories`), so `_promo_card.py` must not import `promotions.py` at module
level. Moving the resolver back into `promotions.py` recreates that cycle. scale <= 1 returns
`"legacy"` as documentation of intent — `MLBPromoCard.draw` never actually branches on it,
since it returns from the `scale <= 1` forward before calling the resolver at all.

**`_mask.py` is the sanctioned clip mechanism for the promo card's name-scroll** — `text_mask`
rasterizes text onto an OFFSCREEN `HeadlessBackend` canvas through the PUBLIC surface
(`_paint.hires`) and reads it back via `HeadlessCanvas.get_pixel` — the one documented supported
readback (see `led_ticker/backends/headless.py`). **Never reach for a private `_pixels`
buffer or invent a core seam for this** — the public-`get_pixel` offscreen-rasterize pattern is
the whole point: it works with zero new core surface. `text_mask` is `functools.lru_cache(64)`'d,
keyed on the exact `(text, size, bold)` triple, so a scrolling promo name pays the rasterize+scan
cost once, not every frame. **Origin convention: `TextMask.pixels` offsets are baked into
CAP-TOP space already** (the `cap_adjust = size - js_round(size * 0.72)` shift applied once at
mask-build time) — `blit_mask`/`mask_scroll` take a bare cap-top `y` and add offsets directly;
never call `_paint.cap_top()` before a `mask_scroll`/`blit_mask` call, or the correction doubles.
`mask_scroll` is the `dc.html` `maskScroll` port: static single blit when the text fits its
`[x0, x1)` band, else a wrap-seamless two-blit scroll at a fixed physical px/sec.

**Single-pass `_order_and_limit` is load-bearing** (`promotions.py`) — the ONE
highlight-partition + `limit`-truncation implementation shared by the legacy
`_build_promo_stories` (`list[str]` names, feeds `SegmentMessage` lines) and the card/crawl
`_build_promo_card_stories` (`list[PromoInfo]`, feeds `MLBPromoCard`). Before this, `self._promos`
(the structured list) was un-highlighted and un-limited relative to the legacy story list — this
closes that gap by construction: both story shapes are sliced from the SAME ordered list at the
SAME index, so `highlight`/`limit` can never apply differently to the two. Tripwires:
`test_promos_field_matches_feed_stories_order` plus the highlight/limit tests that assert both
shapes (`test_promotions.py`).

**Board renderer text conversion** (`layouts/standings_board.py`) — every text draw on the board
routes through the `_t`/`_cap_top` helper pair (same "dc.html visual-cap-top y" -> `_paint.hires`'s
ascent-box-top y formula as the scores physical renderers) so a row mixing multiple font sizes
(rank/abbr/record on one row's pitch) doesn't bleed into its neighbor's band — see the module's
own docstring for the hardware-validated formula. Rows cap at 5 (`_MAX_ROWS`; `_MIN_ROWS` = 3).
`standingsLong` (longboi, real width >= 400px) adds PCT and L10 columns and splits W/L into
separate columns; `standingsBig` (bigsign) has neither and shows a combined W-L record instead.
The GB column on both is `division_gb` (division games back), not the overall `games_back` the
scrolling rows use.

**`board_rows` geometry table** (`layouts/standings_board.py`'s `_BIG_GEOMETRY`/`_LONG_GEOMETRY`,
keyed 3-5) — `render_standings_board`'s `max_rows` param selects a table entry instead of reading
config: the renderer stays config-agnostic, `_standings_card.MLBStandingsBoard.board_rows`
(forwarded from `MLBStandingsMonitor.board_rows`, validated 3-5 in `standings.py`'s
`validate_config` — bool explicitly excluded, mirrors core's `font_threshold` convention) is what
carries the widget's config through. **The 5-row table entries are the pre-#72 hardcoded values,
BYTE-IDENTICAL** — the pre-existing 5-row layout tests assert this unchanged, and
`test_five_row_geometry_matches_pre_uplift_hardcoded_values` pins the table entries directly so a
future edit can't silently drift them while still passing the pixel tests by compensating
elsewhere. 4/3-row entries scale `pitch`/`text`/`rank`/`chip` up (bigger text for fewer rows); the
header (division name + column labels) is drawn separately in `_render_big`/`_render_long` and
NEVER changes with row count. `abbr_x = chip_x + chip_h + 3` (chip_x fixed per variant: 11 big, 18
long) for every entry EXCEPT long's 5-row, which keeps the pre-#72 handoff value (32) exactly —
the formula would give 30 there; this is a preserved pre-existing handoff quirk, not something
introduced by the row-count feature. `gb_x`/`strk_x` (big only — long's column x positions are
fixed across every count) move from 180/212 to 172/216 ONLY at 3 rows: at that size (px15), "16.0"
(worst-case GB) would otherwise run up against a fixed STRK column. A `max_rows` outside the table
(3-5) falls back to 5 rather than `KeyError`ing — defensive only, since `validate_config` is the
real gate. **Collision test is the tripwire for this whole table**
(`test_layout_standings_board.py`): for every (variant, row-count) pair it renders worst-case row
content (record `"100-62"`, gb `"16.0"`, pct `".1000"`, l10 `"10-0"`, strk `"W12"`, abbr `"WSH"`)
and asserts no two columns' measured extents overlap (via `text_width` — the same function
`hires`/`draw_record` use to advance their own cursors, not a pixel-clustering heuristic, which
turned out to be too fragile: individual glyphs within one field routinely have a couple px of
dark kerning between them, at a similar magnitude to some of the tighter cross-column gaps) and
that no row's content bleeds into the next row's vertical band. Any new per-count geometry value
must pass this test before shipping.

**Row selection + tracked-team pinning** (`standings.py`'s `_select_division_rows`) — a board's
`rows` are the top `board_rows` teams by `division_rank`, then any TRACKED team in that division
NOT already included is pinned in by displacing row(s) from the BOTTOM of that top-N selection
(one displaced slot per missing tracked team, best-ranked missing team kept first if there isn't
room for all of them) — re-sorted back into `division_rank` order afterward. The rank digit shown
is always the TRUE `division_rank`, never renumbered 1..N — a board reading `1, 2, 5` is
self-explanatory. `board_rows=5` is a no-op versus pre-#72 behavior whenever a division has <=5
teams (the common case), since every team is already in the top-5 selection and nothing needs
pinning. `_build_board_stories` uses this for both `MLBStandingsBoard.rows` (forwarded to the
scale>1 renderer) and `legacy_rows` (the scale<=1 fallback) — both get the SAME selected rows, so
neither degrades to a different division slice. Tripwires: `TestSelectDivisionRows`
(`tests/test_standings.py`, unit-level on the selection function itself) plus
`test_board_rows_pins_tracked_team_outside_cutoff` (integration, through `update()`).

**Empty-board fallback is load-bearing** (`standings.py`'s `update()`) — `_build_board_stories`
returning an empty list (a divisionless API response, `division_id == 0` everywhere) falls back to
`_build_ticker_stories` so the sign is never blanked under the `auto` default; logs at INFO
(`standings: no divisions resolved; falling back to ticker rows`). Tracked teams that fail to
resolve to a division fall back to the overall leader's division board, NOT to ticker rows. Don't
remove this fallback when touching `_build_board_stories`. Tripwire:
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
- `test_resolve_promo_layout.py` / `test_promo_card_dispatch.py` — `layouts.resolve_promo_layout`'s
  per-sign resolution table and `MLBPromoCard`'s scale-1-vs-scale>1 dispatch, including the
  held-cursor contract, the never-reset `_clock_ticks` clock, and frame-hook forwarding to
  `self.legacy` (see `MLBPromoCard` scale-dispatch above).
- `test_layout_promo_card.py` / `test_layout_promo_crawl.py` — the held promo card (big vs long
  geometry, name auto-scroll via `mask_scroll`, paging dots) and the hires promo crawl (engine
  cursor contract, segment ordering, chip/VS/offer/time fields).
- `test_mask.py` — `_mask.py`'s offscreen-rasterize-and-readback `TextMask` cache, the CAP-TOP
  origin conversion, and `mask_scroll`'s fit-vs-scroll fast path / wrap-seamless two-blit scroll.
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
