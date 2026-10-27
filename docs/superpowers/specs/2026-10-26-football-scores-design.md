# Football scores widget: design

**Date:** 2026-10-26
**Status:** decided without a brainstorm (James opted out of the questions and asked to be guided); ready for planning
**Package:** `plugins/football/` → `led-ticker-football`, namespace `football`, widget `football.scores`
**Template:** `plugins/hockey/` (`hockey.scores`). Every invariant in `plugins/hockey/CLAUDE.md` is inherited unless this document says otherwise.

## Football in one page (for a reader who doesn't follow the sport)

This section exists so the rest of the document can be checked by someone who knows the sign but not the game.

- **The game.** Two teams, four **quarters** of 15 minutes each (`Q1`–`Q4`), a **halftime** break after Q2, and an **overtime** (`OT`) period if the score is tied after Q4. The clock stops constantly, so a game takes about three hours of real time. In the regular season OT is 10 minutes and the game can end in a tie.
- **Scoring.** A **touchdown** (TD) is 6 points; right after it the scoring team kicks an **extra point** (+1, "PAT") or tries a **two-point conversion** (+2). A **field goal** (FG, a kick through the posts) is 3 points. A **safety** is 2 points for the defense. So a team's score goes up by 6 then 1 (or 2), by 3, or by 2.
- **Possession.** One team has the ball at a time (the *offense*). They get four tries (**downs**) to move the ball 10 yards. "**3rd & 4**" means third try, 4 yards still to go. The ball's spot is written as "**PHI 38**": on PHI's half of the field, 38 yards from PHI's goal line. Within 20 yards of scoring the offense is in the **red zone** (a big moment, and the thing every open-source scoreboard highlights in red).
- **Timeouts.** Each team gets three per half. Scoreboards show them as three small bars.
- **The season.** 32 teams. Each team plays **once a week** for 18 weeks (17 games plus one week off, the **bye**), then a single-elimination postseason: Wild Card, Divisional, Conference Championship, Super Bowl. Most games are on Sunday (1 PM, 4 PM, 8 PM Eastern), plus one on Thursday night and one on Monday night; Saturdays appear late in the season, and Thanksgiving/Christmas have extra games.
- **Team codes.** Three letters or two: `PHI` (Philadelphia Eagles), `NYG` (New York Giants), `GB`, `KC`, `SF`, … ESPN's spellings are used throughout (`WSH`, `LAR`, `JAX`, `LV`, `LAC`).

The example teams in docs, demo data and example configs are the **Philadelphia Eagles (`PHI`)** and the **New York Giants (`NYG`)**, division rivals who play each other twice a year (the football analogue of hockey's `PHI`/`NYI`).

## Intent

Live NFL scores on the sign, built the same way as `hockey.scores`: one held card per game, a scoring celebration when a tracked team scores, final and next-game cards, three modes, purpose-designed layouts for **smallsign** (160×16, scale 1), **bigsign** (256×64, scale 4) and **longboi** (512×64, scale 4).

What makes it feel like football on the panel: quarter and clock, **who has the ball**, **down and distance** with the ball spot, **timeouts** remaining, the **red zone** lit in red, and a **touchdown celebration**.

## Prior art (researched 2026-10-26)

Every open-source LED football scoreboard uses ESPN's unofficial, keyless `site.api.espn.com` scoreboard feed. Features were taken from the popular ones:

- **mikemountain/nfl-led-scoreboard** (the best-known Pi project): quarter, clock, possession, down & distance from `shortDownDistanceText`, ball spot from `possessionText`; the team name turns **red in the red zone**; pregame shows the kickoff time; game priority is favourite team → live → upcoming → final.
- **tronbyt `retronfl`** (Tidbyt, 64×32, the most complete small-panel design): possession as a **dot** on the team row, **timeouts as up to three bars** per team, `HALF` / `OT` labels, a kickoff-time pregame, `FINAL` in yellow, `PPD`/`CANC`/`SUSP` handling, and a game chooser (held → live → recent within 18 h → next upcoming). It also hits the per-team schedule endpoint for the next game.
- **AustinReese/HomeCourt**: the only one with a **scoring celebration**: the play type and team blink in team colours, then the play text scrolls. Its detection compares the summary endpoint's `scoringPlays` length between polls.
- **robbydyer/sports** (Go, multi-sport): config ideas worth noting: `favoriteSticky`, `hideFavoriteScore` (a spoiler mode), `scoreHighlightRepeat` (a changed score stays highlighted red for N cycles).
- **Cornell ECE5725 scoreboard**: timeouts as dashes, possession as dots, celebration triggered when `situation.lastPlay` changes.
- **fewieden/MMM-NFL**: the cleanest status mapping (`pre` → pregame, `STATUS_HALFTIME` → halftime, `post` with `period > 4` → final/OT).

None of them designs for a 16-row strip or a 512-wide board, none shows timeouts *and* down-and-distance *and* a celebration together, and none handles a bye week beyond "no game". Those are the differentiators, as with hockey.

## Goals

1. Live score, quarter and clock, `HALF` / `END Q3` / `OT` / `DELAY`, possession marker, down & distance plus ball spot, timeouts remaining, red zone in red.
2. A scoring celebration (touchdown, field goal, safety) for a tracked team that plays **when the card's turn comes around**, never interrupting other content; the extra point folds into the touchdown's celebration silently.
3. Finals `FINAL` and `FINAL/OT` with the winner highlighted, held for `final_hold_hours`.
4. Next game when a tracked team isn't playing this week or has already played, with a `BYE WEEK` label when the team is on its bye.
5. Modes `teams` / `league` / `live`; layouts `auto` / `scoreboard` / `ticker`.
6. Works on all three reference signs under the layout invariant.

## Non-goals

- Interrupting other widgets on a score (core engine work; declined for hockey too).
- Standings, player stats, playoff brackets, win probability, betting odds, a play-by-play crawl. The payload carries odds and leaders; they are deliberately not shown. Possible later widgets (`football.standings`, …).
- A spoiler delay / hide-score mode (robbydyer's `hideFavoriteScore`). *My call to defer; a possible later knob.*
- Leagues other than the NFL (college football has the same ESPN shape under `football/college-football` and could be a `league` knob later; not now).
- Team logos. The panels are too small; two-tone brand chips as in hockey.

## Anti-goals

- A crash or frozen panel because the unofficial feed changed shape or returned 403. Bad data degrades to the last good games marked `STALE`.
- Overlapping or clipped text on any sign.
- Inferring a final from a game vanishing from the feed.
- Celebrating the same score on every rotation, or celebrating the extra point as a second event.

## Data source

ESPN's unofficial site API. Keyless, undocumented, `cache-control: max-age=10`, ~245 KB per scoreboard payload (gzip brings it to ~25 KB; aiohttp negotiates gzip by default). Community references: the akeaswaran gist (its comment thread is the live changelog of breakage), `pseudo-r/Public-ESPN-API`, `zuplo/espn-openapi`.

| Endpoint | Use |
|---|---|
| `GET /apis/site/v2/sports/football/nfl/scoreboard` (no params) | **The current week's games**, Thursday through Monday, in one payload. ESPN's week boundaries are Wednesdays around 07:00Z. Top level: `week.number`, `week.teamsOnBye[]`, `season.type` (1 pre, 2 regular, 3 post, 4 off), `leagues[0].calendar` (labels per week, incl. postseason round names), `events[]`. |
| `GET /apis/site/v2/sports/football/nfl/teams/{ABBR}/schedule` | Per tracked team: the full season schedule and `byeWeek` (an int). Used only for teams with no game in the week payload (bye) or whose game this week is already final past the hold: the next `state == "pre"` event is the next game. Fetched at most every 6 h per team. **Note the shape differs:** `competitors[].score` is an object `{value, displayValue}` (or absent pre-game), and `status` sits under `competitions[0]`. |

**Hosts.** `https://site.api.espn.com` first; on any HTTP ≥ 400 or network error the same path is retried once on `https://site.web.api.espn.com` (the mirror that stayed up in the August 2026 403 incident). Both failing is one `_fail` (stale + backoff). A descriptive `User-Agent` as in hockey.

**Not used:** the `summary?event=` endpoint (~560 KB per game; carries `scoringPlays[]`). Scoring is detected from the scoreboard's score deltas instead (below), enriched by `situation.lastPlay` which is already in the payload. This keeps a live poll at one request. *My call; cheaper on a Pi and one fewer unofficial endpoint to break.*

### Scoreboard field map (confirmed against the 2026-10-26 Week 7 payload)

Per event `e`, with `c = e.competitions[0]`:

- id `e.id` (string), `e.date` ISO Z (`"2026-10-27T00:15Z"`), `e.shortName` (`"DAL @ PHI"`), `e.week.number`, `e.season.type`.
- status `e.status`: `period` (0 pre, 1–4, 5+ OT), `displayClock` (`"9:11"`), `clock` (float seconds), `type.name` (`STATUS_SCHEDULED`, `STATUS_IN_PROGRESS`, `STATUS_HALFTIME`, `STATUS_END_PERIOD`, `STATUS_DELAYED`, `STATUS_SUSPENDED`, `STATUS_POSTPONED`, `STATUS_CANCELED`, `STATUS_FINAL`), `type.state` (`pre` / `in` / `post`), `type.completed`, `type.detail` / `shortDetail` (`"Final/OT"`, `"10/26 - 8:15 PM EDT"`, `"TBD"`), `type.altDetail` (`"OT"` on OT finals).
- competitors `c.competitors[]`: `homeAway`, `score` (**string**), `winner` (post only), `records[]{type:"total", summary:"5-2"}`, `linescores[]{value}`, `team{id, abbreviation, location, name, color, alternateColor}`.
- `c.venue.fullName`, `c.broadcasts[]{names[]}`, `c.neutralSite`.
- `c.situation` (**present only while live**): `possession` (a team **id** string; **absent at every dead ball**: timeouts, end of quarter, halftime, between a touchdown and the kickoff), `down` (int, `-1` at dead balls), `distance`, `yardLine`, `isRedZone`, `homeTimeouts` / `awayTimeouts` (ints 0–3, sometimes absent), `shortDownDistanceText` (`"3rd & 4"`, `"1st & Goal"`, `"PAT"`, `"Kickoff"`), `possessionText` (`"SF 38"`, `"50"`), `downDistanceText`, `lastPlay{type{text}, text, scoreValue, team{id}}`.

Quirks to encode:
- A game whose kickoff time isn't set yet carries `date` at `05:00Z` (midnight Eastern) and `shortDetail == "TBD"` (seen on PHI's Week 18 game). Show the date with no time when `shortDetail` is `TBD` or `detail` ends in `TBD`.
- `STATUS_DELAYED` has `state == "in"`; key on the status name before the state.
- Scores occasionally go **down** (a correction). Treat a negative delta as a correction, never a score.
- Everything is read with `.get` defaults; a pre-season `situation` has been seen with only `[awayTimeouts, distance, down, homeTimeouts, isRedZone, lastPlay, yardLine]`.

### Polling cadence (one shared source per session, as hockey)

- **15 s** while any relevant game is live (ESPN caches for 10 s; `MIN_INTERVAL` 10 s; a widget's `update_interval` below 15 speeds it up).
- **60 s** when a relevant game kicks off within 30 minutes. *My call: so the first poll after kickoff lands quickly and the celebration baseline is the 0–0 score.*
- **5 min** when a relevant game is scheduled later today (local date).
- **Hourly** otherwise (the rest of the week, the offseason).
- The per-team schedule fetch at most every 6 h.
- Backoff: 2× the cadence, doubling, capped at 4 h; a bad payload keeps the last good games marked stale. A game that drops out of the week payload keeps its last state until `last_seen` passes the hold.

**Clocks are not ticked locally.** *This differs from hockey, deliberately.* A football clock stops after most plays and the feed carries no "running" flag, so a locally ticking clock would be wrong more often than right. The board shows `displayClock` as polled.

## Model

`GameInfo` (frozen dataclass, the one shape every renderer consumes):

- `game_id: str`, `state: "future" | "live" | "final"`, `status: str` (the ESPN status name, for `HALF`/`END Q3`/`DELAY`/`PPD`/`CANC`/`SUSP`), `away`, `home` (abbreviations), `away_score`, `home_score`, `period: int`, `clock: str` (`displayClock`), `start_utc: datetime | None`, `time_tbd: bool`, `venue: str`, `broadcast: str` (first network name or `""`), `away_record`, `home_record` (`"5-2"` or `""`), `final_ot: bool`, `week: int | None`, `situation: Situation | None`, `polled_at: float`.
- `Situation`: `possession: str | None` (abbreviation, resolved from the team id), `down_distance: str` (`shortDownDistanceText` upper-cased, `""` when absent), `spot: str` (`possessionText` or `""`), `red_zone: bool`, `away_timeouts: int | None`, `home_timeouts: int | None`, `last_play: LastPlay | None` (`text`, `score_value`, `team`, `type_text`).
- `ScoringPlay` (built by the source from score deltas, see below): `key`, `team`, `kind` (`"TD" | "FG" | "SAFETY"`), `extra` (`"" | "PAT" | "2PT" | "PAT NO GOOD"`... keep to `""`, `"+PAT"`, `"+2PT"`), `text` (play description from `lastPlay` when it matched, else `""`), `period_label`, `clock`, `away_score`, `home_score`.

State mapping: `pre` → future; `in` → live; `post` → final. `STATUS_POSTPONED` → future with `time_tbd` and status label `PPD`; `STATUS_CANCELED` → final with label `CANC` and no winner; `STATUS_SUSPENDED` → live with label `SUSP`.

Status lines (`status_lines(game, now, tz) -> (line1, line2)`):
- live: `("Q3", "9:11")`; halftime `("HALF", "")`; end of period `("END Q3", "")`; delayed `("DELAY", "")`; OT `("OT", "4:02")`, later OTs `2OT`….
- final: `("FINAL", "OT" | "")`; canceled `("CANC", "")`.
- future: `(day_label, kickoff)` where `day_label` is hockey's (`TODAY`, `TONIGHT`, `SUN NOV 1`) and `kickoff` is `1:00 PM` or `TBD`; postponed `("PPD", "")`.

**Possession hold** *(my call)*: while the status is `STATUS_IN_PROGRESS` and the period hasn't changed, a poll with no `possession` keeps the previous poll's possession (dead balls between plays drop the key for a few seconds). Halftime, end of period, a period change, or a final clears it. Down & distance and the spot are **not** held: an absent value draws nothing.

## Scoring detection (in the source, shared by all widgets)

Per game the source keeps the last `(away_score, home_score)`. First sight is the silent baseline (boot, restart, hot reload, a game found mid-drive: nothing celebrates). On each poll, per team, `delta = new - old`:

| delta | meaning | action |
|---|---|---|
| 6 | touchdown, extra point pending | new `ScoringPlay(kind="TD")` |
| 7 | touchdown + extra point (collapsed in one poll) | new `TD`, `extra="+PAT"` |
| 8 | touchdown + two-point conversion | new `TD`, `extra="+2PT"` |
| 3 | field goal | new `FG` |
| 1 | the extra point after a `6` | **follow-up**: update that TD's score snapshot and `extra`; no new play |
| 2 | two-point conversion if the team's last play was a `TD` with no extra yet, else a safety | follow-up, or new `SAFETY` |
| < 0 | correction | drop any pending play whose snapshot the new score no longer supports (hockey's `drop_overturned`) |
| other | unknown (two scores inside one poll, e.g. TD + FG) | one new play of the larger kind with `extra=""`; never raise |

Enrichment: when `situation.lastPlay.scoreValue > 0` and `lastPlay.team` is the scoring team, `text` is the play text (`"A.J. Brown 23 Yd pass from Jalen Hurts"` → upper-cased, kick/conversion parenthetical stripped) and the kind is cross-checked against `lastPlay.type.text` (`"Field Goal Good"`, `"Rushing Touchdown"`, `"Safety"`). The delta decides; `lastPlay` only decorates.

Keys: `f"{game_id}:{away_score}:{home_score}"` of the play's **own** snapshot. A follow-up re-keys the pending play to the new snapshot (so the card's `_swap` replacement works exactly as hockey's scorer corrections). Baseline bookkeeping (`goals_after_baseline` → `plays_after_baseline`) and the widget-side `_celebrated` / `_celebrated_scores` maps carry over from hockey unchanged in shape.

## Celebration

Same timeline and plumbing as hockey (`_celebration.py`, `_card.py`: 80 frames = 4 s per play, max 3 queued, flash then detail, consumed only once shown on a live frame, `hold_time` property extends the hold, demo re-arm every third visit). Differences:

- The flash knocks out the word by kind: `TOUCHDOWN`, `FIELD GOAL`, `SAFETY`. (Smallsign: `TD!` / `FG!` / `SAFETY` in the bitmap font if the full word doesn't fit; measure.)
- Detail card: the kind in the team colour, the new score with the scoring team's number pulsing, the play text (ellipsized; may be empty), `Q3 9:11` dim, and `+PAT`/`+2PT` in amber when known.
- Non-tracked team's score → the score highlight fade (hockey's `highlight`), no flash.

## Modes

| `mode` | Shows |
|---|---|
| `teams` (default) | Per tracked team in config order: its live game; else a final inside `final_hold_hours`; else its game later this week (`pre` in the week payload); else its next game from the schedule endpoint (with `BYE WEEK` when `byeWeek == week.number`). Two tracked teams playing each other are one card. |
| `league` | Every game in the current week: tracked picks first, then live games, then finals inside the hold, then upcoming games by kickoff. Capped by `max_games`. *(Football's unit is the week, not the day; the whole slate is the natural "league" view.)* |
| `live` | Only games in progress, tracked first. Empty when nothing is live, so the rotation skips the widget. |

`final_hold_hours` **defaults to 24** *(my call: a team plays once a week, so Sunday's result stays interesting on Monday; hockey uses 6)*. `GAME_LENGTH` for the hold math is 3 h 30 min from kickoff. Offseason: a tracked team with nothing scheduled contributes no story; the README says a section holding only this widget goes dark then.

## Config surface

| Option | Default | Notes |
|---|---|---|
| `mode` | `"teams"` | `teams` / `league` / `live` |
| `teams` | `[]` | ESPN abbreviations, case-insensitive; required non-empty in `teams` mode; `difflib` close-match hint on typos (`"PHL"` → `Did you mean 'PHI'?`). |
| `layout` | `"auto"` | `auto` / `scoreboard` / `ticker`; `auto` → `scoreboard` on every sign. |
| `max_games` | `8` | `league` / `live` cap. |
| `final_hold_hours` | `24` | see Modes. |
| `timezone` | `"America/New_York"` | kickoff times, the day boundary. |
| `update_interval` | `15` | live cadence, floored at 10. |
| `hold_time`, `padding`, `demo`, `bg_color`, `font_color`, `font`, `small_font` | as hockey | |

## Look

Palette (one hue per field, `_palette.py`): `WHITE` score/clock, `AMBER` quarter/date/kickoff/`+PAT`, `CYAN` down & distance and spot, `RED (230, 40, 40)` red-zone down & distance **and** possession marker, `DIM` labels/dividers/timeout pips when used up, `GREEN` final winner, `LOSER` gray, `GRAY` `@`/records. Team chips: a 32-team table (`teams.py`) seeded from ESPN's `color`/`alternateColor` and **lifted** so every colour has a channel ≥ 90 (several NFL primaries are near-black: `HOU 021018`, `LV 000000`, `PIT 000000`, `CHI 0b1c3a`); where the primary is black the lifted secondary becomes the chip's main colour.

The possession marker is a small solid **triangle pointing at the team** (bigsign/longboi) or a 3-px dot (smallsign) beside that team's score. Timeouts are three 2-px pips per team, lit white when remaining, `DIM` when used. Both are shapes (`rect`/`px`), subject to the ≥ 6 px clearance rule like the hockey chips and badges.

### Per sign (live)

- **Smallsign (160×16, two 8-row bands, away on top):** chip · abbreviation · score · possession dot · timeout pips (3×2 px, 1-px gaps) · down & distance (`3RD & 4`, cyan; red in the red zone) on the possessing team's band only · right-aligned quarter (top band, amber) and clock (bottom band, white). `HALF` / `END Q3` replace the quarter with an empty clock. The ball spot is omitted at scale 1 (the ticker layout carries it). Columns are minimums that push right when a text is wider, exactly as `HockeyBandBoard`.
- **Bigsign (256×64, two 32-row team rows, dotted divider):** chip · abbreviation (brand) · score (large white) · possession triangle · timeout pips under the triangle · the right status column: quarter (amber), clock (white), then `3RD & 4 · PHI 38` (cyan, red in the red zone; shrink ladder, spot dropped first). The `SOG` slot becomes the record (`5-2`, dim) in the next-game card only.
- **Longboi (512×64):** away left (chip, large abbreviation, timeout pips beneath, huge score), home mirrored right, centre column: quarter, large clock, then `3RD & 4 · PHI 38`. Possession triangle sits between the possessing team's score and the centre column.

### Other states

- **Halftime / end of quarter / delay:** the live board; status reads `HALF`, `END Q3`, `DELAY`; no down & distance, no possession.
- **Final:** the board with `FINAL` and `OT` beneath when `final_ot`; winner green, loser gray; no situation row. Timeouts hidden.
- **Next game:** chips, `PHI @ NYG` (or `PHI VS NYG` when `neutralSite`), records dim beside each name, day label amber, kickoff white (`TBD` dim when unknown), venue dim, a small `NEXT GAME` label (`BYE WEEK` instead when the tracked team is on its bye this week; `PPD` for a postponed game). Longboi adds nicknames.
- **Ticker:** one line per game from a single `segments()` source shared by the scale-1 `SegmentMessage` and the hi-res crawl: `PHI 20 · NYG 17 · Q4 2:13 · NYG ball 2ND & 7 · PHI 24 · TOL 1-2`; future: `PHI @ NYG · SUN NOV 1 1:00 PM · ESPN · LINCOLN FINANCIAL FIELD`; final: `… · FINAL/OT`.

## Demo data (`demo = true`, no network)

Five PHI/NYG cards: (1) live Q4 2:13, PHI 20 NYG 17 at NYG, NYG ball `2ND & 7` at `PHI 24`, timeouts PHI 1 / NYG 2, not red zone, with a queued PHI touchdown play `HURTS 12 YD RUSH` (+PAT) for the celebration; (2) halftime PHI 10 NYG 10; (3) OT final NYG 27 PHI 24; (4) next game next Sunday 1:00 PM at Lincoln Financial Field, records `5-2` / `4-3`, broadcast FOX; (5) a `BYE WEEK` next-game card. One live card only; the red-zone rendering path is covered by the layout clearance test, not by a demo card.

## Constraints

- Everything in `plugins/hockey/CLAUDE.md` and `CONTRIBUTING.md`: import only `led_ticker.plugin`; no `from __future__ import annotations`; Python 3.14; `led-ticker-core >= 4.30`; ruff, pyright, coverage ≥ 90; the layout invariant (measured widths, ≥ 6 px, row-uniform ladders, ellipsis at the floor) with a worst-case clearance tripwire on both physical signs (longest abbreviations `WSH`/`JAX`, two-digit scores `48`, `1ST & GOAL · NYG 50`, `END Q3`, `FINAL/OT`, three lit pips each, a possession triangle, `STALE`) and the smallsign twin.
- Hi-res text never pixel-pinned in tests.
- The fetcher never raises; never infer a final from a vanished game; first sight is a silent baseline.
- Package shape mirrors hockey file for file: `scores.py`, `_source.py`, `_models.py`, `_card.py`, `_celebration.py`, `_scoreboard.py`, `layouts/{__init__,scoreboard,crawl}.py`, `_palette.py`, `_paint.py`, `teams.py`, `README.md`, `CLAUDE.md`, `Makefile`, `LICENSE`, `examples/config.football-{demo,live}.{smallsign,bigsign,longboi}.toml`, plus the root `README.md` plugin row and the `scripts/check_release.py` allowlist entry (hockey did the allowlist in a separate PR; here it goes in the same PR).
- Fixtures: real trimmed events from the 2026-10-26 payload (`DAL @ PHI` scheduled, `NE @ CHI` final, `NYG @ HOU` final/OT, `week.teamsOnBye`, `leagues[0].calendar`), a **hand-written** live event with `situation` (flagged `"_handwritten": true`; shape from the community-documented preseason capture), a trimmed `teams/PHI/schedule` fixture (`byeWeek: 10`, a `TBD` Week 18 game, object-shaped scores). The README's known-limitations section says the live `situation` shape is unverified until a live game is captured. No network in CI.

## Left to the builder

- Exact pixel geometry, ladders and the pip/triangle sizes per sign within the arrangement above and the hockey geometry constants.
- Whether `END Q3` fits the smallsign's right column at the bitmap font or shortens to `END3`; measure.
- Which of `3RD & 4` / `PHI 38` drops first when the status column is too narrow (spec says the spot).
- Whether the celebration's flash word on the smallsign is `TD!` or `TOUCHDOWN`; measure against 160 px.
