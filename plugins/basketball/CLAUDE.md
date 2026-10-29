# CLAUDE.md

Guidance for Claude Code when working in **led-ticker-basketball**, a plugin for
[led-ticker](https://github.com/JamesAwesome/led-ticker) in the first-party pack.

`README.md` is the source of truth for the user-facing surface (options, modes, layouts,
cadence). This file keeps the **load-bearing invariants** a contributor must respect, plus
navigation aids. When the two disagree about *how a feature works*, the README wins; this
file is the source of truth for *how to keep it working*.

## Overview

One widget, `basketball.scores`, contributed via the `led_ticker.plugins` entry point
(namespace `basketball`, see `register()` in `__init__.py`; it also registers the
`:basketball.ball:` emoji): live NBA games from ESPN's public, unofficial site API
(`https://site.api.espn.com`, mirror `site.web.api.espn.com`, **no key**), one story per
game, modes `teams` / `league` / `live`, `layout = "auto"` (default) / `"scoreboard"` /
`"ticker"`. `auto` resolves to `scoreboard` on all three signs. Scale 1 renders through the
single-band bitmap `BasketballBandBoard` in `_scoreboard.py`; scale>1 dispatches through
`BasketballGameCard` (`_card.py`) to the horizontal arena board in `layouts/scoreboard.py`
(bundled team logos at the edges). Example teams everywhere are `PHI` and `NY` (the Knicks
are `NY`, never `NYK`). The package is a sibling of `plugins/football/` and
`plugins/hockey/`; their CLAUDE.md invariants hold here unless restated below. Unlike
football it is a DAY model (hockey's), has no per-score takeover (only a win at the final
buzzer), and ships bundled logo assets.

## Commands

```bash
uv sync --extra dev                                              # repo root
uv run pytest plugins/basketball --cov=plugins/basketball/src    # suite (asyncio_mode = "auto")
uv run ruff check plugins/basketball && uv run ruff format --check plugins/basketball
uv run pyright plugins/basketball/src
```

Python **3.14+** only (no `from __future__ import annotations`). `led-ticker-core >= 4.31`.

## Invariants

**Import purity** — import `led_ticker` ONLY from `led_ticker.plugin`. AST tripwire:
`tests/test_import_purity.py::test_plugin_imports_only_public_surface`.

**The source never raises, and falls back to the mirror host** (`_source.py`) — every
network and parse error becomes `stale` + backoff (2x interval, doubling, capped at 4 h); a
bad payload keeps the last good games. `_get` tries `HOSTS` in order (`site.api`, then the
`site.web.api` mirror) and only the LAST host's failure propagates. Never collapse the list
to one host. Tripwires: `test_host_fallback_on_403`, `test_both_hosts_fail_is_stale`,
`test_malformed_payload_keeps_last_games`, `test_poll_never_raises`.

**One shared source, `splay=False`** — `shared_source(session)`; every widget's `want()`
merges into it, and cadence is the source's (15 s live — or the fastest widget
`update_interval` below that — / 60 s within 30 min of a tip-off / 300 s pregame / 3600 s
idle, `MIN_INTERVAL` 10 s floor, schedule fetch at most every 6 h). The source only polls
when a widget's `update()` calls it. `update_interval` is a `start()` kwarg, NOT an attrs
field. `run_monitor_loop(..., splay=False)`: core's default splay adds a fixed random 0-60 s
at startup, which stretched the 15 s live cadence on hardware. Tripwires:
`test_cadence_ladder`, `test_shared_source_is_per_session`,
`test_start_registers_interest_updates_and_spawns`.

**The day model keeps yesterday's slate** — today's scoreboard only; when a cached LIVE game
is missing from today's payload (a West-coast game past midnight Eastern) the source also
fetches `?dates=<yesterday>` — yesterday in `_models.ESPN_TZ` (Eastern, the slate's
day), NEVER the widget's tz (soft: a failure keeps today's payload). A live game missing
from one payload stays live for `LIVE_GRACE` (30 min). NEVER infer a final from a game
vanishing: a vanished game keeps its last state until the hold passes. Tripwires:
`test_yesterday_feed_keeps_late_game`, `test_yesterday_feed_failure_is_soft`,
`test_yesterday_feed_uses_eastern_date_for_western_users`,
`test_vanished_game_keeps_state_until_hold`.

**`FinalEvent` baseline lives in the source; celebrated keys live on the widget** — the
source records one `FinalEvent` per game ONLY when it watched the game go live -> final; a
game first seen final records nothing (`test_first_sight_final_is_silent`,
`test_live_to_final_emits_final_event`). `final_after_baseline(game_id)` is NON-consuming
(`test_final_event_is_non_consuming`). Each `BasketballScoreMonitor` keeps its own
`_celebrated` map with a per-widget first-sight baseline, so a hot reload with a surviving
shared source is silent and every widget celebrates a final exactly once
(`test_reload_with_surviving_source_is_silent`, `test_celebrated_pruned_with_game`). Only a
tracked WINNER queues (`test_queue_final_only_for_tracked_winner_and_caps`,
`test_untracked_win_does_not_queue`); there is no loss takeover.

**Cards are persistent** — one `BasketballGameCard` per game id (or `next:TEAM`), kept in
`_cards` across polls; `_rebuild` reassigns `game` / `stale` in place and arms the score
pulse on a changed score. Never rebuild cards per poll: celebration state, frame counters
and highlights live on them (`test_cards_persist_across_polls`,
`test_next_game_card_keyed_by_team_and_reused`). In `live` mode a card that left the
selection keeps rendering until its final has flashed (`pending` empties)
(`test_live_mode_keeps_finished_card_until_shown`).

**`reset_frame` consumption, self-start, freeze** (`_card.py`) — the celebration plays from a
snapshot (`_playing`) taken at visit-entry `reset_frame()`. A run is consumed only once it was
actually DRAWN on a live (unpaused, `_frame_count > 0`) frame (`_shown`); finals queued
mid-visit wait for the next turn (`test_reset_without_drawing_keeps_pending`,
`test_celebration_consumed_after_one_visit`, `test_paused_frames_do_not_advance_celebration`).
Scroll-mode sections (`ticker`, `one_at_a_time`) never call `reset_frame()`, so with no
snapshot the first live draw SELF-STARTS a run (`_run_start` = that `_frame_count`); its
phase is `_run_pos`, advanced once per frame the card is actually DRAWN (deduped by
`_frame_count`), never by `_frame_count - _run_start` — core advances every buffered widget
each tick but stops drawing once the cursor reaches the width, so a run hidden behind
another card's takeover must not burn out unseen. The draw after its last frame consumes it
and paints the board. Every celebration frame is a full-panel takeover: it first fills the
real panel (`bg_color`, else black) and returns a `canvas.width` cursor so later widgets are
skipped for the tick; the card's effective cursor freezes (`_x_shift`) because the engine
keeps decrementing `pos` under it. Tripwires:
`test_scroll_mode_starts_pending_celebration_on_first_live_draw`,
`test_scroll_mode_run_freezes_cursor_until_next_pass`, `test_takeover_clears_preceding_widget`,
`test_takeover_clear_uses_bg_color_at_every_scale`. The celebration paints only on live
frames (`_celebrate` returns False while `_frame_paused`).

**`hold_time` property** — `base_hold` with nothing due; with a celebration due it is
`CELEBRATION_SECONDS` (4 s) + `max(base_hold, BOARD_FLOOR)` (4 s), `MAX_QUEUED` = 1 (a game
ends once). Core reads it as `max(section_hold, getattr(story, "hold_time", 0.0))` right
AFTER `reset_frame()`. Tripwires: `test_hold_time_extends_while_celebration_pending`,
`test_queue_caps_at_one`.

**Demo re-arm** — the demo live card carries `demo_final` and re-queues it after every
`DEMO_EVERY` (3) COMPLETED visits (`_frame_count > 0` at reset, so a transition's extra
`reset_frame` is not counted); scroll-mode sections re-queue after `DEMO_REST_FRAMES`
(3 x 80 = 240 frames, 12 s). The demo card keeps SHOWING the live state (PHI 98 – NY 101,
clock `1:48`, in the clutch window so the red clock shows) while the queued celebration
carries the final snapshot (`test_demo_rearms_every_third_visit`,
`test_demo_builds_four_cards_and_queues_final`, `test_demo_games_cover_states`).

**`segments()` in `layouts/crawl.py` is the single wording source for the ticker** — the
hi-res crawl paints it and the scale-1 `SegmentMessage` joins the same list
(`test_ticker_message_uses_segments`, `test_segments_live_wording`).

**Every `draw()` honours `cursor_pos` and `y_offset` and returns ABSOLUTE ends** — the scale>1
scoreboard paints at `cursor_pos` (via `_paint.ShiftedReal`), the crawl at `cursor_pos`
(centred when held), the smallsign band board offsets every x by `cursor_pos` and every shape
row by `y_offset`; each returns `cursor_pos + <its width>`. A constant `canvas.width` return
never goes negative, so a `ticker` / `one_at_a_time` section wedges on the first card forever.
Tripwires: `test_scale4_scoreboard_scrolls_with_cursor_pos`, `test_band_board_honours_cursor_pos`,
`test_band_board_follows_y_offset`, `test_render_crawl_honours_cursor_pos`,
`test_y_offset_shifts_content`.

**Logos are bundled assets, never fetched** (`_logos.py`) — 30 64x64 RGBA PNGs under
`assets/logos/` with `MANIFEST.txt` (source URL + fetch date per file). A human refreshes them
with `tools/fetch_logos.py`; CI, tests and the sign never run it, and the render path never
makes an image request. `_logos.sprite(abbrev, size)` is `functools.cache`'d per
`(abbrev, size)`: first call decodes with Pillow, LANCZOS-downsamples, alpha-composites over
black and drops pixels with alpha < `ALPHA_MIN` or a brightest channel < `DARK_FLOOR`
(near-black reads as a hole on the panel). An unknown team, a missing file or a decode error
returns `None` (logged once at DEBUG) and the renderer paints the two-tone chip instead —
it NEVER raises. Tuning (sizes `LOGO_BIG` 36 / `LOGO_LONG` 48, floors, any brightness lift)
lives in `_logos.py` at decode time, so a tuning change needs no asset refresh. Painting is a
`SetPixel` loop on the unwrapped real canvas through `ShiftedReal`. Tripwires:
`test_all_team_logos_decode`, `test_logo_pixels_respect_floor_and_alpha`,
`test_missing_logo_falls_back_to_chip`, `test_corrupt_logo_falls_back_to_chip`,
`test_sprite_is_cached`, `test_paint_logo_clips_on_shifted_real`,
`test_logos_painted_on_both_sides`, `test_logos_false_paints_chips_and_abbrevs`.
Smallsign never shows logos.

**`small_font` is rejected; the smallsign board is ONE 16-row band in `font`** —
`validate_config` returns a message for a `small_font` key (football's two 8-row bands in 5x8
do not exist here) (`test_validate_rejects_small_font`). `logos` must be a bool
(`test_validate_logos_bool`). `update_interval` is validated but is a `start()` kwarg.

**Layout invariant (CONTRIBUTING.md)** — measured widths (`_paint.text_width`), >= 6 px
(`_MIN_GAP`) between texts/shapes sharing a vertical band, row-uniform size ladders for the two
scores and the two chip-fallback abbreviations, ellipsis at the floor or DROP where an ellipsis
would be meaningless (bigsign leader names below the floor, the linescore strip). Logos are
shapes: they count in the clearance check like chips do. **Tripwires:**
`tests/test_layout_scoreboard.py::test_worst_case_keeps_min_clearance` (two three-digit scores,
`UTAH` / `WSH`, `2OT`, `FINAL/OT`, the longest leader name, six linescore columns, `STALE`,
a logo in place) on both physical signs — it spies `hires()` / `rect()` / `paint_logo()` — plus
`test_demo_cards_keep_min_clearance` and the celebration's
`test_detail_texts_keep_clearance_worst_case`. The smallsign twin is
`tests/test_scoreboard.py::test_band_board_worst_case_clearance` (fed by the band board's
`shape_extents`), with `test_band_board_worst_final_shrinks_to_f_ot`. The smallsign
next-game ball (`"ICON"` in `shape_extents`, `emoji.BALL`) IS the `@` / `VS` between the
names, `_ICON_GAP` (3 px) from each; at 14 px it is narrower than the 18 px ` @ ` it replaces,
so it is always drawn and never costs day/tip/STALE text
(`test_future_ball_is_narrower_than_the_at`, `test_future_ball_worst_case_clearance`).
`ball_at = false` (widget -> card -> board) restores the GRAY text separator and draws no
ball (`test_future_ball_at_off_keeps_the_text`). `ball_at` must be a bool
(`test_validate_bool_options`).

**Hi-res text is never pixel-pinned in tests** (freetype differs macOS vs Linux) — assert
extents, bands, ordering and colors. Logo sprites are tested for footprint, never artwork.

**Palette is one hue per field** (`_palette.py`) — white score/clock, amber period/date/tip-off,
cyan points-leader lines, dim labels/dividers/`STALE`/`TBD`, green final winner, gray loser
and records. **`RED` is reserved for the clutch clock** (live, 4th quarter or later, <= 2:00,
margin <= 5 — `_models.is_clutch`; `test_clutch_clock_is_red`, `test_is_clutch_parses_tenths`)
and **`ORANGE` for the ball emoji and the longboi per-quarter linescore strip**
(`test_longboi_linescore_strip_orange_and_dropped_when_narrow`); the strip is budgeted to the
scores' footprint (`_strip_budget`), not the centre column, so OT fits
(`test_longboi_strip_renders_in_overtime`). Never restyle a field locally.
Black is invisible on the panels, so team chips are lifted; near-black primaries use the
lifted secondary. `bg_color` fills at EVERY scale: core fills it before every draw and the
celebration's takeover fills it explicitly
(`test_core_fill_of_bg_color_survives_every_scale`). `font_color` reaches only the scale-1
ticker message.

**Clocks are not ticked locally** — the feed has no running flag and the clock stops on every
whistle; renderers show `game.clock` as polled. A `0.0` clock at an end-of-period buzzer shows
`END Q3` with no clock (`test_status_lines_end_period_hides_zero_clock`).

## Known gaps

- The live and final fixtures (`tests/fixtures/event_live.json`, `event_final_ot.json`) are
  hand-written from a captured `post` event and flagged `"_handwritten": true`; no live NBA
  game was captured during the build. Replace them with real captures
  (`tools/capture_fixtures.py`) when one is on, and re-check the `leaders` / `linescores` /
  in-game clock parsing.
- Smallsign dark team colours (e.g. `UTAH` purple) read dim even after the lift at 3 px chip
  width.
- Bigsign chip-fallback (`logos = false` or a missing logo) with two three-digit scores drops
  the abbreviation to keep >= 6 px clearance.
- `ESPNSource._yesterday_ids` is recorded each poll but nothing reads it yet.
- Side-by-side takeover: only THIS card freezes (`_x_shift`); the widget to its left keeps
  scrolling under the celebration, so up to ~80 logical px of the neighbour pass unseen
  (documented in the README; freezing neighbours needs engine support).
- Scroll-mode takeover vs core's end-of-scroll hold: a win landing while the LAST card of a
  side-by-side scroll sits in `hold_at_end` is cut to the remainder of the section
  `hold_time` (default 3 s) and resumes on the next pass.

## Tests

- `test_import_purity.py` / `test_smoke.py` — public-surface tripwire; entry-point wiring and the
  ball emoji.
- `test_models.py` / `test_teams.py` — parsing (leaders, linescores, sparse and junk payloads),
  status lines, clutch, `final_event`, team table.
- `test_source.py` — host fallback, cadence, backoff, baseline, finals, yesterday's slate,
  vanished games, schedule. Fake session + injected clock; no network.
- `test_scores.py` — `validate_config`, selection per mode, demo, stale, persistent cards, final
  queueing.
- `test_celebration.py` — timeline, flash/detail renderers, card lifecycle.
- `test_logos.py` / `test_paint.py` / `test_emoji.py` — logo decode and fallback, paint helpers,
  the ball.
- `test_resolve_layout.py` / `test_card_dispatch.py` — resolver; scale dispatch.
- `test_layout_scoreboard.py` / `test_layout_crawl.py` / `test_scoreboard.py` — physical and
  bitmap renderers, the clearance tripwires, ticker wording.
- `test_examples.py` — example configs validate, use `PHI`/`NY`, and the README documents every
  option and states `small_font` is not accepted.

CI (`.github/workflows/ci.yml`): Python 3.14, `uv sync --extra dev`, ruff check + format
check, pyright on `src`, pytest with coverage (`fail_under = 90`).
