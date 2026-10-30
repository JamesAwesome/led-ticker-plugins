# CLAUDE.md

Guidance for Claude Code when working in **led-ticker-football**, a plugin for
[led-ticker](https://github.com/JamesAwesome/led-ticker) in the first-party pack.

`README.md` is the source of truth for the user-facing surface (options, modes, layouts,
cadence). This file keeps the **load-bearing invariants** a contributor must respect, plus
navigation aids. When the two disagree about *how a feature works*, the README wins; this
file is the source of truth for *how to keep it working*.

## Overview

One widget, `football.scores`, contributed via the `led_ticker.plugins` entry point
(namespace `football`, see `register()` in `__init__.py`): live NFL games from ESPN's
public, unofficial site API (`https://site.api.espn.com`, mirror `site.web.api.espn.com`,
**no key**), one story per game, modes `teams` / `league` / `live`, `layout = "auto"`
(default) / `"scoreboard"` / `"ticker"`. `auto` resolves to `scoreboard` on all three
signs. Scale 1 renders through the bitmap classes in `_scoreboard.py`; scale>1 dispatches
through `FootballGameCard` (`_card.py`) to the physical renderers in `layouts/`. Example
teams everywhere are `PHI` and `NYG`. The package is a file-for-file sibling of
`plugins/hockey/`; its CLAUDE.md invariants hold here too unless restated below.

## Commands

```bash
uv sync --extra dev                                            # repo root
uv run pytest plugins/football --cov=plugins/football/src      # suite (asyncio_mode = "auto")
uv run ruff check plugins/football && uv run ruff format --check plugins/football
uv run pyright plugins/football/src
```

Python **3.14+** only (no `from __future__ import annotations`). `led-ticker-core >= 4.30`.

## Invariants

**Import purity** — import `led_ticker` ONLY from `led_ticker.plugin`. AST tripwire:
`tests/test_import_purity.py`.

**The source never raises** (`_source.py`) — every network and parse error becomes
`stale` + backoff (2x interval, doubling, capped at 4 h); a bad payload keeps the last
good games. A game that drops out of the week payload keeps its last state until
`last_seen` passes the hold: NEVER infer a final from a game disappearing.

**Host fallback happens inside one poll** — `_get` tries `HOSTS` in order (`site.api`,
then the `site.web.api` mirror) and only the LAST host's failure propagates; a 403 on the
first host is not a stale snapshot (`test_host_fallback_on_403`). Never collapse the list
to one host: the mirror is what survived the August 2026 403s.

**One scoreboard request per poll; never fetch `summary`** — the week payload carries
every live `situation`, so `note_displayed` gates nothing. The per-team `schedule`
endpoint is fetched at most every `SCHEDULE_INTERVAL` (6 h) and ONLY for a tracked team
with no live/upcoming game in the week payload (`_playing`; a HELD final still fetches, so the
next-game card is ready the moment the hold expires between idle polls —
`test_schedule_fetched_while_a_final_is_held`). The ~560 KB
`summary?event=` endpoint is deliberately unused.

**Scoring is DERIVED from score deltas; `lastPlay` only decorates** — the scoreboard has
no play list. `_models.diff_scores` is the ONE table (+6/+7/+8 TD, +3 FG, +2 safety or
two-point follow-up, +1 PAT follow-up, negative = correction). `situation.lastPlay`
supplies the play text when its `scoreValue > 0` and team match, never the decision.
The first sight of a game is a silent baseline (`_prev` seeded, no plays).

**A try re-keys its touchdown** — a +1/+2 after a TD with no `extra` becomes a
`follow_up` (`diff_scores`): the source REPLACES the open TD in `_plays` at the new key,
the widget classifies it `changed` because `pre_extra_score(play, game.home)` (the
snapshot minus the try) is already in `_celebrated_scores`, and the card's `_swap` matches
on the same pre-try snapshot. All three must use `pre_extra_score`; hockey's same-score
rule would celebrate the extra point as a second touchdown
(`test_pat_follow_up_merges_into_touchdown`, `test_follow_up_replaces_pending_play`).

**Polling is widget-driven** — `shared_source(session)`; every widget's `want()` merges
into it, and cadence is the source's (15 s live — or the fastest widget `update_interval`
below that, via `want(live_interval=...)` — / 60 s around a kickoff / 300 s pregame /
3600 s idle, `MIN_INTERVAL` 10 s floor). The source only polls when a widget's `update()`
calls it, and each widget's monitor loop runs every `max(MIN_INTERVAL, update_interval)` s,
so an interval above 15 slows that widget (and a lone widget's polling).

**Possession is held across dead balls, nothing else is** — `_hold_possession` carries
the previous poll's `possession` only while `status == STATUS_IN_PROGRESS` in the SAME
period; halftime / end of period / a period change / a final clear it. Down & distance and
the spot are never held: an absent value draws nothing (`test_possession_held_across_dead_ball`).

**Clocks are not ticked locally** — the feed has no running flag and the clock stops after
most plays; renderers show `game.clock` (`displayClock`) as polled. Do not port hockey's
`live_clock_seconds`.

**First-sight baseline lives in the source; celebrated state lives on the widget/card**
— `ESPNSource.plays_after_baseline(game_id)` is NON-consuming. Each `FootballScoreMonitor`
keeps its own `_celebrated` / `_celebrated_scores` with a per-widget first-sight baseline,
so a hot reload with a surviving shared source is silent and every widget celebrates a
score exactly once.

**Cards are persistent** — one `FootballGameCard` per game id (or `next:TEAM`), kept in
`_cards` across polls; `_rebuild` reassigns `game` / `stale` / `bye` in place. Never
rebuild cards per poll: celebration state, frame counters and the legacy story cache live
on them. `bye` is set only on `next:` cards whose team is in `snap.bye_teams`.

**`reset_frame` consumption** (`_card.py`) — the celebration plays from a snapshot
(`_playing`) taken at visit-entry `reset_frame()`. A play is consumed only once it was
actually DRAWN on a live (unpaused, `_frame_count > 0`) frame (`_shown`). Plays queued
mid-visit wait for the next turn. Non-tracked scores highlight instead; empty `teams`
means no celebrations. Scroll-mode sections (`ticker`, `one_at_a_time`) never call
`reset_frame()`, so with no snapshot (`_playing is None`) the first live draw SELF-STARTS
a run (`_run_start` = that `_frame_count`). Its phase is `_run_pos`, which advances once
per frame the card is actually DRAWN (deduped by `_frame_count`), never by
`_frame_count - _run_start`: core advances every buffered widget each tick but stops
drawing once the cursor reaches the width, so a run hidden behind another card's takeover
must not burn out unseen. The draw after its last frame consumes it exactly as
`reset_frame` would, sets `_playing` and `_run_start` back to None and paints the board;
the next live draw may self-start again. An extra point arriving mid-run still folds into
the running touchdown (`_swap` walks `_playing` too). `reset_frame` always sets
`_run_start = None` (visit runs start at frame 0), so the slideshow path never
self-starts; a PAUSED reset (a transition's — they pause first) takes no `_playing`
snapshot, so a scroll section's first card after a section transition still self-starts
(`test_paused_reset_leaves_no_visit_snapshot`). Every celebration frame is a full-panel
takeover: it first fills the real panel (`bg_color`, else black), because in a side-by-side scroll core
resets once per tick and earlier widgets have already painted; it returns a
`canvas.width` cursor, so later widgets are skipped for the tick. The scroll position
keeps moving beneath it. `hold_time` is not read in scroll modes.

**`hold_time` property** — `base_hold` with nothing due; with `n` celebrations due it is
`n * CELEBRATION_SECONDS` (4 s) + `max(base_hold, BOARD_FLOOR)` (4 s). Core reads it as
`max(section_hold, getattr(story, "hold_time", 0.0))` right AFTER `reset_frame()`.

**Celebration paints only on live frames** — `_celebrate` returns False (the board draws)
while `_frame_paused` (transition compositing).

**Demo re-arm** — demo live cards carry `demo_plays`; `reset_frame` re-queues them after
every `DEMO_EVERY` (3) COMPLETED visits (`_frame_count > 0` at reset, so a transition's
extra `reset_frame` before `_show_one`'s is not counted). Scroll-mode sections have no
visits: a self-started run's end records `_demo_rest_from`, and the demo re-queues once
`DEMO_REST_FRAMES` (3 x 80 = 240, 12 s) live frames pass with nothing pending.

**`run_monitor_loop(..., splay=False)`** — core's default splay adds a fixed random
0–60 s to the poll interval at startup, which turned the 15 s live cadence into 29 s
on hardware. The shared source rate-limits itself (`_next_allowed`), so the widget
loop must not add jitter (`test_start_registers_interest_updates_and_spawns`).

**`segments()` in `layouts/crawl.py` is the single wording source for the ticker** — the
hi-res crawl paints it and the scale-1 `SegmentMessage` joins the same list.

**Every `draw()` honours `cursor_pos` and `y_offset`** — the scale>1 scoreboard paints at
`cursor_pos` (`render_scoreboard(..., x_offset=)`, via `_paint.ShiftedReal`), the crawl at
`cursor_pos + w + padding`, and the smallsign band board offsets every x by `cursor_pos`
and every shape row by `y_offset` (`test_band_board_honours_cursor_pos`,
`test_band_board_shapes_follow_y_offset`); each returns `cursor_pos + <its width>`; a constant `canvas.width` return never goes negative, so a
`ticker` / `one_at_a_time` section wedges on the first card forever
(`test_scale4_scoreboard_scrolls_with_cursor_pos`). A self-started celebration run freezes
the card's EFFECTIVE cursor (`_x_shift`, cleared when the raw cursor next increases = a
fresh pass) because the engine keeps decrementing `pos` under the takeover
(`test_scroll_mode_run_freezes_cursor_until_next_pass`).

**Layout invariant (CONTRIBUTING.md)** — measured widths (`_paint.text_width`), >= 6 px
(`_MIN_GAP`) between texts/shapes sharing a vertical band, row-uniform name sizes,
ellipsis at the floor. The situation line drops ` · spot` BEFORE ellipsizing so the down &
distance is never cut (`_situation_text`). **Tripwire:**
`tests/test_layout_scoreboard.py::test_worst_case_keeps_min_clearance` (`WSH 48 @ JAX 48`,
`1ST & GOAL · WSH 50`, red zone, three pips each, `END Q3`, `FINAL/OT`, a `TBD` bye-week
next game, `STALE`) on both physical signs; it spies `rect()` / `triangle()` / `pips()` /
`_dotted()` so the chips, possession triangle, timeout pips and divider keep >= 6 px from
any text sharing their rows. The smallsign twin is
`tests/test_scoreboard.py::test_band_board_worst_case_clearance`, fed by the band board's
`shape_extents`. The smallsign sport icon (`:football.ball:`, `emoji.BALL`) is in
`shape_extents` as `"ICON"`; it may sit `_ICON_GAP` (2 px) from the text it labels (the
quarter on a live/final card, the matchup on a next game) and keeps >= 6 px from everything
else, and it is the element that is LEFT OUT when it cannot (never the score, clock or
status). The bigsign celebration detail puts `+PAT` on its own bottom row because
`TOUCHDOWN` plus the score run cannot share row 1.

**Logos are bundled assets, never fetched** (`_logos.py`) — 32 64x64 RGBA PNGs under
`assets/logos/` with `MANIFEST.txt` (source URL + fetch date per file). A human refreshes them
with `tools/fetch_logos.py`; CI, tests and the sign never run it, and the render path never
makes an image request. Same module shape as the basketball plugin: `_logos.sprite(abbrev,
size)` is `functools.cache`'d per (team, size), drops alpha < `ALPHA_MIN` and near-black
(< `DARK_FLOOR`) pixels, and returns None for an unknown team or an undecodable asset — it
NEVER raises. Sizes: `LOGO_ROW` 28 (bigsign, one per 32 px team row — the board AND the
celebration detail, where the logo sits in the BOTTOM row beside the play because
`TOUCHDOWN` needs the top row's full width left of the score run), `LOGO_LONG` 48 (longboi
board edges and detail). A logo REPLACES
the chip in place (`_slot`); when it can't be drawn (`logos = false`, missing sprite) the chip
goes in and that side's abbrev moves back to `name_x` — per SIDE, so one missing logo never
shifts the other team. On the bigsign next-game card the home logo rides inside the name run
(its width is in the run's `fixed`); the longboi next card keeps the chip-era name limits so
a logo eats the names' budget, never the centre column's. Smallsign never shows logos.
Tripwires: `test_logos.py`, `test_logos_replace_both_chips`, `test_logos_false_paints_chips`,
`test_missing_sprite_falls_back_to_chip`, `test_one_missing_logo_keeps_the_other`,
`test_detail_paints_scoring_team_logo_clear_of_text`, and `test_worst_case_keeps_min_clearance`
parametrized over `logos`.

**Every team logo is an inline emoji** (`register` → `_logos.emoji(abbrev)`) — `:football.<team>:`
(lower-case code), a lo-res + hi-res pair per team, because inline text resolves through the
lo-res registry and a hi-res-only slug renders as literal text. `emoji` crops to the alpha
bbox and fits aspect-preserving (`_decode_fit`): hi-res `EMOJI_HIRES` 32 tall (core's inline
sprite height) up to `EMOJI_HIRES_MAX_W` 64 wide, lo-res within 8×8 with the lenient
`TINY_ALPHA_MIN` and no premultiply (the board's square resize + thresholds leave wide marks —
WSH, NYJ — blank at 8×8). Both are trimmed flush left with `physical_width` set: core
auto-trims its OWN hi-res emoji but stores plugin ones as given. `emoji` is cached and NEVER
raises; a team whose pair is None is skipped, never fatal to `register` (a raise there drops
the whole plugin, widget included). It does not share `sprite`'s cache or thresholds — keep
the board's look and the emoji's tuning independent.

**Hi-res text is never pixel-pinned in tests** (freetype differs macOS vs Linux) — assert
extents, bands, ordering and colors.

**Palette is one hue per field** (`_palette.py`) — white score/clock/lit pips, amber
quarter/date/kickoff/`+PAT`, cyan down & distance and spot, RED reserved for the red zone
(situation text and the possession marker), dim labels/spent pips, green final winner,
gray loser/records. Black is invisible on the panels, so team chips are lifted; near-black
NFL primaries (`LV`, `PIT`, `HOU`, `CHI`, `DEN`) use the lifted secondary as primary.
`bg_color` fills at EVERY scale: core fills `getattr(widget, "bg_color", None)` before
every draw (`reset_canvas`), no football renderer clears the panel, and the celebration's
takeover fills it explicitly — so `FootballGameCard.bg_color` is a plain field (the
#105 ScaleMemo / scale-1-only machinery was removed; `test_core_fill_of_bg_color_survives_every_scale`).
`font_color` reaches only the scale-1 ticker message.

## Known gaps

- The live `situation` fixture is hand-written from the community-documented shape and a
  captured preseason dead-ball payload; no regular-season live game was on during the
  build. Capture a real in-progress event as a fixture when one is on.
- `week.teamsOnBye` is read from the scoreboard; `byeWeek` from the schedule endpoint is
  the fallback. Both were confirmed on 2026-10-26 (Week 7: BUF/LAC/WSH/JAX; PHI bye 10).
- Side-by-side takeover: only THIS card freezes (`_x_shift`); the widget to its left keeps
  scrolling under the celebration, so when the run ends an up-to-80-logical-px gap opens
  between them and that much of the neighbour passed unseen. Freezing neighbours needs
  engine support; documented in the README instead.
- Scroll-mode takeover vs core's end-of-scroll hold: a score that lands while the LAST card
  of a side-by-side scroll sits in core's `hold_at_end` is cut to the remainder of the
  section `hold_time` (default 3 s) and resumes on the next pass (frames advance only
  when the card is drawn). No `hold_time` value avoids it.

## Tests

- `test_import_purity.py` / `test_smoke.py` — public-surface tripwire; entry-point wiring.
- `test_models.py` / `test_teams.py` — parsing (incl. the schedule's object scores, TBD
  kickoffs, dead balls), `diff_scores` table, `pre_extra_score`, team table.
- `test_source.py` — host fallback, cadence, backoff, baseline, follow-ups, corrections,
  possession hold, vanished games, schedule/bye. Fake session + injected clock; no network.
- `test_scores.py` — `validate_config`, selection per mode, demo, stale, persistent cards,
  play queueing.
- `test_logos.py` — logo decode, floors, fallback, cache, clipping.
- `test_celebration.py` — timeline, flash/detail renderers, card lifecycle.
- `test_resolve_layout.py` / `test_card_dispatch.py` — resolver; scale dispatch.
- `test_layout_scoreboard.py` / `test_layout_crawl.py` / `test_scoreboard.py` — physical and
  bitmap renderers, the clearance tripwires, ticker wording.
- `test_examples.py` — example configs validate, use `PHI`/`NYG`, and the README documents
  every option.

CI (`.github/workflows/ci.yml`): Python 3.14, `uv sync --extra dev`, ruff check + format
check, pyright on `src`, pytest with coverage (`fail_under = 90`).
