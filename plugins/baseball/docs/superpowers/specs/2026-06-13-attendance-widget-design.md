# baseball.attendance widget — design

**Date:** 2026-06-13
**Status:** Approved
**Scope note:** Fourth and final widget from the original post-promotions
brainstorm (promotions #9, statcast #10 shipped). Completes the set.

## Purpose

Show ballpark attendance and conditions from the MLB StatsAPI. Two modes,
chosen by whether `team` is configured:

- **League-wide** (no `team`): daily attendance superlatives — biggest /
  smallest crowd, fullest / emptiest park by capacity %.
- **Team** (`team` set): the tracked team's game today — attendance + fill %
  once final, plus venue and weather (available pre-game as a forecast).

## Data sources (probed 2026-06-12/13, real payloads)

All from the StatsAPI the plugin already uses; no new dependency.

**Schedule** (the shared gate), one call per refresh, ~47 KB:

```
GET {MLB_API}/schedule?sportId=1&date={YYYY-MM-DD}&hydrate=venue(fieldInfo),team
```

Per game it yields: `status.abstractGameState` (Preview/Live/Final),
`gamePk`, `gameNumber` (1/2 for doubleheaders), `venue.name`,
`venue.fieldInfo.capacity`, and — because of the `,team` hydration —
`teams.home/away.team.abbreviation` (verified: `venue(fieldInfo)` alone
returns only `{id, name, link}`, no abbreviation; adding `,team` brings it in
and roughly doubles the payload, ~23 KB → ~47 KB). **Attendance is NOT in the
schedule at any hydration** — it lives per-game only.

**Live game feed** (team mode), one fetch for the tracked team's game:

```
GET {_MLB_LIVE_API}/game/{gamePk}/feed/live
```

`gameData.gameInfo.attendance` (int, present only once Final),
`gameData.weather` = `{condition, temp, wind}`, plus `gameData.venue`. One
fetch carries everything team mode needs.

Weather availability (verified): populated for **same-day** games at every
state — including a Preview before first pitch, the day-of forecast (e.g.
`{"condition": "Clear", "temp": "97", "wind": "7 mph, Out To LF"}`) — and for
Live/Final. It is empty (`{}`) only for **future-day** Previews (a game days
away). This widget only ever renders today's or yesterday's game, so weather
is normally present; the "omit the weather segment when absent" rule below
covers the rare early-morning-before-forecast case.

**Boxscore** (league mode), one per Final game, ~165 KB (≈10× lighter than
the live feed):

```
GET {MLB_API}/game/{gamePk}/boxscore
```

Attendance is in `info[]` as `{"label": "Att", "value": "19,587."}` — a
formatted string. Some games (doubleheader game 1, undisclosed) omit it.

Field availability by game state (verified): attendance exists only at
**Final**; weather, venue, and capacity exist at every state. This is why
attendance is the post-game headline and venue/weather is the always-available
fallback.

Rejected: full live feeds for league mode (~789 KB × ~15 games ≈ 11.8 MB per
refresh vs ~2.5 MB of boxscores at ~165 KB each — the boxscore is ~4.8× lighter
than the feed); schedule-only (no attendance anywhere in it).

## User-facing surface

**Widget type:** `baseball.attendance`
**Class:** `MLBAttendanceMonitor` in `src/led_ticker_baseball/attendance.py`
**Registration:** `api.widget("attendance")(MLBAttendanceMonitor)`.

### Config

```toml
[[playlist.section.widget]]
type = "baseball.attendance"
# team mode:
team = "TOR"
# league mode (omit team); optional subset/order of the four superlatives:
stats = ["biggest_crowd", "smallest_crowd", "fullest", "emptiest"]
# common (all optional):
update_interval = 1800              # 30 min; schedule-gated
timezone = "America/New_York"
title = "Attendance"
# standard: padding, hold_time, bg_color, font_color, font
```

- `team` optional; case-insensitive; absent → league mode.
- `stats` applies to league mode only (silently ignored when `team` is set —
  not flagged, since `validate_config` messages become fatal pre-flight
  errors). Default = all four in the order above; list
  order is display order.
- `update_interval` default 1800 s; the gate makes off-hours refreshes nearly
  free (one ~20 KB schedule call).

### League mode lines

One centered story per superlative. Day label grey, value amber, venue name in
the **home team's** brand color (`_team_color(home_abbr)`) so lines stay
self-identifying and on-brand:

```
Today · Biggest crowd 45,123 — Dodger Stadium
Today · Smallest crowd 8,201 — Tropicana Field
Today · Fullest 99% — Wrigley Field
Today · Emptiest 51% — PNC Park
```

| Key | Rule |
| --- | --- |
| `biggest_crowd` | max attendance over Final games with a parsed attendance |
| `smallest_crowd` | min attendance over the same set |
| `fullest` | max attendance ÷ capacity over Final games with capacity > 0 |
| `emptiest` | min attendance ÷ capacity over the same set |

Attendance formatted with thouscommas (`45,123`); fill % as `<round>%`. Ties:
first game in schedule order wins. A stat with no qualifying game omits its
line; remaining stats still render.

### Team mode line

One centered story for the tracked team's game, prefixed with the team abbr in
its brand color (self-identifying — the tracked team even on a road game; the
venue says where):

```
final:   TOR · Rogers Centre 41,212 (89%) · 72° Clear, wind 5 mph In From CF
live:    TOR · Rogers Centre · 72° Clear, wind 5 mph In From CF
preview: TOR · Rogers Centre · 72° Clear, wind 5 mph In From CF
```

Segments: `TOR ` (team color) · venue name (body) · attendance + ` (NN%)`
(amber; omitted until Final, and the `%` omitted when capacity missing/0) ·
weather `<temp>° <condition>, wind <wind>` (body). `temp` is Fahrenheit as a
bare string from the feed → `72°`. Weather is shown whenever present (it is,
for the same-day game this widget renders); the segment is omitted if the feed
returns empty weather.

**Doubleheader rule:** if the tracked team has two games on the date, pick the
Live one if either is in progress; else the later game (`gameNumber == 2`) when
both are Final; else the earlier (`gameNumber == 1`). One line, one game.

**Yesterday fallback line** prepends the short date as its own grey segment,
after the team prefix:

```
6/12 · TOR · Rogers Centre 41,212 (89%) · 72° Clear, wind 5 mph In From CF
```

### Day selection & fallbacks

| Mode | Condition | Display |
| --- | --- | --- |
| League | ≥1 Final today with attendance | `Today · …` superlative lines |
| League | no Final today (morning/in-progress) | yesterday's finals, short-date label (`6/12 · …`) |
| Team | team has a game today | that game's line (attendance once Final, else venue+weather) |
| Team | no game today | yesterday's final, short-date label; else 30-day team probe → `Next game: Jun 22` |
| Either | no games in 30-day probe (offseason) | `No games soon` |
| Either | fetch/parse failure | `No Data` |

`title` (default `"Attendance"`, white `TickerMessage`; config overrides) is
set unconditionally at the top of `update()` — same setter contract as the
siblings. Fallback lines are generic and self-explanatory; no team prefix.

## Internals

### Architecture

`MLBAttendanceMonitor` mirrors `MLBStatcastMonitor`: attrs class (`session`,
config fields, `init=False` state incl. `_tz`, `_team_id`, `_last_derive`,
`feed_title`, `feed_stories`), `start()` classmethod
(`spawn_tracked(run_monitor_loop(...))`, default interval 1800), gated
`update()` branching on `self.team`. Core imports from `led_ticker.plugin`
only; `MLB_API`/`_MLB_LIVE_API`/`_team_color`/`resolve_team_id` from
`teams.py`. No `from __future__ import annotations` (PEP 649).

### Shared gate

`_fetch_schedule(today)` returns the hydrated game list (or None on failure).
`_should_skip(today, snapshot)` — re-derive when the gate fetch failed (fail
open), no prior successful derive, the local date rolled over, any game is
Live, or the Final count changed; else keep current stories. Snapshot is
`(date, final_count)`, reset to None on error/fallback so the next tick
re-derives. Identical discipline to statcast. The gate uses the **league-wide**
Final count even in team mode — slightly coarse (another team finalizing
forces a re-derive of an unchanged team line) but cheap and simpler than a
team-specific gate; the re-derive just rebuilds the same line.

### update() flow

1. `_set_title()`; compute `today` in tz.
2. `_fetch_schedule(today)`; `_should_skip` → return.
3. Branch on `self.team`:
   - **Team:** resolve id (cached after first run), find the team's game in the
     gated schedule (doubleheader rule above). If found → fetch its live feed →
     build the team line (no date prefix). If no game today → `_fetch_schedule(
     yesterday)`, find the team's game, fetch its feed, build the line with the
     short-date prefix. If still none → 30-day team probe
     (`teamId=…&gameType=R`) → `Next game: <date>`, else `No games soon`.
   - **League:** from the gated schedule take Final games with capacity > 0;
     `asyncio.gather` boxscore fetches (per-game failures skipped); parse
     attendance; derive the requested superlatives; build `Today · …` lines. If
     none → repeat against `_fetch_schedule(yesterday)` with short-date labels.
     If still none → 30-day league probe → `No games soon`.
4. On success, store the schedule snapshot; INFO log the rebuild.

Team mode reuses the full league-wide gated schedule to locate the team's game
(one ~47 KB call) rather than a separate `teamId=`-scoped schedule — a
deliberate trade-off that keeps one gate call shared across both modes.

### Parsing

- **Boxscore attendance:** find `info[]` entry with `label == "Att"`, take
  `value`, strip everything but digits, `int()`. Missing entry or empty →
  skip that game (None).
- **Weather:** `temp` → `f"{temp}°"`; line is `f"{temp}° {condition}, wind
  {wind}"`. Missing weather → omit the weather segment.
- **Capacity:** from `venue.fieldInfo.capacity`; 0/missing → no fill %, and the
  game is excluded from `fullest`/`emptiest` (but still counts for
  biggest/smallest crowd).
- **Venue/home colour:** venue name from the schedule (league) or feed (team);
  home abbr from the schedule game's `teams.home.team.abbreviation` →
  `_team_color`.

### Error handling

Any exception in the team feed fetch or the league derive → `logger.exception`
+ `_set_error_state` (`No Data`) + snapshot reset. Per-game boxscore failures
in league mode are caught per task and skipped (one bad game never sinks the
superlatives). A failed fallback/offseason probe degrades silently to
`No games soon` (debug log).

### validate_config

Classmethod, returns `list[str]`, never raises (sibling contract):

- `team` present but not a string → message.
- `stats` present but not a list of strings, or containing keys outside the
  four → message naming the bad key(s) and listing valid ones.
- `stats` present together with `team` → NOT flagged. The engine turns any
  returned message into a fatal `ValueError`, so warning here would reject an
  otherwise-valid config; team mode just ignores `stats` at runtime.

## Docs

- **README.md:** new `### baseball.attendance` section — both modes, line
  formats, stat keys, config table, fallback behavior.
- **CLAUDE.md:** overview bullet, `attendance.py` file-map line, `register()`
  snippet line, `test_attendance.py` in the tests list; bump the "all four
  widget modules import teams.py" count to five.
- **`__init__.py`:** add the import + `api.widget("attendance")(...)` line and
  extend the module docstring's widget list (`baseball.attendance`).

## Testing

`tests/test_attendance.py`, fixture strings, mock session routed by URL
substring (same harness as the sibling tests):

- **Boxscore parse:** `"19,587."` → 19587; missing `Att` → None; thousands
  commas and trailing period handled.
- **League derive:** all four superlatives from a small schedule + boxscore
  fixture set; capacity-missing game excluded from fullest/emptiest but counted
  for biggest/smallest; tie keeps first; missing stat omits its line; `stats`
  subset/order honoured.
- **Team line:** final (attendance + fill %), pre-game (venue + weather, no
  attendance), capacity-missing (no %), missing weather (segment omitted);
  team prefix in brand color; road-game venue.
- **Gating:** frozen clock; skip when unchanged; re-derive on Live / Final-count
  change / date rollover / first run; gate failure fails open.
- **Fallbacks:** league today-empty → yesterday short-date; team no-game →
  yesterday → probe `Next game`; offseason → `No games soon`; error → `No
  Data`.
- **validate_config:** non-string team; unknown/`non-list stats`; stats+team
  warning.
- **start():** patched `spawn_tracked`/`run_monitor_loop` (sync mocks), loop
  spawned with the configured interval, update ran — per the convention set in
  #11. Two cases: team mode (asserts `_tz` and `_team_id` resolved) and league
  mode (asserts `_tz` resolved, no team resolution).
- **Smoke/import purity:** `test_smoke.py` asserts `baseball.attendance`
  registers; AST tripwire auto-covers the module.
