# baseball.statcast widget — design

**Date:** 2026-06-11
**Status:** Approved
**Scope note:** Second of the three widgets sketched after the promotions
brainstorm (promotions shipped in PR #9). The attendance/ballpark-conditions
widget (live-feed `gameData.gameInfo` / `gameData.weather`) remains deferred.

## Purpose

Scroll league-wide daily Statcast superlatives — longest home run, hardest-hit
ball, fastest pitch, slowest pitch — re-derived throughout the day as games
progress. Values update intra-day (the fastest pitch at noon is rarely the
fastest pitch at midnight); the widget is stateless and re-derives from the
full day's data on every refresh.

## Data sources (probed 2026-06-11, real payloads)

**Baseball Savant day CSV** (primary):

```
GET https://baseballsavant.mlb.com/statcast_search/csv
    ?all=true&type=details&game_date_gt={YYYY-MM-DD}&game_date_lt={YYYY-MM-DD}
```

- One request returns every pitch of the day: measured ~3.0 MB / ~4,570 rows /
  ~8 s for a full 15-game slate. No API key; it is an undocumented website
  endpoint, so requests carry a `led-ticker-baseball` User-Agent and the
  default refresh is conservative.
- Columns used: `events`, `description`, `launch_speed`, `hit_distance_sc`,
  `release_speed`, `pitch_name`, `batter`, `pitcher` (person IDs),
  `home_team`, `away_team`, `inning_topbot`.
- The `player_name` column is NOT used — its meaning shifts with query type;
  the `batter`/`pitcher` ID columns are authoritative.
- Data lags live play by a minute or two — fine at this cadence.

**MLB StatsAPI** (auxiliary, same keyless API the plugin already uses):

- Day schedule (`/schedule?sportId=1&date=…`, ~10 KB) — the refresh gate.
- `/people?personIds=…` — one batched call resolves the ≤4 record-holder IDs
  to names.
- 30-day league schedule (`gameType=R`) — the offseason/off-day probe.

Rejected alternatives: per-game StatsAPI live feeds (~15 × 1–5 MB per refresh
for the same answer); per-stat filtered Savant queries (the pitch stats force
the full-day query anyway).

## User-facing surface

**Widget type:** `baseball.statcast`
**Class:** `MLBStatcastMonitor` in `src/led_ticker_baseball/statcast.py`
**Registration:** `api.widget("statcast")(MLBStatcastMonitor)` in `register()`.

### Config

```toml
[[playlist.section.widget]]
type = "baseball.statcast"
# everything optional:
stats = ["longest_hr", "hardest_hit", "fastest_pitch", "slowest_pitch"]
update_interval = 1800                # 30 min; gating makes off-hours ~free
timezone = "America/New_York"        # governs "today" + day rollover
title = "Statcast"
# standard knobs: padding, hold_time, bg_color, font_color, font
```

- `stats` defaults to all four, in that order; the list order is the display
  order. Unknown keys are rejected by `validate_config` by name.
- No `team` field — the widget is league-wide by design (decision from
  brainstorm: superlatives are most fun across all of MLB).

### Lines

One story per selected stat, each self-contained (story lines must identify
their subject inline — section titles scroll away):

```
Today · Longest HR 463 ft — Butler OAK
Today · Hardest hit 113.4 mph — Tatis Jr. SD
Today · Fastest pitch 101.8 mph — Misiorowski MIL
Today · Slowest pitch 69.6 mph (Slow Curve) — Pederson KC
```

Segments and colors:

| Segment | Color |
| --- | --- |
| `Today · ` / `6/12 · ` (short date) | grey `make_color(150, 150, 150)` |
| stat label (`Longest HR `) | white / plain `font_color` tint (same `_plain_body_color` semantics as promotions) |
| value (`463 ft`, `101.8 mph`) | amber `make_color(255, 200, 60)` |
| ` — <LastName> ` | white / plain `font_color` tint |
| team abbr (`OAK`) | `_team_color(abbr)`. Savant's `ATH`/`AZ` codes are normalized to the plugin's `OAK`/`ARI` (see `_SAVANT_ABBR`) so the abbr and color match the other widgets; abbreviations still missing from `MLB_TEAM_COLORS` fall back to white. |

- Batter stats name the batter; pitch stats name the pitcher. Last names from
  the `/people` lookup; on lookup failure the line renders without the name
  (value + team abbr still shown).
- `slowest_pitch` appends ` (<pitch_name>)` when present — the
  eephus/position-player flavor. `fastest_pitch` does not (always a fastball).
- A stat with no qualifying row (no HR yet today) omits its line; remaining
  stats still render.
- Value formatting: distance `<int> ft`; speeds `<one-decimal> mph`.

### Stat definitions

| Key | Rule |
| --- | --- |
| `longest_hr` | max `hit_distance_sc` over rows with `events == "home_run"` |
| `hardest_hit` | max `launch_speed` over rows with `description == "hit_into_play"` |
| `fastest_pitch` | max `release_speed` over all rows |
| `slowest_pitch` | min `release_speed` over all rows |

Rows missing the relevant value are skipped. Ties: first row wins (CSV order).

### Day selection & fallbacks

| Condition | Display |
| --- | --- |
| Today's CSV yields ≥1 selected stat | `Today · …` lines |
| Today empty (pre-game morning, postponed slate) | derive from yesterday's CSV, short-date (`6/12 · …`) labels |
| Both days empty (off-day / offseason) | 30-day league schedule probe: first game date → `Next games: Mar 26`, else `No games soon` |
| Fetch/parse failure | `No Data` |

The title (`Statcast`, white `TickerMessage`; `title` config overrides) is set
unconditionally at the top of `update()` — same setter contract as the
promotions widget. Fallback lines are league-generic and self-explanatory, so
they carry no prefix.

## Internals

### Architecture

`MLBStatcastMonitor` mirrors `MLBPromotionsMonitor`: attrs class
(`session`, config fields, `init=False` state, `feed_title`/`feed_stories`),
`start()` classmethod (`update()` then
`spawn_tracked(run_monitor_loop(widget, update_interval))`), default
`update_interval` 1800 s. Every core import from `led_ticker.plugin`; the
Savant base URL is a module constant in `statcast.py` (statcast-specific, not
`teams.py`). No `from __future__ import annotations` (PEP 649).

### update() data flow

1. **Schedule gate:** fetch the StatsAPI day schedule (~10 KB). Re-derive only
   when at least one of: (a) any game `Live`; (b) the `Final` count differs
   from the count at the last successful derive; (c) the local date rolled
   over since the last derive; (d) no successful-derive snapshot exists —
   first run, or the last update ended in an error/fallback state. Otherwise
   keep current stories and return. A failed gate fetch counts as
   "re-derive" (fail open).
2. **Fetch + parse:** Savant day CSV via the widget's `aiohttp` session with
   the `led-ticker-baseball` User-Agent; stdlib `csv.DictReader`
   (UTF-8-sig — the CSV ships a BOM). ~4,500 rows parse in milliseconds;
   no thread offload needed.
3. **Derive:** one pass produces a `StatRecord` per stat key —
   `(value, person_id, team_abbr, pitch_name)`. Team attribution: batter team
   = `away_team` when `inning_topbot == "Top"` else `home_team`; pitcher team
   is the other one.
4. **Names:** single `/people?personIds=…` call for the distinct IDs →
   `lastName` map. Failure degrades per-line (no name), not to the error
   state.
5. **Stories or fallbacks** per the table above; on success remember the
   schedule snapshot (date + Final count) for the next gate decision.

Errors: any exception in steps 2–3 → `logger.exception` + `No Data` state.
INFO log on every story rebuild (`MLB Statcast updated: …`), same
observability convention as the siblings.

### validate_config

Same contract (returns `list[str]`, never raises):

- `stats` present but not a list of strings → message (with TOML example).
- `stats` containing keys outside the four known → message naming the bad
  key(s) and listing valid ones (mirrors the scores widget's layout check).

## Docs

- **README.md**: new `### baseball.statcast` section — line format, stat keys
  table, config table, fallback behavior, a note that Savant is an
  undocumented endpoint refreshed at a polite default cadence.
- **CLAUDE.md**: overview bullet, `statcast.py` file-map line, `register()`
  snippet line, `test_statcast.py` in the tests list.

## Testing

`tests/test_statcast.py`, CSV-fixture strings (no network), mock session
routing by URL substring (same harness as `test_promotions.py`):

- **Derivation:** each stat key from a small fixture CSV; missing-value rows
  skipped; tie keeps first; missing stat omits its line.
- **Attribution & names:** topbot → batter/pitcher team; `/people` resolution;
  lookup-failure renders value + abbr without name.
- **Line format:** segment texts/colors incl. amber value, grey day label,
  team-colored abbr, `(Slow Curve)` suffix on slowest only, plain
  `font_color` tint on body segments.
- **Gating:** frozen clock (the `_freeze_today` pattern from the promotions
  tests); skip when nothing changed; re-derive on Live game, Final-count
  change, date rollover, empty stories; gate fetch failure fails open.
- **Day fallback:** today empty → yesterday with short-date label; both empty →
  probe (`Next games: <date>` / `No games soon`); fetch error → `No Data`.
- **validate_config:** unknown stat key named; non-list `stats` rejected.
- `test_smoke.py` asserts `baseball.statcast` registers; import purity
  auto-covers the module.
