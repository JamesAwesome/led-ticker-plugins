# CLAUDE.md

Guidance for Claude Code when working in **led-ticker-hockey**, a plugin for
[led-ticker](https://github.com/JamesAwesome/led-ticker) in the first-party pack.

`README.md` is the source of truth for the user-facing surface (options, modes, layouts,
cadence). This file keeps the **load-bearing invariants** a contributor must respect, plus
navigation aids. When the two disagree about *how a feature works*, the README wins; this
file is the source of truth for *how to keep it working*.

## Overview

One widget, `hockey.scores`, contributed via the `led_ticker.plugins` entry point
(namespace `hockey`, see `register()` in `__init__.py`): live NHL games from the public,
unofficial web API (`https://api-web.nhle.com`, **no key**), one story per game, modes
`teams` / `league` / `live`, `layout = "auto"` (default) / `"scoreboard"` / `"ticker"`.
`auto` resolves to `scoreboard` on all three signs. Scale 1 renders through the bitmap
classes in `_scoreboard.py`; scale>1 dispatches through `HockeyGameCard` (`_card.py`) to
the physical renderers in `layouts/`. Example teams everywhere are `PHI` and `NYI`.

## Commands

```bash
uv sync --extra dev                                        # repo root
uv run pytest plugins/hockey --cov=plugins/hockey/src      # suite (asyncio_mode = "auto")
uv run ruff check plugins/hockey && uv run ruff format --check plugins/hockey
uv run pyright plugins/hockey/src
```

Python **3.14+** only (no `from __future__ import annotations`). `led-ticker-core >= 4.30`.

## Invariants

**Import purity** — import `led_ticker` ONLY from `led_ticker.plugin`. AST tripwire:
`tests/test_import_purity.py`.

**The source never raises** (`_source.py`) — every network and parse error becomes
`stale` + backoff (2x interval, doubling, capped at 4 h; until the first successful poll
it starts from `LIVE_INTERVAL`, since an empty source reads idle); a bad payload keeps the last
good games. A game that drops out of the feed keeps its last state: NEVER infer a final
from a game disappearing. `polled_at` is wall-clock epoch seconds.

**One shared source per session** — `shared_source(session)`; every widget's `want()`
merges into it, and cadence is the source's (15 s live — or the fastest widget
`update_interval` below that, via `want(live_interval=...)` — / 300 s pregame / 3600 s
idle, `MIN_INTERVAL` 10 s floor; season schedule at most every 6 h). The source only
polls when a widget's `update()` calls it, and each widget's monitor loop runs every
`max(MIN_INTERVAL, update_interval)` s, so an interval above 15 slows that widget (and a
lone widget's polling). The landing "situation" call is
gated to live games that some consumer displays (`note_displayed`, per consumer, so
shared widgets do not multiply requests).

**`run_monitor_loop(..., splay=False)`** — core's default splay adds a fixed random
0–60 s to the poll interval at startup (a 15 s live cadence ran at 29 s on hardware, in
football). The shared source rate-limits itself, so the widget loop must not add jitter
(`test_start_registers_interest_updates_and_spawns`).

**Next game vs `_games` share ONE hold predicate** — `_models.final_in_hold` (with
`GAME_LENGTH`) is used by both `scores.select_stories` and `NHLSource._playing`. A team
skips the next-game lookup (and its `next_games` entry is dropped) only while it has a
LIVE game or a final inside the hold at the SHORTEST widget hold (`_next_hold_hours`). A
future game never counts — a post-midnight game is not "later today" and must come from
the lookup. A live game absent from one payload keeps the live cadence for `LIVE_GRACE`
(30 min) (`_cadence` only) at every hold, including 0: the hold prune keeps a live game
at least that long, and yesterday's feed is also fetched when a cached live game is missing from today's;
`_playing` reads `_games` unchanged, matching
`select_stories`. Diverge `select_stories` and `_playing` and a team's card vanishes
after its final's hold (`test_next_game_returns_after_final_hold`).

**First-sight goal baseline lives in the source; celebrated state lives on the widget/card**
— `NHLSource.goals_after_baseline(game_id)` is NON-consuming: the first sight of a game
records a baseline and returns nothing older. Each `HockeyScoreMonitor` keeps its own
`_celebrated` map with a per-widget first-sight baseline, so a hot reload with a surviving
shared source is silent and every widget celebrates a goal exactly once. Do not move
consumption into the source.

**Cards are persistent** — one `HockeyGameCard` per game id (or `next:TEAM`), kept in
`_cards` across polls; `_rebuild` reassigns `game` / `stale` in place. Never rebuild cards
per poll: celebration state, frame counters and the legacy story cache live on them.

**`reset_frame` consumption** (`_card.py`) — the celebration plays from a snapshot
(`_playing`) taken at visit-entry `reset_frame()`. A goal is consumed only once it was
actually DRAWN on a live (unpaused, `_frame_count > 0`) frame (`_shown`), so stale frame
counts or transition compositing never eat an unseen celebration. Goals queued mid-visit
wait for the next turn. Non-tracked goals highlight the score instead; empty `teams` means
no celebrations. Scroll-mode sections (`ticker`, `one_at_a_time`) never call
`reset_frame()`, so with no snapshot (`_playing is None`) the first live draw SELF-STARTS
a run (`_run_start` = that `_frame_count`). Its phase is `_run_pos`, which advances once
per frame the card is actually DRAWN (deduped by `_frame_count`), never by
`_frame_count - _run_start`: core advances every buffered widget each tick but stops
drawing once the cursor reaches the width, so a run hidden behind another card's takeover
must not burn out unseen. The draw after its last frame consumes it exactly as `reset_frame` would, sets `_playing` and
`_run_start` back to None and paints the board; the next live draw may self-start again.
`reset_frame` always sets `_run_start = None` (visit runs start at frame 0), so the
slideshow path never self-starts. A PAUSED `reset_frame` is a transition's
(`run_transition` / `_scroll_transition` call `pause_frame()` then `reset_frame()` on the
incoming widget; `FrameAwareBase.reset_frame` keeps the pause flag): it consumes as usual
but sets `_playing = None`, because a scroll section never resets again and a leftover
snapshot would stop the card self-starting for good; a slideshow's `_show_one` resets
again live and snapshots (`test_transition_reset_keeps_self_started_runs`). Every celebration frame is a full-panel takeover: it
first clears the real panel (to `bg_color` when set, else black, at every scale), because in a
side-by-side scroll core resets once per tick and earlier widgets have already painted;
it returns a `canvas.width` cursor, so later widgets are skipped for the tick. Core keeps
decrementing the cursor beneath it, so a self-started run freezes the card's EFFECTIVE
cursor: `_x_shift` (effective = raw + shift) puts the board back where the run began, and
is cleared when the raw cursor next increases (a fresh pass), which also re-bases a run
that spans passes (`test_scroll_mode_run_freezes_cursor_until_next_pass`,
`test_run_cut_by_a_section_end_resumes_at_the_new_pass`). `reset_frame` clears it. Only
the FIRST live draw of a frame (`_last_frame`) updates the freeze: a one-game `ticker`
section cycles ONE card object, so at the pass junction core draws it two or three times in
one tick, and a later copy's higher cursor must not read as a fresh pass (it zeroed the
shift and teleported the left copy ~80 columns; `test_same_card_twice_per_tick_never_jumps`).
A non-first draw (a later copy, or a paused transition redraw, since core pauses the
outgoing widget too) paints with the shift when its cursor is at or left of the last raw
cursor and raw otherwise (a later copy's cursor already chains off the shifted first copy)
(`test_non_first_draws_never_touch_the_freeze`). A self-started run (and the demo re-arm that feeds one) also BEGINS
only on a frame's first live draw: started on a later copy it would record that copy's
cursor as `_run_cursor`, and the left copy would resume there after the run
(`test_back_to_back_runs_on_a_repeated_card_never_jump`). Slideshow and `one_at_a_time`
draw each card once per tick, so every draw there is a first draw.
`hold_time` is not read in scroll modes.

**Draw return is absolute** — `draw()` returns `cursor_pos + content width` (core's
contract, like `widgets/message.py`): the hi-res held board paints at `cursor_pos`
(`render_scoreboard(..., x_offset=)`, through `_paint.ShiftedReal`, clipped at both edges)
and returns `cursor_pos + canvas.width`; the hi-res crawl returns
`cursor_pos + run + padding`. Only the celebration takeover returns a bare `canvas.width`.
Core ends a widget in a `ticker` / `one_at_a_time` section only once that end goes
negative, so a constant return wedges the section on the first card forever (#113). The
scale-1 band board returns `cursor_pos + width` too but still PAINTS at x = 0 (see Known
gaps).
Tripwires: `test_scroll_two_hires_cards_completes` and
`test_scroll_with_celebration_completes` drive core's REAL `_scroll_one_by_one` /
`_scroll_side_by_side` (`test_card_dispatch.py`, core-internal imports are fine in
tests only), plus `test_scale4_scoreboard_scrolls_with_cursor_pos`.

**`hold_time` property** — `HockeyGameCard.hold_time` = `base_hold` with nothing due;
with `n` celebrations due it is `n * CELEBRATION_SECONDS` (80 frames x 50 ms = 4 s) +
`max(base_hold, BOARD_FLOOR)` (4 s) so the board after the celebration keeps its own hold.
Core reads it as `max(section_hold, getattr(story, "hold_time", 0.0))` in led-ticker
`ticker.py` (`_show_one`, around line 762 at time of writing), right AFTER `reset_frame()`.
Keep it a property reading `_playing` (fall back to `pending`); if core changes that line
the celebration is cut short.

**Celebration paints only on live frames** — `_celebrate` returns False (the board draws)
while `_frame_paused` (transition compositing), so a mid-celebration frame is never
composited into a transition.

**Scoring changes are replacements, keyed by score snapshot** — the feed's goal key is
`period:time:playerId`, so a scorer correction arrives as a NEW key. The widget keeps
`_celebrated_scores[gid]` (`(away, home)` snapshots, first-sight seeded from all of the
game's goals, pruned to <= the current score so a disallowed goal's snapshot is forgotten)
alongside `_celebrated`; a new key at a known snapshot goes to `card.replace_goals`, which
swaps the pending/playing entry and never celebrates or highlights. `card.queue_goals` also
replaces a pending entry with the same snapshot instead of appending. Test helpers that
queue several goals MUST give them distinct scores.

**Demo re-arm** — demo live cards carry `demo_goals`; `reset_frame` re-queues them after
every `DEMO_EVERY` (3) COMPLETED visits (`_frame_count > 0` at reset, so a transition's
extra `reset_frame` before `_show_one`'s is not counted). Scroll-mode sections have no
visits: a self-started run's end records `_demo_rest_from`, and the demo re-queues once
`DEMO_REST_FRAMES` (3 x 80 = 240, 12 s) live frames pass with nothing pending.

**`segments()` in `layouts/crawl.py` is the single wording source for the ticker** — the
hi-res crawl paints it and the legacy ticker message joins the same list, so the two
paths cannot drift.

**Layout invariant (CONTRIBUTING.md)** — measured widths (`_paint.text_width`), >= 6 px
(`_MIN_GAP`) between texts sharing a vertical band, row-uniform name sizes, ellipsis at the
floor. **Tripwire:** `tests/test_layout_scoreboard.py::test_worst_case_keeps_min_clearance`
(longest abbreviations, double-digit scores, `SOG 99`, `PP` + `EN`, `FINAL/SO`) on both
physical signs; it also spies `rect()` / `_dotted()` so chips, badges and the divider
keep >= 6 px from any text sharing their rows (a badge's knocked-out label is exempt) and
everything stays inside the panel vertically (cap top >= 0, baseline < height). The
bigsign chip is x2-7 for that reason, and the divider clamps to the measured left edge of
any status line on its row. Any geometry/ladder change must pass it. The smallsign twin is
`tests/test_scoreboard.py::test_band_board_worst_case_clearance` (texts per band, from
measured columns, plus the band board's `shape_extents`). The smallsign sport icon
(`:hockey.puck:`, `emoji.PUCK`) is the only entry in `shape_extents` (`"ICON"`); it may sit
`_ICON_GAP` (2 px) from the text it labels (the period on a live/final card, the matchup on
a next game), keeps >= 6 px from everything else, and is the element LEFT OUT when it
cannot (never the score, clock or period).

**Logos are bundled assets, never fetched** (`_logos.py`) — 32 64x64 RGBA PNGs under
`assets/logos/` with `MANIFEST.txt` (source URL + fetch date per file). A human refreshes them
with `tools/fetch_logos.py`; CI, tests and the sign never run it, and the render path never
makes an image request. Same module shape as the basketball plugin: `_logos.sprite(abbrev,
size)` is `functools.cache`'d per (team, size), drops alpha < `ALPHA_MIN` and near-black
(< `DARK_FLOOR`) pixels, and returns None for an unknown team or an undecodable asset — it
NEVER raises. Sizes: `LOGO_ROW` 28 (bigsign board, one per 32 px team row), `LOGO_BIG` 36
(bigsign celebration detail), `LOGO_LONG` 48 (longboi board edges and detail). A logo REPLACES
the chip in place (`_slot`); when it can't be drawn (`logos = false`, missing sprite) the chip
goes in and that side's abbrev moves back to `name_x` — per SIDE, so one missing logo never
shifts the other team. On the bigsign next-game card the home logo rides inside the name run
(its width is in the run's `fixed`); the longboi next card keeps the chip-era name limits so
a logo eats the names' budget, never the centre column's. Smallsign never shows logos.
Tripwires: `test_logos.py`, `test_logos_replace_both_chips`, `test_logos_false_paints_chips`,
`test_missing_sprite_falls_back_to_chip`, `test_one_missing_logo_keeps_the_other`,
`test_detail_paints_scoring_team_logo_clear_of_text`, and `test_worst_case_keeps_min_clearance`
parametrized over `logos`.

**Hi-res text is never pixel-pinned in tests** (freetype differs macOS vs Linux) — assert
extents, bands, ordering and colors.

**Palette is one hue per field** (`_palette.py`) — white score/clock, amber period/PP/date,
cyan SOG, dim labels, green final winner, gray loser. Black is invisible on the panels, so
team chips are lifted for LED brightness.
`bg_color` applies at every scale: core fills it before every draw (`reset_canvas`)
and the renderers paint over it, never clearing it (the takeover refills it). `font_color`
reaches only the scale-1 ticker message.

## Known gaps

- The landing `situation` field shapes (power play, empty net) come from community docs and
  are unverified against a live game; capture a real payload as a fixture when one is on.
- The scale-1 `ticker` layout's clock text updates per poll; boards and hi-res tick per second.
- Scroll-mode takeover vs core's end-of-scroll hold (`ticker` sections only; `hold_at_end`
  is the section `hold_time`, default 3 s): any celebration on the section's LAST card can be
  cut once that card's end is inside the panel. Core starts the hold when the last buffered
  widget's end is `<= canvas.width` and it has fetched the end sentinel. The takeover's
  `canvas.width` end satisfies the first condition, and the sentinel is fetched as soon as
  the last card's end is inside the panel while it is not first. So a last card narrower than
  the panel (fully visible behind the previous card) has the hold start the moment the
  previous card pops, mid-run. A card at least as wide as the panel only reaches it through
  the hold itself. The run is cut to what is left of the hold and the rest plays on the
  card's next pass, unless a section transition resets the card first (it is the section's
  first card), which consumes the shown goal. No `hold_time` rules it out
  (`test_narrow_last_card_celebration_is_cut_then_resumes`,
  `test_goal_inside_the_end_hold_is_cut_then_resumes`,
  `test_wide_last_card_celebration_before_the_end_hold_plays_in_full`).
- A card celebrating at buffer index > 0 while the card to its left is still visible: the left
  card keeps scrolling under the takeover and the frozen card resumes where its run began,
  so a gap of up to 80 columns opens after the left card. By design (the celebrating card's
  own board is never skipped).
- The scale-1 band board (`_scoreboard.HockeyBandBoard.draw`) paints at x = 0 whatever the
  cursor and `Fill`s the whole canvas with `bg_color`. It returns `cursor_pos + width`, so
  scroll sections do not wedge, but a smallsign scoreboard does not visually scroll, and in
  a side-by-side section it wipes the widget to its left. Pre-existing; not fixed here.
- Celebration and demo timing in scroll modes count scroll ticks: 80 frames (and the demo's
  240-frame rest) are 4 s (12 s) only at the default `scroll_step_ms` of 50 ms; the
  end-of-scroll hold always ticks at 50 ms.

## Tests

- `test_import_purity.py` / `test_smoke.py` — public-surface tripwire; entry-point wiring.
- `test_models.py` / `test_teams.py` — parsing (incl. garbage rows), team table and codes.
- `test_source.py` — cadence, gate, shared source, baseline, backoff, never raising.
  Fake session + injected clock; no network.
- `test_scores.py` — `validate_config`, selection per mode, demo, stale, persistent cards.
- `test_logos.py` — logo decode, floors, fallback, cache, clipping.
- `test_celebration.py` — timeline phases and renderers.
- `test_resolve_layout.py` / `test_card_dispatch.py` — resolver; scale dispatch; consumption.
- `test_layout_scoreboard.py` / `test_layout_crawl.py` / `test_scoreboard.py` — physical and
  bitmap renderers, the clearance tripwire, ticker wording.
- `test_examples.py` — example configs validate, use `PHI`/`NYI`, and the README documents
  every option.

CI (`.github/workflows/ci.yml`): Python 3.14, `uv sync --extra dev`, ruff check + format
check, pyright on `src`, pytest with coverage (`fail_under = 90`).
