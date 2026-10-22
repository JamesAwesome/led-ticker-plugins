# Hockey scores widget: design

**Date:** 2026-10-22
**Status:** approved in brainstorming; ready for planning
**Package:** `plugins/hockey/` → `led-ticker-hockey`, namespace `hockey`, widget `hockey.scores`
**Mockups:** `2026-10-22-hockey-mockups/live-board.html` (live board) and `states.html` (goal, final, next game). Open either file in a browser. These HTML fragments were written for the brainstorm companion, so standalone they render unstyled, but the canvases draw correctly.

## Intent

This adds live NHL scores to the sign, built the same way as the existing `tennis.scores` and `baseball.scores` plugins. It is a feature for the sign, not an attempt to compete with a phone app. It has to feel like hockey on the panel: clock, period, power play and, above all, a goal celebration. It must work on all three reference signs: **smallsign** (160×16, scale 1), **bigsign** (256×64, scale 4) and **longboi** (512×64, scale 4).

The preferred example teams, used in docs, demo data and example configs, are the **Philadelphia Flyers (`PHI`)** and the **New York Islanders (`NYI`)**.

## Prior art (researched)

- **riffnshred/nhl-led-scoreboard**: the best-known project. It was archived in May 2024 after a small change in the NHL feed broke it, and that risk drives our degrade-don't-die rule.
- **joshkay/nhl-led-scoreboard**: one favourite team on a 64×32 panel. It plays a goal GIF and updates about once a minute. It notes that the sign shows goals before TV does.
- **gidger/rpi-led-sports-scoreboard**: shows all games, then the favourite team's next game, then standings. It marks a new goal by turning the score red and fading it back. It does not run on a Pi 5.
- **Adafruit Matrix Portal scoreboard**: an ESP32 board using ESPN's feed, which is a possible backup data source.

None of these shows power-play state, and none designs for a 16-row strip or a 512-wide board. Those are our differentiators.

## Goals

1. Live score, period and clock, intermission, shots on goal, and the power play (team plus time remaining), with `EN` when a goalie is pulled.
2. A goal celebration that plays **when the widget's turn comes around**. It never interrupts other content.
3. Final states `FINAL`, `FINAL/OT` and `FINAL/SO`, with the winner highlighted, held for `final_hold_hours`.
4. Next game shown when a tracked team isn't playing today.
5. Three modes: `teams`, `league` and `live` (see below).
6. Purpose-designed layouts for each reference sign, matching the mockups.

## Non-goals

- Interrupting or pre-empting other widgets or sections when a goal is scored. This needs core engine work and was explicitly declined.
- Standings, player stats, playoff brackets and play-by-play crawls. These are possible later widgets (`hockey.standings`, …), not part of this one.
- A TV-sync or spoiler delay. Prior art says sync is impractical. *(My call to defer. It is a possible later knob.)*
- Leagues other than the NHL.

## Anti-goals (a failure even if it "works")

- The panel freezes, or the app crashes, because the unofficial feed changed shape. A bad payload must degrade to the last good data marked `STALE`. A crash would repeat riffnshred's failure.
- Overlapping or clipped text on any of the three signs (the CONTRIBUTING layout invariant, as in tennis).
- Inferring a final result from a game disappearing out of the feed.
- A celebration for the same goal on every rotation.

## Data source

The source is the NHL's public web API at `https://api-web.nhle.com`. It is free and needs no key. It is unofficial and undocumented (community reference: github.com/Zmalski/NHL-API-Reference), so the parser must be defensive.

| Endpoint | Use |
|---|---|
| `/v1/score/{YYYY-MM-DD}` (or `/now`) | The day's games: `gameState`, `period`, `periodDescriptor.periodType` (`REG`/`OT`/`SO`), `clock{timeRemaining, running, inIntermission}`, team `abbrev`/`score`/`sog`, `gameOutcome.lastPeriodType`, `startTimeUTC`, `venue`, and `goals[]` (scorer, `goalsToDate`, assists, `strength` ev/pp/sh, `goalModifier` e.g. empty-net, period, time). |
| `/v1/gamecenter/{id}/landing` | Live situation (power play, time remaining, empty net). **Unverified:** no live game was on during research. The builder must confirm the field names (believed to be `situation{homeTeam/awayTeam.situationDescriptions, situationCode, timeRemaining}`) against a live game, or a saved live fixture, before relying on them. If it's absent, the fallback is the play-by-play `situationCode`. |
| `/v1/club-schedule/{TEAM}/week/now` (or `month`) | The next game for each tracked team in `teams` mode. |

Observed `gameState` values: `FUT`, `PRE`, `LIVE`, `CRIT`, `FINAL` and `OFF`. The builder should confirm the set from the reference and treat unknown states as non-live.

**Polling** *(my call; the builder may tune it)*:
- Every ~15 s while any relevant game is `LIVE`/`CRIT`. "Relevant" means a tracked team in `teams` mode, or any game in `league`/`live` mode.
- Every ~5 min when relevant games are scheduled today but not started.
- About hourly otherwise.
- The landing call is made only for live relevant games that are on screen.

One shared source per process (tennis's `shared_source` shape), so several hockey widgets don't multiply requests. Failures keep the last good data and add a visible `STALE` label next to the state, never in place of it. Backoff follows the tennis ladder.

**Clocks tick locally between polls** *(my call)*. The model stores the poll timestamp with `clock.running`. While running, the game clock, the PP time and the intermission countdown are drawn as `polled_value − (monotonic_now − poll_time)`. They clamp at `0:00` and hold there until the next poll. When `running` is false (stoppage), the polled value is shown as-is. Reading a monotonic clock in `draw()` is acceptable for this; the frame-counter rule applies to the celebration animation. The time source is injected so tests can control it.

**Day boundary:** a game belongs to its local date in the widget's `timezone`. While a final is inside `final_hold_hours` across midnight, also fetch the previous date.

## Modes

| `mode` | Shows |
|---|---|
| `"teams"` (default) | Only games involving `teams` (e.g. `["PHI", "NYI"]`): live, then final, then next game for each team with no game today. When two tracked teams play each other, that's one card, not two. |
| `"league"` | Every NHL game today: tracked teams first, then other live games, then finals, then not-yet-started. |
| `"live"` | Like `league` but only games in progress. With nothing live, `feed_stories` is empty, so the rotation skips it. (Core never visibility-checks the container itself, only its stories, so an empty story list is the mechanism, not `should_display()`.) |

Each game is one story (one card) in the widget's rotation, the same Container/`feed_stories` shape as tennis and baseball.

**`teams` mode story selection, per tracked team** *(my call)*:
- **Live game today:** the live card.
- **Game later today (`FUT`/`PRE`):** the next-game card, with `TODAY` (or `TONIGHT` after 5 PM local) in place of the date. No separate pregame layout.
- **Final inside `final_hold_hours`:** the final card *replaces* the next-game card until the hold expires, then the next-game card returns.
- **Nothing in the week/month window** (All-Star or Olympic break, offseason): fall back to `/v1/club-schedule-season/{TEAM}/now` for the next game, e.g. the season opener. That fetch is made at most about every 6 h. If no game is scheduled at all, the team contributes no story. A section holding only this widget can therefore go dark in the offseason; the README must say so.

## Config surface

Same conventions as tennis and baseball. *(These fields are my call; the names follow the sibling plugins.)*

| Option | Default | Notes |
|---|---|---|
| `mode` | `"teams"` | `teams` / `league` / `live` |
| `teams` | `[]` | NHL abbreviations, case-insensitive. Required and non-empty in `teams` mode; in other modes it sets priority and celebrations. Unknown codes are rejected at validate time with a close-match hint (tennis uses `difflib`). |
| `layout` | `"auto"` | `auto` / `scoreboard` / `ticker`. `auto` → `scoreboard` on all three signs (the approved mockups show a held board on the smallsign too). `ticker` = one scrolling line per game. |
| `max_games` | `8` | Cap per rotation in `league`/`live` modes. |
| `final_hold_hours` | `6` | As in baseball. |
| `timezone` | `"America/New_York"` | For start times and the day boundary. |
| `update_interval` | — | Optional override of the live poll interval, floored at ~10 s. |
| `demo` | `false` | Fixture games (live PP, goal, intermission, OT final, next game) using PHI/NYI, with no network. Used for docs, gifs, hardware checks and tests. |
| `padding`, `bg_color`, `font_color`, `font`, `small_font` | as tennis | Scale-1 / ticker only. The physical renderers use a fixed palette. |

## Look

Treat the mockups as the spec for arrangement, hierarchy and color. Exact pixel positions and font sizes are the builder's to finalize under the layout invariant.

**Palette:** one hue per data field, as in baseball and tennis:
- Team: name in brand color with a two-tone brand chip (all 32 teams need a chip/color table, lifted for LED brightness the way baseball's `MLB_TEAM_CHIPS` are).
- Scores white. Period amber. Clock white. Shots on goal cyan. Power play amber, with an amber **PP** badge holding unlit (knocked-out) text. Dividers and labels dim gray.
- Final: the winner's score green, the loser's dimmed.

Black is invisible on these panels, so dark brand colors must be lifted (see the core memory on LED quirks).

### Per sign (live state)

- **Smallsign (160×16, bitmap font, scale 1):** two 8-row bands, one per team (away on top). Each band: a 3-px brand chip, the abbreviation, the score, `SOG nn`. `PP m:ss` sits on the power-play team's band. Period is right-aligned in the top band, clock in the bottom band.
- **Bigsign (256×64):** two held rows, one per team, with a dotted divider. Each row: chip, abbreviation (brand), score (large, white), `SOG nn` (cyan). The **PP** badge sits on the power-play team's row. The right status column shows period (amber), clock (white) and `PP m:ss` (amber).
- **Longboi (512×64):** a full scoreboard. The away team fills the left third (chip, large abbreviation, `SOG` below, huge score), the home team mirrors it on the right, and the center holds period, a large clock, and the **PP** badge with `TEAM m:ss` beneath.

### Other states

- **Intermission:** the live board, with the clock replaced by `2ND INT` and the intermission countdown.
- **Empty net:** `EN` in place of, or beside, the PP badge on the team that pulled its goalie *(placement is the builder's call)*.
- **Final:** the same board. Status reads `FINAL`, then `OT`/`SO` when applicable. The winner's score is green.
- **Next game (`teams` mode):** both teams' chips and names, `@` between them, day and date in amber, time in white, arena dimmed. Bigsign adds a small `NEXT GAME` label. Longboi adds the team nicknames under the abbreviations.
- **Ticker layout:** one line per game using the same wording as the boards. Like tennis's `segments()`, the scale-1 and hi-res crawl paths must use one wording source so they can't drift.

## Goal celebration

Shown in the mockups (`states.html` §1, animated). Behavior:

- **Detection:** compare each game's `goals[]` (or score) against the previous poll. A new goal by a **tracked team** queues a celebration on that game's card.
- **First sight is a silent baseline** *(my call)*. Goals already in the feed the first time a game is seen don't celebrate. "First sight" covers boot, restart, hot-reload, and a game first seen mid-period. No persistence across restarts; missing a goal scored just before a restart is accepted.
- **Where the state lives** *(my call)*. The shared source owns the per-game "goals seen" baseline, keyed by game id plus goal identity (period + time + scorer). Each widget/card owns its own "celebrated" set. A goal therefore celebrates once on every widget that shows that game, never twice on the same one.
- **Playback:** on the card's next turn, it plays once for about 4 s:
  - Three quick flashes of the full panel in the scoring team's color, with `GOAL` knocked out.
  - Then the new score with the scoring team's number pulsing, the scorer and season goal count (`KONECNY (5)`), the assists, and the period and time of the goal.
  - Then the normal board for the rest of the hold.
  - The celebration is consumed when it plays. It never repeats on later turns.
- **Several goals between turns:** celebrate in order, up to 3 per turn. Older ones beyond that are dropped.
- **Non-tracked teams' goals** (in `league`/`live` modes): no flash. The new score is drawn highlighted and fades back to white on that turn (gidger-style).
- **Overturned goals** (the score goes down, or a goal disappears): quietly correct the score. No un-celebration, and drop any queued celebration for that goal.
- **Hold time:** the section's hold must accommodate the celebration plus a readable board. Builder's call whether the card extends its own hold while a celebration is pending, for example by returning an overflowing cursor or becoming a `play()`-style story, or whether it documents a minimum `hold_time`. The animation must advance per tick through the frame counter (core constraint #12), and must not depend on wall-clock reads inside `draw()` that break during transition compositing (`pause_frame`).

## Constraints

- Everything in the led-ticker-plugins conventions applies: public surface only (`led_ticker.plugin`), no `from __future__ import annotations`, Python 3.14, `led-ticker-core >= 4.30`, ruff, pyright, and ≥90% coverage.
- The layout invariant: measured widths, ≥6 px clearance, row-uniform shrink ladders, ellipsis at the floor. Add a worst-case-clearance tripwire like tennis's `test_worst_case_keeps_min_clearance`. Worst case: longest abbreviations, double-digit scores, `SOG 99`, `PP` + `EN`, `FINAL/SO`.
- Hi-res text is never pixel-pinned in tests (freetype differs across platforms).
- The fetcher never raises into the poll loop. All network and parse errors become stale-state.
- Package shape mirrors tennis: `scores.py` (widget), `_source.py` (fetcher), `_models.py` (pure parse and helpers), `_card.py` (scale-dispatching story), `_scoreboard.py` (scale-1), `layouts/`, `_palette.py`, `_paint.py`, `teams.py` (32-team table), plus `README.md`, `CLAUDE.md`, `examples/config.hockey-{demo,live}.{smallsign,bigsign,longboi}.toml`, and a `Makefile`.
- Tests use saved JSON fixtures for every game state, including a real live payload captured once the landing fields are verified. No network in CI.

## Left to the builder

- Exact pixel geometry, font sizes and shrink ladders per sign, within the mockups' arrangement and the layout invariant.
- How the celebration gets enough hold time (see above).
- Poll intervals within the stated spirit (fast while live, slow otherwise).
- `EN` placement. Scale-1 handling of the celebration (a bitmap flash then the bands, as mocked, is the default).
- Whether a docs-site page lands in this PR or a follow-up. The README and examples are required.
