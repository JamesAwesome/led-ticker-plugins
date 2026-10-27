# Football Scores Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `led-ticker-football`, a `football.scores` widget showing live NFL scores (quarter, clock, possession, down & distance, timeouts, red zone), a touchdown/field-goal/safety celebration, and final / next-game / bye-week cards on the smallsign, bigsign and longboi.

**Architecture:** A new uv workspace member `plugins/football/` cloned from `plugins/hockey/` file for file. `_source.py` is a shared, never-raising fetcher over ESPN's keyless scoreboard with a host fallback; it also turns score deltas into `ScoringPlay`s. `_models.py` holds pure parsing and formatting. `scores.py` is the Container widget with one persistent `FootballGameCard` per game; `_card.py` dispatches on scale to the scale-1 band board (`_scoreboard.py`) or the physical renderers (`layouts/`). The celebration is hockey's frame-counter timeline with football words.

**Tech Stack:** Python 3.14, attrs, aiohttp, `led_ticker.plugin` public surface, pytest + pytest-asyncio, ruff, pyright.

**Spec:** `docs/superpowers/specs/2026-10-26-football-scores-design.md`

**Read before starting:**
- `plugins/hockey/CLAUDE.md` — every invariant is inherited unless this plan says otherwise.
- `plugins/hockey/src/led_ticker_hockey/` — the whole package; most football modules start as a copy of their hockey twin with the sport-specific parts replaced. Where a step says "as hockey", copy that function and adapt names.
- `plugins/hockey/tests/{conftest.py,test_layout_scoreboard.py,test_source.py,test_celebration.py}`.
- The spec's "Football in one page" section if you do not follow the sport.

## Global Constraints

- Python **3.14+**; `led-ticker-core>=4.30`, `aiohttp>=3.12`; **no `from __future__ import annotations`**.
- Import `led_ticker` **only** from `led_ticker.plugin` (AST tripwire `test_import_purity.py`).
- Package `led-ticker-football`, module `led_ticker_football`, entry point `football = "led_ticker_football:register"`, widget `football.scores`, hatch-vcs tag match `football-v*`.
- Hosts, in order: `https://site.api.espn.com`, `https://site.web.api.espn.com`. Path prefix `/apis/site/v2/sports/football/nfl`. No API key. `User-Agent: led-ticker-football (+https://github.com/JamesAwesome/led-ticker-plugins)`.
- Example teams are `PHI` and `NYG` in every doc, demo and example.
- Coverage `fail_under = 90`; ruff check + format check; pyright on `src` clean.
- Layout invariant: measured widths, ≥ **6 px** clearance between texts/shapes sharing a vertical band, row-uniform name ladders, ellipsis at the floor. Hi-res text never pixel-pinned in tests.
- Never raise into the poll loop or the render loop. Never infer a final from a vanished game. First sight is a silent baseline. Clocks are **not** ticked locally.
- Palette (0–255): `WHITE (255,255,255)` score/clock; `AMBER (255,180,0)` quarter/date/kickoff/`+PAT`; `CYAN (0,200,220)` down & distance, spot; `RED (230,40,40)` red zone; `DIM (70,70,70)` labels/dividers/used pips; `GREEN (0,220,90)` winner; `LOSER (120,120,120)`; `GRAY (110,110,110)` `@`/records.
- Mode names `teams` / `league` / `live`. Layout names `auto` / `scoreboard` / `ticker`; `auto` → `scoreboard` at every scale. `final_hold_hours` default **24**. `GAME_LENGTH` 3 h 30 min.
- Cadence constants: `LIVE_INTERVAL 15`, `KICKOFF_INTERVAL 60` (within `KICKOFF_WINDOW` 30 min), `PREGAME_INTERVAL 300`, `IDLE_INTERVAL 3600`, `SCHEDULE_INTERVAL 6*3600`, `MIN_INTERVAL 10`, `MAX_BACKOFF 4*3600`.

## Review Focus

1. **A dead-ball poll** (live game, `situation` without `possession`, `down == -1`, no `shortDownDistanceText`) must keep the previous possession marker and draw no down & distance, never a stale `3RD & 4`. Owned by Task 3 (`test_possession_held_across_dead_ball`) and Task 2 (`test_parse_situation_dead_ball`).
2. **A touchdown then its extra point across two polls** (+6 then +1) must celebrate once, with the detail showing the 7-point score. Owned by Task 3 (`test_pat_follow_up_merges_into_touchdown`).
3. **A score correction** (a team's score goes down) must drop the queued celebration and never raise. Owned by Task 3 (`test_negative_delta_is_a_correction`) and Task 6 (`test_overturned_play_drops_pending`).
4. **A game with a TBD kickoff** (`date` at `05:00Z`, `shortDetail == "TBD"`) must show the date and `TBD`, never `12:00 AM`. Owned by Task 2 (`test_tbd_kickoff`).
5. **The first host returning 403** must transparently use the mirror host within the same poll and not mark the snapshot stale. Owned by Task 3 (`test_host_fallback_on_403`).

---

### Task 1: Package scaffold, teams table, fixtures, release allowlist

**Files:**
- Create: `plugins/football/{pyproject.toml,Makefile,LICENSE}` — copy from hockey; swap name, description ("Live NFL football scores widget for led-ticker, fed by ESPN's public scoreboard API (no key)."), keywords (`football`, `nfl`), the `football-v*` tag match, the wheel package path.
- Create: `plugins/football/src/led_ticker_football/__init__.py` with `register(api)` → `api.widget("scores")(FootballScoreMonitor)`; until Task 5 `scores.py` holds `class FootballScoreMonitor: pass`.
- Create: `plugins/football/src/led_ticker_football/teams.py`
- Create: `plugins/football/tests/fixtures/*.json`
- Create: `plugins/football/tests/{conftest.py,test_import_purity.py,test_smoke.py,test_teams.py}` — copy hockey's; conftest keeps `smallsign`/`bigsign`/`longboi`/`tz` and resets `led_ticker_football._source._SHARED_SOURCES`.
- Modify: root `README.md` — add `| Football | `led-ticker-football` | `football.scores` | ESPN public scoreboard API (no key) |` after the Hockey row, and `football` to the original-plugins list.
- Modify: `scripts/check_release.py` — add `"football"` to the allowlist after `"hockey"`; `RELEASING.md` publishable list; `tests/test_check_release.py` — add the football case mirroring the hockey one.

**Interfaces:**
- Produces `teams.py`:
  - `@dataclass(frozen=True) class TeamInfo: abbrev: str; espn_id: str; city: str; nickname: str; primary: Color; secondary: Color` (`Color = tuple[int, int, int]`).
  - `NFL_TEAMS: dict[str, TeamInfo]` — all 32: `ARI ATL BAL BUF CAR CHI CIN CLE DAL DEN DET GB HOU IND JAX KC LV LAC LAR MIA MIN NE NO NYG NYJ PHI PIT SF SEA TB TEN WSH`. ESPN ids: ARI 22, ATL 1, BAL 33, BUF 2, CAR 29, CHI 3, CIN 4, CLE 5, DAL 6, DEN 7, DET 8, GB 9, HOU 34, IND 11, JAX 30, KC 12, LV 13, LAC 24, LAR 14, MIA 15, MIN 16, NE 17, NO 18, NYG 19, NYJ 20, PHI 21, PIT 23, SF 25, SEA 26, TB 27, TEN 10, WSH 28. Colours: start from ESPN's `color`/`alternateColor` (in the saved payload `sb.json`; BUF `00338d`/`c60c30`, LAC `0080c6`/`ffc20e`, WSH `5a1414`/`ffb612`, JAX `006778`/`d7a22a`) and **lift** so `max(channel) >= 90` for both; where ESPN's primary is black or near-black (`LV`, `PIT`, `HOU`, `CHI`, `ATL`'s secondary…) use the lifted other colour as `primary`. `PHI` primary `(0, 150, 130)` (midnight green lifted), secondary `(190, 190, 190)`; `NYG` primary `(40, 90, 220)`, secondary `(230, 40, 60)`.
  - `def team(abbrev: str) -> TeamInfo` — unknown → `TeamInfo(abbrev, "", "", abbrev, (200,200,200), (200,200,200))`, never raises.
  - `def normalize_team(code: str) -> str | None`.
  - `def team_by_id(espn_id: str) -> str | None` — abbreviation for an ESPN team id (possession resolution).
- Produces fixtures: `scoreboard_week7.json` (the saved `sb.json` trimmed to events `401873009` DAL@PHI scheduled, `401873010` NE@CHI final, `401873016` NYG@HOU final/OT; keep `week`, `season`, `leagues[0].calendar`), `event_live.json` (**hand-written**, `"_handwritten": true`: `PHI @ NYG`, id `"401873099"`, `STATUS_IN_PROGRESS`, period 4, `displayClock "2:13"`, PHI 20 NYG 17, `situation{possession:"19", down:2, distance:7, yardLine:76, isRedZone:false, homeTimeouts:2, awayTimeouts:1, shortDownDistanceText:"2nd & 7", possessionText:"PHI 24", downDistanceText:"2nd & 7 at PHI 24", lastPlay{type{text:"Rushing Touchdown"}, text:"Jalen Hurts 12 Yd Rush (Jake Elliott Kick)", scoreValue:6, team{id:"21"}}}`), `event_live_deadball.json` (same game, `situation` with only `down:-1, distance:10, yardLine:0, isRedZone:true, homeTimeouts:2, awayTimeouts:1, lastPlay{...}`), `event_halftime.json` (`STATUS_HALFTIME`, period 2, `0:00`), `schedule_phi.json` (trimmed `teams/PHI/schedule`: `byeWeek: 10`, `season`, three events: one final with object scores `{value: 24.0, displayValue: "24"}`, one `pre` Week 17 game, the Week 18 `TBD` game with `date "2027-01-10T05:00Z"` and `shortDetail "TBD"`).

- [ ] **Step 1: Write failing tests** in `test_teams.py`: `test_all_32_teams_present`, `test_eagles_and_giants_colors` (`team("phi").primary == (0,150,130)`, `team("NYG").secondary == (230,40,60)`), `test_unknown_team_is_neutral`, `test_colors_are_led_visible` (every primary and secondary `max >= 90`), `test_normalize_team` (`"phi"` → `"PHI"`, `"PHL"` → `None`), `test_team_by_id` (`"21"` → `"PHI"`, `"999"` → `None`).
- [ ] **Step 2: Run** `uv run pytest plugins/football -q`. Expected: FAIL (import error).
- [ ] **Step 3: Implement** `teams.py`, the stub `scores.py`, `__init__.py`, the fixtures (write them from the scratchpad `sb.json`/`event_*.json` saved during research; hand-write the live ones), and the root/release edits. `uv sync --extra dev` at the repo root.
- [ ] **Step 4: Run** `uv run pytest plugins/football tests -q && uv run ruff check plugins/football && uv run ruff format --check plugins/football`. Expected: PASS incl. `test_import_purity`, `test_smoke`, `tests/test_check_release.py`.
- [ ] **Step 5: Commit** `git add plugins/football README.md RELEASING.md scripts tests uv.lock && git commit -m "feat(football): scaffold led-ticker-football with the 32-team table and ESPN fixtures"`

---

### Task 2: Models: parsing, status lines, scoring diff

**Files:**
- Create: `plugins/football/src/led_ticker_football/_models.py`
- Test: `plugins/football/tests/test_models.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class LastPlay: text: str; score_value: int; team: str; type_text: str`
  - `@dataclass(frozen=True) class Situation: possession: str | None; down_distance: str; spot: str; red_zone: bool; away_timeouts: int | None; home_timeouts: int | None; last_play: LastPlay | None`
  - `@dataclass(frozen=True) class ScoringPlay: key: str; team: str; kind: str; extra: str; text: str; period_label: str; clock: str; away_score: int; home_score: int` — `kind ∈ {"TD","FG","SAFETY"}`, `extra ∈ {"", "+PAT", "+2PT"}`.
  - `@dataclass(frozen=True) class GameInfo: game_id: str; state: str; status: str; away: str; home: str; away_score: int; home_score: int; period: int; clock: str; start_utc: datetime | None; time_tbd: bool; venue: str; broadcast: str; away_record: str; home_record: str; final_ot: bool; neutral_site: bool; week: int | None; situation: Situation | None = None; polled_at: float = 0.0`
  - `def parse_event(e: dict, *, polled_at: float) -> GameInfo | None` — scoreboard shape; `None` without an id or either abbreviation. Score strings → int (`"24"`); object scores (`{"value": 24.0}`) also accepted so the schedule shape parses through the same function. `state`: `pre`→future, `in`→live, `post`→final; `STATUS_POSTPONED`→future + `time_tbd=True`; `STATUS_CANCELED`→final. `final_ot = state == "final" and (period > 4 or "OT" in altDetail/detail)`. `time_tbd` when `shortDetail == "TBD"` or `detail.endswith("TBD")`. `away_record`/`home_record` = the `type == "total"` record summary. `broadcast` = first `broadcasts[0].names[0]` or `""`.
  - `def parse_situation(c: dict, away_id: str, home_id: str, away: str, home: str) -> Situation | None` — `None` when `c.situation` is absent; `possession` resolves the id to an abbreviation via the ids passed (fallback `teams.team_by_id`); `down_distance = shortDownDistanceText.upper()` or `""` (also `""` when `down == -1` and the text is absent); `spot = possessionText` or `""`.
  - `def period_label(period: int, status: str) -> str` — `HALF` for `STATUS_HALFTIME`; `END Q{n}` for `STATUS_END_PERIOD`; `DELAY`, `SUSP`; else `Q1`–`Q4`, `OT`, `2OT`….
  - `def status_lines(game: GameInfo, now: float, tz: ZoneInfo) -> tuple[str, str]` — per the spec: live `(period_label, clock)` with an empty clock for `HALF`/`END Qn`/`DELAY`; final `("FINAL", "OT"|"")`, canceled `("CANC","")`; future `(day_label, kickoff)` with `kickoff = "TBD"` when `time_tbd`, postponed `("PPD","")`.
  - `day_label`, `_clock_12h`, `winner`, `final_in_hold`, `GAME_LENGTH = timedelta(hours=3, minutes=30)` — as hockey.
  - `def diff_scores(game: GameInfo, prev: tuple[int, int], last_td: ScoringPlay | None) -> tuple[list[ScoringPlay], ScoringPlay | None]` — the pure scoring table from the spec. Input `prev` is the previous `(away, home)`; `last_td` is this game's most recent TD without an `extra` yet (per team is unnecessary: only one TD can be awaiting its try). Returns `(new_plays, follow_up)` where `follow_up` is the re-keyed TD after a +1/+2 (the caller replaces the pending entry). Keys are `f"{game_id}:{away}:{home}"`. Text comes from `situation.last_play` when `score_value > 0` and its team matches: upper-cased with any trailing parenthetical removed (`"JALEN HURTS 12 YD RUSH"`).
  - `def build_demo_games(now: float) -> tuple[list[GameInfo], ScoringPlay]` — the five spec cards plus the demo TD play (`HURTS 12 YD RUSH`, `+PAT`, snapshot 20–17 → after PAT; `period_label "Q4"`, `clock "9:41"`).

- [ ] **Step 1: Write failing tests** in `test_models.py`:
  - `test_parse_scheduled_event` (`401873009`): state future, `start_utc == 2026-10-27T00:15Z`, `venue == "Lincoln Financial Field"`, `broadcast == "ESPN"`, `away == "DAL"`, records `"2-4"`.
  - `test_parse_final_ot_event` (`401873016`): state final, `final_ot`, `winner(g) == "NYG"`, scores 27/21.
  - `test_parse_final_regulation` (`401873010`): `final_ot is False`, `winner == "CHI"`.
  - `test_parse_live_event_situation` (`event_live.json`): `possession == "NYG"`, `down_distance == "2ND & 7"`, `spot == "PHI 24"`, `away_timeouts == 1`, `home_timeouts == 2`, `last_play.score_value == 6`.
  - `test_parse_situation_dead_ball`: `possession is None`, `down_distance == ""`, `spot == ""`, `red_zone is True`.
  - `test_schedule_shape_object_scores`: a `schedule_phi.json` event parses with `away_score == 22`.
  - `test_parse_event_sparse_never_raises`: `{}`, `{"id": "1"}`, a competitor without `team`, `status.type.name == "WEIRD"` with `state == "in"` → live.
  - `test_tbd_kickoff`: the Week 18 schedule event → `time_tbd`, `status_lines(...)[1] == "TBD"`, `[0]` is the date label not `TODAY`.
  - `test_period_labels`: `(2,"STATUS_HALFTIME")→"HALF"`, `(3,"STATUS_END_PERIOD")→"END Q3"`, `(5,"STATUS_IN_PROGRESS")→"OT"`, `(6,…)→"2OT"`, `(1,"STATUS_DELAYED")→"DELAY"`.
  - `test_status_lines_states`: halftime → `("HALF","")`; final OT → `("FINAL","OT")`; postponed → `("PPD","")`; canceled → `("CANC","")`.
  - `test_diff_scores_table`: parametrized `(prev, new, expected kinds/extra)`: +6→`TD ""`; +7→`TD "+PAT"`; +8→`TD "+2PT"`; +3→`FG`; +2 with no pending TD→`SAFETY`; +1 after a `TD ""`→ `([], follow_up with extra "+PAT" and key at the new score)`; +2 after a `TD ""` → follow-up `"+2PT"`; −7 → `([], None)`; +9 → one `TD ""`.
  - `test_diff_scores_text_from_last_play`: the live fixture's TD text → `"JALEN HURTS 12 YD RUSH"`; a last play for the other team → `text == ""`.
  - `test_demo_games_cover_states`: five games; states `{live, live, final, future, future}`; the halftime one has `status == "STATUS_HALFTIME"`; the TD play's `team == "PHI"`.
- [ ] **Step 2: Run** `uv run pytest plugins/football/tests/test_models.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** `_models.py`; every dict read through `.get` with a default (hockey's `_dict`/`_int` helpers, plus `_str`).
- [ ] **Step 4: Run** the same. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "feat(football): parse ESPN scoreboard events into GameInfo; score-delta scoring plays"`

---

### Task 3: Source: shared fetcher, host fallback, cadence, baseline, schedule

**Files:**
- Create: `plugins/football/src/led_ticker_football/_source.py`
- Test: `plugins/football/tests/test_source.py` (fake session + injected `clock`/`wall`, as hockey)

**Interfaces:**
- Consumes Task 2.
- Produces (hockey's `NHLSource` shape, renamed `ESPNSource`):
  - `HOSTS = ("https://site.api.espn.com", "https://site.web.api.espn.com")`, `PATH = "/apis/site/v2/sports/football/nfl"`.
  - `Snapshot(games: dict[str, GameInfo], next_games: dict[str, GameInfo], bye_teams: frozenset[str], week: int | None, stale: bool, error: str | None)`.
  - `ESPNSource.want(*, teams, all_games, tz, final_hold_hours, live_interval)`, `note_displayed`, `poll() -> Snapshot`, `next_delay()`, `plays_after_baseline(game_id) -> tuple[ScoringPlay, ...]`.
  - `async _get(path: str) -> Any` — tries each host in order; `_FetchError`/`TimeoutError`/`aiohttp.ClientError` on host N falls through to host N+1; the last failure propagates. Logs one DEBUG per fallback.
  - `_poll`: one scoreboard GET; `fetched = {e.id: parse_event}`; `_latest_ids`, `_games`, `_last_seen`, hold pruning as hockey; `_bye_teams` from `week.teamsOnBye[].abbreviation`; `_week` from `week.number`; **possession hold**: when the new `GameInfo` is live, `status == "STATUS_IN_PROGRESS"`, same `period` as the stored game, and `situation.possession is None`, replace it with the stored game's possession (`dataclasses.replace`). Then `_track_scores(game)` → `_diff_plays`.
  - `_track_scores`: first sight sets `_baseline[gid] = (away, home)` and `_known_plays[gid] = set()`; otherwise `diff_scores(game, prev, self._open_td.get(gid))` → new plays appended to `_plays[gid]` (keys into `_known_plays`), a follow-up replaces the matching entry in `_plays[gid]` and re-keys it; `_prev[gid]` updated. `plays_after_baseline(gid)` returns `tuple(self._plays.get(gid, ()))` (every play since first sight; widgets dedupe by key as hockey).
  - `_cadence()`: live → `max(MIN_INTERVAL, live_interval)`; any future relevant game with `0 <= start - now <= KICKOFF_WINDOW` → `KICKOFF_INTERVAL`; any future relevant game today (local date) → `PREGAME_INTERVAL`; else `IDLE_INTERVAL`.
  - `_refresh_next`: for each tracked team not `_playing()` and with no `pre` game among `_latest_ids`, at most every `SCHEDULE_INTERVAL`: GET `{PATH}/teams/{TEAM}/schedule`; the first event whose `competitions[0].status.type.state == "pre"` → `parse_event` → `_next[team]`; also `_bye_teams |= {team}` when `body.byeWeek == self._week`. A team with a `pre` game in the week payload uses that game and drops its `_next` entry.
  - `shared_source(session)` as hockey.

- [ ] **Step 1: Write failing tests** in `test_source.py` (copy hockey's fake session; routes keyed by URL suffix):
  - `test_poll_parses_week` — the Week 7 fixture → 3 games, `week == 7`, `bye_teams == {"BUF","LAC","WSH","JAX"}`, not stale.
  - `test_host_fallback_on_403` — first host answers 403, second 200 → snapshot not stale, 2 requests made, both hosts hit in order.
  - `test_both_hosts_fail_is_stale` — 403 then network error → `stale`, `error` mentions HTTP/network, backoff `== 2 * cadence`.
  - `test_malformed_payload_keeps_last_games` — good poll, then `{"events": "nope"}` → stale with the previous games.
  - `test_cadence_ladder` — live game → 15; a game kicking off in 20 min → 60; a game later today → 300; nothing → 3600; `want(live_interval=10)` → 10; `MIN_INTERVAL` floor at 5 → 10.
  - `test_first_sight_scores_are_baseline` — live fixture at 20–17 on first poll → `plays_after_baseline == ()`.
  - `test_touchdown_detected_from_delta` — 20–17 then 26–17 → one `TD` play, key `"<gid>:26:17"`, `text == "JALEN HURTS 12 YD RUSH"`.
  - `test_pat_follow_up_merges_into_touchdown` — then 27–17 → still one play, `extra == "+PAT"`, key `"<gid>:27:17"`, `away_score == 27`.
  - `test_negative_delta_is_a_correction` — 27–17 then 20–17 → plays with snapshots above 20–17 are dropped; no raise.
  - `test_possession_held_across_dead_ball` — live fixture then the dead-ball fixture → `possession == "NYG"`, `down_distance == ""`; a halftime poll clears it to `None`.
  - `test_vanished_game_keeps_state_until_hold` — a final drops out of the payload → still in `games` until `last_seen` + hold.
  - `test_next_game_from_schedule_for_bye_team` — tracked `PHI` with no PHI event in the week payload, schedule fixture → `next_games["PHI"]` is the first `pre` event; with `byeWeek == week` → `"PHI" in bye_teams`; schedule not refetched within 6 h.
  - `test_week_pre_game_beats_schedule` — tracked `DAL` → its `pre` week game is used, no schedule request.
  - `test_shared_source_is_per_session`, `test_poll_never_raises` (the session raises `RuntimeError`).
- [ ] **Step 2: Run** `uv run pytest plugins/football/tests/test_source.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** `_source.py`.
- [ ] **Step 4: Run** the same. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "feat(football): shared ESPN source with host fallback, cadence ladder and scoring baseline"`

---

### Task 4: Palette, paint helpers, scale-1 band board, ticker wording

**Files:**
- Create: `plugins/football/src/led_ticker_football/{_palette.py,_paint.py,_scoreboard.py}`, `layouts/__init__.py`, `layouts/crawl.py` (`segments()` + `render_crawl`, hockey's)
- Test: `plugins/football/tests/{test_scoreboard.py,test_layout_crawl.py,test_resolve_layout.py}`

**Interfaces:**
- Consumes Task 2 helpers and `teams.team`.
- Produces:
  - `_palette.py`: the Global Constraints colours plus `RED`; `chip(abbrev)`, `dim`, `lerp` as hockey.
  - `_paint.py`: hockey's helpers plus `def triangle(real, x: int, cy: int, h: int, color: Color, *, point_left: bool) -> None` (a solid isoceles triangle `h` rows tall, `h // 2 + 1` wide, tip at `x` when `point_left`) and `def pips(real, x: int, y: int, remaining: int | None, *, size: int, gap: int) -> int` (three `size×size` squares left to right, `WHITE` for the first `remaining`, `DIM` after; nothing when `None`; returns the total width).
  - `_scoreboard.py`: `FootballBandBoard(FrameAwareBase)` — hockey's `HockeyBandBoard` with columns: chip x0–2, abbrev x5, score x28, possession dot (3×3 at the band's middle row) x40, pips x46 (3× 2 px, 1-px gaps → 8 px), down & distance x60 on the possessing band (`CYAN`, `RED` when `red_zone`), right-aligned `status_lines` (top amber / bottom white; final: `FINAL` white / `OT` amber). Columns push right past wider texts with `_GAP = 6` as hockey. Final/future hide the dot, pips and situation. Future band: `PHI @ NYG` / venue, day label / kickoff right-aligned as hockey, with `BYE` dim after the names when `bye`.
  - `build_ticker_message(game, now, tz, *, font, bg_color, font_color, stale, bye) -> SegmentMessage`.
  - `layouts/__init__.py`: `VALID_LAYOUTS`, `resolve_layout` (hockey's).
  - `layouts/crawl.py`: `segments(game, now, tz, *, stale=False, bye=False) -> list[tuple[str, Color]]` — live: `PHI 20 · NYG 17 · Q4 2:13 · NYG BALL 2ND & 7 · PHI 24 · TOL 1-2` (the ball run only when possession is known; `2ND & 7`/spot in `CYAN` or `RED`; `TOL a-h` only when both timeouts are known); final: `… · FINAL/OT`; future: `PHI @ NYG · SUN NOV 1 1:00 PM · ESPN · LINCOLN FINANCIAL FIELD` (`VS` for neutral sites, `BYE WEEK` after the day when `bye`, `TBD` kickoff); `STALE` as hockey. `render_crawl` as hockey.

- [ ] **Step 1: Write failing tests**:
  - `test_scoreboard.py`: `test_band_board_live_columns` (dot pixels in rows 8–15 x40–42 for NYG possession, three pips with 2 lit in the NYG band and 1 in the PHI band, `2ND & 7` cyan text in the NYG band, `Q4` top right, `2:13` bottom right — assert via `draw_text` spy + pixel reads on the headless canvas); `test_red_zone_turns_down_distance_red`; `test_band_board_final_hides_situation`; `test_band_board_future_bye`; `test_band_board_worst_case_clearance` (texts per band from measured columns, `WSH 48` vs `JAX 48`, `1ST & GOAL`, `END Q3`, ≥ 6 px between neighbours in a band; `STALE` label).
  - `test_layout_crawl.py`: `test_segments_live_wording` (joined text equals the spec line), `test_segments_future_tbd_and_bye`, `test_segments_final_ot`, `test_render_crawl_held_when_fits` (bigsign).
  - `test_resolve_layout.py`: `auto → scoreboard` at scale 1 and 4; explicit names pass through.
- [ ] **Step 2: Run** `uv run pytest plugins/football/tests/test_scoreboard.py plugins/football/tests/test_layout_crawl.py plugins/football/tests/test_resolve_layout.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** the five modules.
- [ ] **Step 4: Run** the same. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "feat(football): palette, pips/possession paint helpers, smallsign band board and ticker wording"`

---

### Task 5: Widget: config, modes, story selection, persistent cards

**Files:**
- Create: `plugins/football/src/led_ticker_football/scores.py`, `_card.py` (board-only for now; Task 6 adds the celebration)
- Test: `plugins/football/tests/{test_scores.py,test_card_dispatch.py}`

**Interfaces:**
- Consumes Tasks 2–4.
- Produces:
  - `select_stories(games, next_games, *, mode, teams, max_games, now_wall, final_hold_hours, tz) -> list[GameInfo]` — hockey's with `_later_this_week(g)` (`state == "future"`) replacing `_later_today` in `teams` picks and the `league` tail (upcoming by kickoff; `time_tbd` games sort last).
  - `@attrs.define class FootballScoreMonitor` — hockey's fields and `validate_config` messages with `football.scores`, default `final_hold_hours = 24`, `_LIST_FIELD_HINTS`; `start`, `update`, `_rebuild`, `_queue_plays` (hockey's `_queue_goals` over `plays_after_baseline`, with `_celebrated: dict[str, set[str]]` and `_celebrated_scores`). Cards get `bye = team in snap.bye_teams` for `next:` keys.
  - `@attrs.define class FootballGameCard(FrameAwareBase)` — hockey's `HockeyGameCard` with `Goal` → `ScoringPlay`, `bye: bool = False`, `queue_plays`/`replace_plays`/`drop_overturned`; `draw` dispatches scale ≤ 1 → `FootballBandBoard` / ticker, scale > 1 → `render_crawl` / `render_scoreboard` (Task 7; until then a stub `render_scoreboard` that clears the canvas is acceptable).

- [ ] **Step 1: Write failing tests**:
  - `test_scores.py`: `test_validate_unknown_team_suggests` (`["PHL"]` → message contains `Did you mean 'PHI'?`); `test_validate_mode_layout_timezone`; `test_teams_mode_selection_order` (live > final in hold > later this week > next game; two tracked teams in one game → one card); `test_final_hold_default_24h` (a final from 26 h ago at hold 24 is dropped; at 20 h kept); `test_league_mode_order_and_cap`; `test_live_mode_empty_when_nothing_live`; `test_demo_builds_five_cards_and_queues_td`; `test_cards_persist_across_polls` (same object identity after a second `_rebuild`); `test_stale_marks_cards`; `test_bye_flag_reaches_next_card`.
  - `test_card_dispatch.py`: hockey's (`test_scale1_uses_band_board`, `test_scale4_calls_render_scoreboard`, `test_ticker_layout_adds_padding`, `test_has_play_shape_is_sync_draw`).
- [ ] **Step 2: Run** `uv run pytest plugins/football/tests/test_scores.py plugins/football/tests/test_card_dispatch.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** `scores.py` and `_card.py`.
- [ ] **Step 4: Run** `uv run pytest plugins/football -q`. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "feat(football): football.scores widget — modes, selection, persistent cards"`

---

### Task 6: Scoring celebration

**Files:**
- Create: `plugins/football/src/led_ticker_football/_celebration.py`
- Modify: `_card.py` (the hockey celebration plumbing: `pending`, `_playing`, `_shown`, `hold_time`, `reset_frame`, `demo_plays`, `DEMO_EVERY`)
- Test: `plugins/football/tests/test_celebration.py`

**Interfaces:**
- Consumes `ScoringPlay`, `GameInfo`, `_paint`, `_palette`.
- Produces: hockey's `FLASH_FRAMES 12`, `CELEBRATION_FRAMES 80`, `CELEBRATION_SECONDS`, `MAX_QUEUED 3`, `HIGHLIGHT_FRAMES 40`, `phase_at`, `pulse`; `def flash_word(kind: str) -> str` (`TD → "TOUCHDOWN"`, `FG → "FIELD GOAL"`, `SAFETY → "SAFETY"`); `def render_flash(canvas, color, on, word: str, *, y_offset=0)` (smallsign uses `TD!`/`FG!`/`SAFETY` when the full word's measured width exceeds `canvas.width - 4`); `def render_detail(canvas, game, play, frame, *, y_offset=0, font=None)` — kind word in the team colour, scores (scoring team pulsing) from the play's snapshot, `play.text` ellipsized, `+PAT`/`+2PT` amber, `Q4 9:41` dim.

- [ ] **Step 1: Write failing tests** in `test_celebration.py`: hockey's suite renamed (`test_phase_timeline`, `test_flash_knocks_out_word` on bigsign + `test_small_flash_shortens_word`, `test_detail_draws_play_text` on all three signs, `test_hold_time_extends_while_celebration_pending` (base 3.0 + 1 play → 7.0), `test_celebration_consumed_after_one_visit`, `test_reset_without_drawing_keeps_pending`, `test_untracked_score_highlights_instead`, `test_queue_caps_at_three`, `test_overturned_play_drops_pending`, `test_paused_frames_do_not_advance_celebration`, `test_follow_up_replaces_pending_snapshot` (a `+PAT` follow-up at 27–17 replaces the pending 26–17 play, `pending` length stays 1, `extra == "+PAT"`), `test_demo_rearms_every_third_visit`).
- [ ] **Step 2: Run** `uv run pytest plugins/football/tests/test_celebration.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** `_celebration.py` and the card plumbing (copy hockey's `_card.py` celebration sections verbatim, renaming).
- [ ] **Step 4: Run** `uv run pytest plugins/football -q`. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "feat(football): touchdown / field goal / safety celebration on the card's next turn"`

---

### Task 7: Physical scoreboard: bigsign and longboi

**Files:**
- Create: `plugins/football/src/led_ticker_football/layouts/scoreboard.py`
- Test: `plugins/football/tests/test_layout_scoreboard.py`

**Interfaces:**
- Consumes Tasks 2, 4.
- Produces `def render_scoreboard(canvas, game, now, tz, *, y_offset=0, stale=False, highlight=None, bye=False) -> None`; geometry by `real.width` (`_LONG ≥ 400`, else `_BIG`), hockey's constants as the base:
  - **`_BIG`:** hockey rows (chip x2–7, abbrev x14 ladder 22…14, score right edge x108 size 26, divider y32 to x195). The hockey badge slot becomes the **possession triangle** (`h = 9`, pointing left at the team, x114–118, vertically centred on the row) and the SOG slot the **pips** (3× 4 px, 2-px gaps, at x126 on the row's lower half, only live). Status column right-aligned at x251: line 1 quarter 15 px amber (ladder 15…10), line 2 clock 18 px white (18…11), line 3 situation 12 px (`3RD & 4 · PHI 38`, cyan or red; ladder 12, 11, 10, then drop ` · spot`, then ellipsize). Final: `FINAL` 24 px white / `OT` 16 px amber, scores `GREEN`/`LOSER`, no triangle/pips. Next game: hockey's `_big_next` plus records 10 px gray after each name (`PHI 5-2 @ NYG 4-3`, records dropped first when the run doesn't fit) and the top-right label `NEXT GAME` / `BYE WEEK` / `PPD`.
  - **`_LONG`:** hockey sides (chip x6–13 / x498–505, abbrev x22 / right x490 ladder 28…18, scores right x168 / left x344 size 46); pips under the abbrevs at the SOG baseline (y54), triangle between the possessing score and the centre (x ≈ 176 pointing left for away, x ≈ 336 pointing right for home, h 13). Centre x256: quarter 15 px amber, clock 26 px white, situation 12 px (same ladder/drop order). Final and next-game as hockey's `_long_board`/`_long_next`; records sit after the abbrevs on the name row at 12 px gray (next game only), and the nickname row ellipsizes first when the budget is short.
  - `highlight` as hockey (score fade); `stale` as hockey.

- [ ] **Step 1: Write failing tests** in `test_layout_scoreboard.py` (spy `_paint.hires`, `rect`, `triangle`, `pips`, `_dotted` as hockey):
  - `test_worst_case_keeps_min_clearance` parametrized over bigsign/longboi × {live `WSH 48 @ JAX 48`, Q4 `14:59`, JAX possession, `1ST & GOAL · WSH 50`, red zone, 3 timeouts each, `STALE`; `END Q3` halftime-style status; final OT 48–48 with `STALE`; next game `WSH 10-7 @ JAX 10-7` bye + `TBD`}: ≥ 6 px between any two recorded texts/shapes sharing rows, all inside the panel.
  - `test_possession_triangle_on_possessing_row` (bigsign: triangle recorded on the NYG row only; longboi: on the home side).
  - `test_pips_reflect_timeouts` (pips called with `remaining` 1 and 2; absent timeouts → not called).
  - `test_red_zone_situation_is_red`; `test_final_scores_colored`; `test_next_game_shows_records_day_and_bye`; `test_stale_label_beside_status`; `test_sparse_game_never_raises`.
- [ ] **Step 2: Run** `uv run pytest plugins/football/tests/test_layout_scoreboard.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** `layouts/scoreboard.py`.
- [ ] **Step 4: Run** `uv run pytest plugins/football -q`. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "feat(football): physical held scoreboard for bigsign and longboi"`

---

### Task 8: Docs, examples, CLAUDE.md, demo render check

**Files:**
- Create: `plugins/football/README.md`, `plugins/football/CLAUDE.md`
- Create: `plugins/football/examples/config.football-{demo,live}.{smallsign,bigsign,longboi}.toml` — copy hockey's six, swap type/teams (`["PHI", "NYG"]`) and the header comment ("Check the score, clock, possession marker and timeout pips.").
- Test: `plugins/football/tests/test_examples.py` (hockey's with `football.scores`, `config.football-*`, `["PHI", "NYG"]`).

- [ ] **Step 1: Write failing tests** (`test_all_six_examples_exist`, `test_examples_validate`, `test_examples_use_example_teams`, `test_readme_lists_every_option`).
- [ ] **Step 2: Run** `uv run pytest plugins/football/tests/test_examples.py -q`. Expected: FAIL.
- [ ] **Step 3: Write the README** in hockey's section order: disclosure (ESPN unofficial, host fallback, not affiliated), install, options table (all attrs fields + `update_interval`), modes (week-based wording; offseason/bye notes), layouts per sign, the scoring celebration (TD/FG/SAFETY, extra point folds in, hold extension, first-sight baseline, corrections), polling cadence (15/60/300/3600, schedule 6 h, no local clock tick and why), sign checks, known limitations (unofficial feed; live `situation` shape hand-written until a live capture; the sign runs ahead of TV; NFL only), data, development. Include a short "Reading the board" glossary (quarter, down & distance, spot, timeouts, red zone) for users new to football.
- [ ] **Step 4: Write `CLAUDE.md`** in hockey's shape; invariants: import purity; source never raises + host fallback order; one shared source; **scoring is delta-derived, `lastPlay` only decorates** (never fetch `summary`); PAT/2PT follow-ups re-key the pending play; possession hold rules; clocks not ticked; first-sight baseline in the source / celebrated state on the card; `reset_frame` consumption; `hold_time` property + the core line; `segments()` single wording source; cards persistent; the layout tripwire (incl. triangle/pips as shapes); hi-res never pixel-pinned; palette one hue per field (`RED` reserved for the red zone).
- [ ] **Step 5: Run** `uv run pytest plugins/football --cov=plugins/football/src --cov-report=term-missing && uv run ruff check plugins/football && uv run ruff format --check plugins/football && uv run pyright plugins/football/src`. Expected: PASS, coverage ≥ 90.
- [ ] **Step 6: Visual check.** From the core repo, render each demo example headlessly (`make render-demo`, see the `making-a-gif` skill) to the scratchpad and Read the PNGs: check possession marker, pips, down & distance, red-zone colour (force it via a demo tweak locally if needed), the celebration frames, final and bye cards on all three signs. Fix clipping; re-run Step 5.
- [ ] **Step 7: Commit** `git commit -m "docs(football): README, CLAUDE.md and per-sign example configs"`
