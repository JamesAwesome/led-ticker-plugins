# baseball.statcast team filter — design

**Date:** 2026-06-14
**Status:** Approved
**Scope:** Enhancement to the existing `baseball.statcast` widget — add an
optional `team` filter so the daily superlatives can be scoped to one team's
players (e.g. the Phillies), mirroring `baseball.attendance`'s team/league
duality. Existing league-wide behavior is unchanged when `team` is unset.

## Purpose

Today `baseball.statcast` is league-wide only: longest HR / hardest-hit ball /
fastest+slowest pitch across all of MLB. Add an optional `team` config field; when
set, every superlative is drawn from **that team's own players** — the record
holder is always on the tracked team (a Phillies batter for `longest_hr`, a
Phillies pitcher for `fastest_pitch`, etc.). This is what a fan means by "the
Phillies' superlatives," and it matches how `baseball.attendance` already toggles
league vs team mode by the presence of `team`.

## Data

No new data source. The widget already pulls the full-day Baseball Savant CSV
(`_derive_day`); team mode filters those rows **client-side**. Each row carries
`home_team`/`away_team`/`inning_topbot`, and the existing `_row_team(row, who)`
already resolves a batter's or pitcher's team (with the `ATH`→`OAK` / `AZ`→`ARI`
Savant normalization). So the filter is row selection only — same fetch, same
schedule gate.

Rejected: a team-scoped Savant query (smaller payload, but a second URL/code
path for a marginal bandwidth win on an already-gated 3 MB pull); a separate
widget (the `team`-field dual-mode is the established convention).

## User-facing surface

### Config

```toml
[[playlist.section.widget]]
type = "baseball.statcast"
team = "PHI"            # optional; omit → league-wide (unchanged)
stats = ["longest_hr", "fastest_pitch"]   # works in both modes
# common: update_interval, title, timezone, padding, bg_color, font_color, font
```

- `team` optional, case-insensitive (upper-cased at construction via an attrs
  converter, like `attendance`); absent/`""` → league mode.
- `stats` applies in both modes (which superlatives, display order) — unchanged.
- Default `title` stays `"Statcast"`; the team is identified inline on each line
  (below), so no team-derived title is needed.

### Line format

League mode is unchanged. Team mode leads with the team abbr in its brand color
and drops the now-redundant trailing abbr (the holder is always the tracked
team):

```
league:  Today · Longest HR 463 ft — Butler OAK
team:    PHI Today · Longest HR 472 ft — Schwarber
```

Segments, team mode: `PHI ` (team color) · `Today · ` or short-date (grey) ·
`<Label> ` (body) · `<value>` (amber) · ` — <LastName>` (body). The slowest-pitch
`(pitch_name)` suffix is unchanged. When the resolved name is missing, the line
degrades to value only (` —`), same as today.

### Day selection & fallbacks

Same ladder as the current widget, scoped by mode:

| Condition | Display |
| --- | --- |
| Today has ≥1 qualifying record (for the team, or league-wide) | `Today · …` lines |
| Today empty | yesterday's records, short-date label (`6/12 · …`) |
| Both empty (off-day / team didn't play) | 30-day probe: team mode → `Next game: Jun 20`, league mode → `Next games: Jun 20`, else `No games soon` |
| Fetch/parse failure | `No Data` |

A stat with no qualifying record omits its line; remaining stats still render
(unchanged). In team mode the probe is team-scoped (`teamId=…`) and says
`Next game`; league mode keeps `Next games` — mirroring `attendance`.

## Internals

### Changes to `statcast.py`

- **`MLBStatcastMonitor.team`** — new field: `team: str = attrs.field(default="",
  converter=lambda v: v.upper() if v else "")` (same converter as attendance);
  plus the existing `_team_id` (already on attendance, add here) resolved in
  `start()` when `team` is set, for the probe.
- **`_derive_records(rows, stats, team="")`** — add the optional `team` param.
  Inside the per-stat checks, when `team` is set, a row is only considered for a
  stat if `_row_team(r, who) == team` (`who` = `"batter"` for
  `longest_hr`/`hardest_hit`, `"pitcher"` for `fastest_pitch`/`slowest_pitch`).
  League mode (`team=""`) skips the check → identical to today.
- **`_derive_day`** passes `self.team` through to `_derive_records`.
- **`_build_stat_stories`** — when `self.team` is set, prepend a
  `(f"{self.team} ", _team_color(self.team))` segment and render the holder as
  the bare last name (no trailing team abbr); league mode unchanged.
- **`start()`** — resolve `_team_id` via `resolve_team_id` when `team` set
  (import it from `teams.py`), like attendance.
- **`_set_no_games_state`** — make team-aware: append `&teamId=` when `_team_id`
  is set; text `Next game:` (team) vs `Next games:` (league). Mirrors attendance.
- **`validate_config`** — add: `team` present but not a string → message
  (mirrors attendance). Existing `stats` checks unchanged.

### Out of scope

- No change to league-mode behavior or output (regression-guarded by tests).
- No new "whole-game" filter mode (own-players only, per the brainstorm).
- No README "common patterns" recipe changes beyond noting `team` on statcast.

## Testing (`tests/test_statcast.py`, extend)

- **Team filter derivation:** with `team="PHI"`, `longest_hr`/`hardest_hit`
  consider only Phillies *batters*; `fastest_pitch`/`slowest_pitch` only
  Phillies *pitchers*; an opponent's bigger event is excluded; a stat with no
  Phillies event is omitted. League mode (`team=""`) unchanged (regression).
- **Savant abbr in filter:** a Phillies game where the row's team code needs
  normalization still matches (reuse the ATH/AZ path via `_row_team`).
- **`team` coercion:** `make_widget(team="phi").team == "PHI"`.
- **Team-mode line format:** leading `PHI ` segment in brand color; holder is
  bare last name (no trailing abbr); value amber; grey day label; slowest-pitch
  suffix retained.
- **Team-aware probe:** team mode → `Next game: <date>` with `teamId` in the URL;
  league mode → `Next games:` unchanged.
- **validate_config:** non-string `team` rejected; valid `team` + `stats`
  passes.
- **start():** team-mode resolves `_team_id` and spawns loop (extend the
  existing start test for the team branch, like attendance).
- Smoke/import purity already cover the module; no registration change.

## Docs

- **README.md** `### baseball.statcast`: add a `team` row to the options table
  and a one-line team-mode example + line-format note. Mention in the intro that
  statcast can be league-wide or team-scoped.
- **CLAUDE.md**: tweak the statcast overview bullet to note the optional team
  filter.
