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
`stale` + backoff (2x interval, doubling, capped at 4 h); a bad payload keeps the last
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

**Next game vs `_games` share ONE hold predicate** — `_models.final_in_hold` (with
`GAME_LENGTH`) is used by both `scores.select_stories` and `NHLSource._playing`. A team
skips the next-game lookup (and its `next_games` entry is dropped) only while it has a
LIVE game or a final inside the hold at the SHORTEST widget hold (`_next_hold_hours`). A
future game never counts — a post-midnight game is not "later today" and must come from
the lookup. Diverge the two and a team's card vanishes after its final's hold
(`test_next_game_returns_after_final_hold`).

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
a run (`_run_start` = that `_frame_count`; phase = `_frame_count - _run_start`) and the
draw after its last frame consumes it exactly as `reset_frame` would, sets `_playing` and
`_run_start` back to None and paints the board; the next live draw may self-start again.
`reset_frame` always sets `_run_start = None` (visit runs start at frame 0), so the
slideshow path never self-starts. A self-started run is a full-panel takeover
(`canvas.width` cursor, later widgets skipped for the tick) while the scroll position keeps
advancing beneath it, so the crawl resumes ~80 px on. `hold_time` is not read in scroll
modes.

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
measured columns).

**Hi-res text is never pixel-pinned in tests** (freetype differs macOS vs Linux) — assert
extents, bands, ordering and colors.

**Palette is one hue per field** (`_palette.py`) — white score/clock, amber period/PP/date,
cyan SOG, dim labels, green final winner, gray loser. Black is invisible on the panels, so
team chips are lifted for LED brightness.
`bg_color` never paints at scale > 1 (hi-res board, crawl or goal celebration); at
scale 1 the band board, the ticker message and the goal detail fill it. `font_color`
reaches only the scale-1 ticker message.

## Known gaps

- The landing `situation` field shapes (power play, empty net) come from community docs and
  are unverified against a live game; capture a real payload as a fixture when one is on.
- The scale-1 `ticker` layout's clock text updates per poll; boards and hi-res tick per second.

## Tests

- `test_import_purity.py` / `test_smoke.py` — public-surface tripwire; entry-point wiring.
- `test_models.py` / `test_teams.py` — parsing (incl. garbage rows), team table and codes.
- `test_source.py` — cadence, gate, shared source, baseline, backoff, never raising.
  Fake session + injected clock; no network.
- `test_scores.py` — `validate_config`, selection per mode, demo, stale, persistent cards.
- `test_celebration.py` — timeline phases and renderers.
- `test_resolve_layout.py` / `test_card_dispatch.py` — resolver; scale dispatch; consumption.
- `test_layout_scoreboard.py` / `test_layout_crawl.py` / `test_scoreboard.py` — physical and
  bitmap renderers, the clearance tripwire, ticker wording.
- `test_examples.py` — example configs validate, use `PHI`/`NYI`, and the README documents
  every option.

CI (`.github/workflows/ci.yml`): Python 3.14, `uv sync --extra dev`, ruff check + format
check, pyright on `src`, pytest with coverage (`fail_under = 90`).
