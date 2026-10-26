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
with no live/upcoming/held game in the week payload (`_playing`). The ~560 KB
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
means no celebrations.

**`hold_time` property** — `base_hold` with nothing due; with `n` celebrations due it is
`n * CELEBRATION_SECONDS` (4 s) + `max(base_hold, BOARD_FLOOR)` (4 s). Core reads it as
`max(section_hold, getattr(story, "hold_time", 0.0))` right AFTER `reset_frame()`.

**Celebration paints only on live frames** — `_celebrate` returns False (the board draws)
while `_frame_paused` (transition compositing).

**Demo re-arm** — demo live cards carry `demo_plays`; `reset_frame` re-queues them after
every `DEMO_EVERY` (3) COMPLETED visits.

**`segments()` in `layouts/crawl.py` is the single wording source for the ticker** — the
hi-res crawl paints it and the scale-1 `SegmentMessage` joins the same list.

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
`shape_extents`. The bigsign celebration detail puts `+PAT` on its own bottom row because
`TOUCHDOWN` plus the score run cannot share row 1.

**Hi-res text is never pixel-pinned in tests** (freetype differs macOS vs Linux) — assert
extents, bands, ordering and colors.

**Palette is one hue per field** (`_palette.py`) — white score/clock/lit pips, amber
quarter/date/kickoff/`+PAT`, cyan down & distance and spot, RED reserved for the red zone
(situation text and the possession marker), dim labels/spent pips, green final winner,
gray loser/records. Black is invisible on the panels, so team chips are lifted; near-black
NFL primaries (`LV`, `PIT`, `HOU`, `CHI`, `DEN`) use the lifted secondary as primary.

## Known gaps

- The live `situation` fixture is hand-written from the community-documented shape and a
  captured preseason dead-ball payload; no regular-season live game was on during the
  build. Capture a real in-progress event as a fixture when one is on.
- `week.teamsOnBye` is read from the scoreboard; `byeWeek` from the schedule endpoint is
  the fallback. Both were confirmed on 2026-10-26 (Week 7: BUF/LAC/WSH/JAX; PHI bye 10).

## Tests

- `test_import_purity.py` / `test_smoke.py` — public-surface tripwire; entry-point wiring.
- `test_models.py` / `test_teams.py` — parsing (incl. the schedule's object scores, TBD
  kickoffs, dead balls), `diff_scores` table, `pre_extra_score`, team table.
- `test_source.py` — host fallback, cadence, backoff, baseline, follow-ups, corrections,
  possession hold, vanished games, schedule/bye. Fake session + injected clock; no network.
- `test_scores.py` — `validate_config`, selection per mode, demo, stale, persistent cards,
  play queueing.
- `test_celebration.py` — timeline, flash/detail renderers, card lifecycle.
- `test_resolve_layout.py` / `test_card_dispatch.py` — resolver; scale dispatch.
- `test_layout_scoreboard.py` / `test_layout_crawl.py` / `test_scoreboard.py` — physical and
  bitmap renderers, the clearance tripwires, ticker wording.
- `test_examples.py` — example configs validate, use `PHI`/`NYG`, and the README documents
  every option.

CI (`.github/workflows/ci.yml`): Python 3.14, `uv sync --extra dev`, ruff check + format
check, pyright on `src`, pytest with coverage (`fail_under = 90`).
