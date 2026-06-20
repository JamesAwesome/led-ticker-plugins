# Attendance team-code fix + shared next-game probe — design

**Date:** 2026-06-15
**Status:** Approved
**Scope:** The two cross-cutting follow-ups flagged by the independent review of
PR #14 (statcast team filter). Both touch the already-merged `attendance`
widget and `teams.py`; bundled into one small PR.

## Background

PR #14 established the team-code duality centrally: `teams.py`
`API_TO_CANONICAL_ABBR = {"ATH": "OAK", "AZ": "ARI"}` (MLB's StatsAPI/Savant
emit `ATH`/`AZ`; the plugin's canonical config codes are `OAK`/`ARI`), and
`resolve_team_id` now matches a canonical code against its API spelling. Two
gaps in `attendance.py` were deferred from that PR and are fixed here.

## Change 1 — Normalize attendance schedule abbreviations

`attendance._parse_schedule_games` reads schedule team abbreviations raw:
`home.get("abbreviation")` → `"ATH"` for the Athletics. Downstream that breaks
two things for the Athletics and D-backs:

- **Team mode matching:** `_pick_team_game` does `self.team in (g.home_abbr,
  g.away_abbr)`. A user's canonical `team = "OAK"` never matches the raw
  `"ATH"`, so the widget acts as if the team never plays.
- **Brand color:** league lines color the venue via `_team_color(rec.home_abbr)`
  and team lines via `_team_color(self.team)`. `_team_color("ATH")` misses
  `MLB_TEAM_COLORS` (keyed `OAK`) → white fallback, and the two paths disagree.

**Fix:** apply `API_TO_CANONICAL_ABBR` to both abbreviations as they are parsed
in `_parse_schedule_games`, so every `GameVenue.home_abbr`/`away_abbr` is
canonical (`OAK`/`ARI`). Everything downstream (matching, color, the home-abbr
shown in league lines) then agrees with statcast and the config/README codes.
Add `API_TO_CANONICAL_ABBR` to attendance's `teams` import.

This is the schedule-side mirror of what statcast's `_row_team` already does
for Savant rows; the canonical map stays the single source of truth in
`teams.py`.

## Change 2 — Extract the shared 30-day next-game probe

`statcast._set_no_games_state` and `attendance._set_no_games_state` run a
byte-identical 30-day regular-season schedule probe (build URL with optional
`&teamId=`, fetch, walk `dates[]`, return the first parseable `date`). PR #14
deepened this into full duplication. Extract the probe into `teams.py`:

```python
async def next_game_date(
    session: aiohttp.ClientSession,
    today: date,
    *,
    team_id: int = 0,
    lookahead_days: int = 30,
) -> date | None:
    """Earliest scheduled regular-season game date in
    [today, today + lookahead_days], optionally scoped to ``team_id``.
    Returns None on fetch failure or when no game is found (debug-logged)."""
```

It owns the URL build (`sportId=1`, `gameType=R`, `&teamId=` only when
`team_id`), the fetch-with-`try/except`-→-None, and the `dates[]` walk with
`date.fromisoformat` + malformed-entry skip. `teams.py` gains
`from datetime import date, timedelta`.

Both widgets' `_set_no_games_state` shrink to: call `next_game_date(...)`, then
build their own label / `TickerMessage` / INFO log:

```python
    async def _set_no_games_state(self, today: date) -> None:
        next_date = await next_game_date(self.session, today, team_id=self._team_id)
        if next_date is None:
            text = "No games soon"
        elif self._team_id:
            text = f"Next game{tail}: {next_date.strftime('%b %-d')}"  # see note
        else:
            text = f"Next games{tail}: ..."
```

(Each widget keeps its existing wording — statcast `Next game` / `Next games`,
attendance the same — and its own log string. Only the probe mechanics move.)

### Twin of PR #14 finding #2 (attendance)

While extracting, **attendance's label gating moves from `self.team` to
`self._team_id`** — matching the fix statcast already shipped. Today attendance
gates the `"Next game:"` label on `self.team` but the `&teamId=` query on
`_team_id`; a team whose id failed to resolve would mislabel a league-wide date
as the team's next game. Gating both on `_team_id` makes a failed resolve
degrade honestly to `"Next games:"`. (With Change 1 + the merged resolve fix,
`OAK`/`ARI` now resolve, so this is the transient-failure safety net.)

## Out of scope

- No change to statcast's probe output (identical behavior through the helper).
- No new config, display, or widget surface.
- No further widget de-duplication (the team field/converter/start scaffolding
  stays per-widget — only two widgets, no base class, as the review affirmed).

## Testing

- **teams.next_game_date:** team-scoped URL contains `&teamId=`, league URL does
  not; returns the first valid date; skips a malformed `dates[]` entry; returns
  `None` on empty `dates` and on fetch exception. (New `tests/test_teams.py`, or
  alongside the resolve tests.)
- **attendance abbr normalization:** `_parse_schedule_games` maps `ATH`→`OAK`,
  `AZ`→`ARI`, leaves others; `_pick_team_game` finds a game when `team="OAK"`
  and the schedule says `ATH`; a league/team line for the A's uses the real
  `OAK` brand color (not white).
- **attendance probe honest-degrade:** `team` set but `_team_id == 0` →
  `"No games soon"` is queried league-wide and labeled `"Next games:"`, not
  `"Next game:"`.
- **statcast regression:** existing `_set_no_games_state` tests stay green after
  the helper swap (team → `Next game` + `teamId`; league → `Next games`; failed
  → `No games soon`).
- All gates: ruff/format/pyright, full suite, coverage ≥90.

## Docs

No README/CLAUDE.md change required (no surface change; A's/D-backs now simply
behave correctly). Optionally note nothing — the Team-codes list already shows
`OAK`/`ARI` as the codes to use.
