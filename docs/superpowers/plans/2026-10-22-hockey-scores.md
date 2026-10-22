# Hockey Scores Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `led-ticker-hockey`, a `hockey.scores` widget that shows live NHL scores, a goal celebration, and final and next-game cards on the smallsign, bigsign and longboi.

**Architecture:** A new uv workspace member, `plugins/hockey/`, shaped like `plugins/tennis/`:
- `_source.py` is a shared, never-raising fetcher over `api-web.nhle.com`.
- `_models.py` holds the pure parsing and formatting helpers.
- `scores.py` is the Container widget. It keeps one persistent `HockeyGameCard` per game id, so celebration state survives polls.
- `_card.py` dispatches on scale: the scale-1 bitmap board (`_scoreboard.py`) or the scale>1 physical renderers in `layouts/`.

The celebration is a frame-counter timeline inside the card. The card's `hold_time` property extends the engine hold while a celebration is pending. The engine reads it via `max(section_hold, getattr(widget, "hold_time", 0.0))` at `led-ticker/src/led_ticker/ticker.py:762`.

**Tech Stack:** Python 3.14, attrs, aiohttp, `led_ticker.plugin` public surface, pytest + pytest-asyncio, ruff, pyright.

**Spec:** `docs/superpowers/specs/2026-10-22-hockey-scores-design.md` (mockups in `docs/superpowers/specs/2026-10-22-hockey-mockups/`).

**Read before starting:**
- `plugins/tennis/CLAUDE.md`. Its invariants are inherited verbatim unless this plan says otherwise.
- `plugins/tennis/src/led_ticker_tennis/{_source.py,_card.py,scores.py,layouts/scoreboard.py,_paint.py}`.
- `plugins/tennis/tests/{conftest.py,test_layout_scoreboard.py}`.

## Global Constraints

- Python **3.14+**. `led-ticker-core>=4.30`, `aiohttp>=3.12`. **No `from __future__ import annotations`.**
- Import `led_ticker` **only** from `led_ticker.plugin` (AST tripwire `test_import_purity.py`).
- Package `led-ticker-hockey`, module `led_ticker_hockey`, entry point `hockey = "led_ticker_hockey:register"`, widget `hockey.scores`. Version via hatch-vcs with tag match `hockey-v*`.
- Base URL `https://api-web.nhle.com`. No API key.
- Example teams are `PHI` and `NYI` in every doc, demo and example.
- Coverage `fail_under = 90`. ruff check + format check, and pyright on `src`, must be clean.
- Layout invariant: measured widths, ≥ **6 px** clearance between texts sharing a vertical band, row-uniform name sizes, ellipsis at the floor.
- Hi-res text is never pixel-pinned in tests. Assert extents, bands, ordering and colors.
- Never raise into the poll loop or the render loop. Bad data becomes `stale`, never a crash. Never infer a final from a game disappearing.
- Palette (0–255):
  - `WHITE (255,255,255)` score/clock
  - `AMBER (255,180,0)` period/PP/date
  - `CYAN (0,200,220)` SOG
  - `DIM (70,70,70)` labels/dividers
  - `GREEN (0,220,90)` final winner score
  - `LOSER (120,120,120)` final loser score
  - `GRAY (110,110,110)` `@`, goal count
  - Team chips: `PHI` primary `(255,90,0)`, secondary `(255,90,0)`. `NYI` primary `(40,110,255)`, secondary `(255,130,40)`.
- Mode names `teams` / `league` / `live`. Layout names `auto` / `scoreboard` / `ticker`. `auto` → `scoreboard` at every scale.

## Review Focus

1. **A team code typo** (`teams = ["PHL"]`) should be rejected at validate time with a `Did you mean 'PHI'?` hint, not silently show nothing. Owned by Task 5 (`test_validate_unknown_team_suggests`).
2. **Feed shape drift:** a game row missing `clock`, `periodDescriptor` or `homeTeam.score`, or with `gameState = "WEIRD"`, should parse to a non-live game or be skipped. It must never raise. Owned by Task 2 (`test_parse_game_sparse_rows_never_raise`).
3. **Restart mid-game** should not replay the night's goals. Owned by Task 3 (`test_first_sight_goals_are_baseline`).
4. **A section hold shorter than the celebration** should still play the celebration once in full, then never again. Owned by Task 6 (`test_hold_time_extends_while_celebration_pending`, `test_celebration_consumed_after_one_visit`).
5. **Worst-case text** (`SOG 99` both rows, two-digit scores, `PP` + `EN` together, `FINAL/SO`, a 9-char nickname) must keep ≥6 px clearance on bigsign and longboi. Owned by Task 7 (`test_worst_case_keeps_min_clearance`).

---

### Task 1: Package scaffold, teams table, live fixtures

**Files:**
- Create: `plugins/hockey/{pyproject.toml,Makefile,LICENSE}`. Copy from tennis and swap names, description, keywords (`hockey`, `nhl`), the `hockey-v*` tag match and the wheel package path. Drop the `maintainers` entry.
- Create: `plugins/hockey/src/led_ticker_hockey/__init__.py`, which holds `register(api)` → `api.widget("scores")(HockeyScoreMonitor)`. Until Task 5 it imports a stub class from `scores.py`.
- Create: `plugins/hockey/src/led_ticker_hockey/teams.py`
- Create: `plugins/hockey/tests/fixtures/*.json`
- Create: `plugins/hockey/tests/{conftest.py,test_import_purity.py,test_smoke.py,test_teams.py}`. Copy `conftest.py`, `test_import_purity.py` and `test_smoke.py` from tennis and adapt them. The conftest keeps the `smallsign`/`bigsign`/`longboi` fixtures and resets `_SHARED_SOURCES`, so Task 3 must also define it.
- Modify: root `README.md` plugin table. Add a row: `| Hockey | led-ticker-hockey | hockey.scores | NHL public web API (no key) |`.

**Interfaces:**
- Produces `teams.py`:
  - `NHL_TEAMS: dict[str, TeamInfo]`, keyed by upper-case abbrev, with all 32 teams: ANA BOS BUF CGY CAR CHI COL CBJ DAL DET EDM FLA LAK MIN MTL NSH NJD NYI NYR OTT PHI PIT SJS SEA STL TBL TOR UTA VAN VGK WSH WPG.
  - `@dataclass(frozen=True) class TeamInfo: abbrev: str; city: str; nickname: str; primary: tuple[int,int,int]; secondary: tuple[int,int,int]`. Colors are lifted so no channel set is all-dark: max channel ≥ 90.
  - `def team(abbrev: str) -> TeamInfo`. Unknown codes return a neutral `TeamInfo(abbrev, "", abbrev, (200,200,200), (200,200,200))`, never raise.
  - `def normalize_team(code: str) -> str | None` returns the upper-cased code if known, else `None`.
- Produces fixtures under `tests/fixtures/`: `score_live.json`, `score_final_ot.json`, `score_future.json`, `landing_pp.json`, `landing_en.json`, `club_week_phi.json`, `club_season_nyi.json`.

- [ ] **Step 1: Capture real payloads.** `curl -s https://api-web.nhle.com/v1/score/now > /tmp/score_now.json`. Also curl `/v1/club-schedule/PHI/week/now` and `/v1/club-schedule-season/NYI/now`. Trim each fixture to 2–3 games and keep every field the spec lists.
  - If a game is LIVE at capture time, curl its `/v1/gamecenter/{id}/landing` and record the actual `situation` shape in the PR description.
  - If none is live, hand-write `landing_pp.json` with `{"situation": {"homeTeam": {"abbrev": "NYI", "situationDescriptions": ["PP"], "strength": 5}, "awayTeam": {"abbrev": "PHI", "strength": 4}, "situationCode": "1451", "timeRemaining": "01:42", "secondsRemaining": 102}}`. Hand-write `landing_en.json` with `situationCode "0651"`. Add a top-level `"_handwritten": true` key to both and list "verify landing.situation against a live game" as an open item in the PR body.
  - Hand-edit the score fixtures to PHI/NYI where needed: live 2nd 12:34, PHI 2 NYI 1, SOG 18–22, plus one OT final PHI 3 NYI 2.
- [ ] **Step 2: Write failing tests** in `test_teams.py`:
  - `test_all_32_teams_present`: `len(NHL_TEAMS) == 32` and the set equals the list above.
  - `test_flyers_and_islanders_colors`: `team("phi").primary == (255,90,0)`; `team("NYI").secondary == (255,130,40)`.
  - `test_unknown_team_is_neutral`: `team("XXX").primary == (200,200,200)`.
  - `test_colors_are_led_visible`: every team's `max(primary) >= 90` and `max(secondary) >= 90`.
  - `test_normalize_team`: `normalize_team("phi") == "PHI"`; `normalize_team("PHL") is None`.
- [ ] **Step 3: Run.** `uv run pytest plugins/hockey -q`. Expected: FAIL (import error).
- [ ] **Step 4: Implement `teams.py`**, plus the stub `scores.py` (`class HockeyScoreMonitor: pass`) and `__init__.py`. Then `uv sync --extra dev` at the repo root so the workspace picks up the member.
- [ ] **Step 5: Run.** `uv run pytest plugins/hockey -q && uv run ruff check plugins/hockey && uv run ruff format --check plugins/hockey`. Expected: PASS, including `test_import_purity` and `test_smoke`.
- [ ] **Step 6: Commit.** `git add plugins/hockey README.md uv.lock && git commit -m "feat(hockey): scaffold led-ticker-hockey with the 32-team table and feed fixtures"`

---

### Task 2: Models: parsing and formatting

**Files:**
- Create: `plugins/hockey/src/led_ticker_hockey/_models.py`
- Test: `plugins/hockey/tests/test_models.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class Goal: key: str; team: str; scorer: str; season_total: int | None; assists: tuple[str, ...]; period_label: str; time_in_period: str; strength: str; empty_net: bool; away_score: int; home_score: int`
    - `key = f"{period}:{timeInPeriod}:{playerId}"`.
    - `scorer` is the upper-cased last name.
    - `assists` are upper-cased last names.
  - `@dataclass(frozen=True) class Situation: pp_team: str | None; pp_seconds: int | None; en_team: str | None`
    - `en_team` = the team whose goalie digit is `0`.
  - `@dataclass(frozen=True) class GameInfo: game_id: int; state: str; away: str; home: str; away_score: int; home_score: int; away_sog: int | None; home_sog: int | None; period: int; period_type: str; clock_seconds: int | None; clock_running: bool; in_intermission: bool; start_utc: datetime | None; venue: str; final_type: str | None; goals: tuple[Goal, ...]; situation: Situation | None = None; polled_at: float = 0.0`
    - `state ∈ {"future", "live", "final"}`. `FUT`/`PRE` → future, `LIVE`/`CRIT` → live, `FINAL`/`OFF` → final, anything else → future.
    - `final_type ∈ {None, "OT", "SO"}`.
  - `def parse_game(row: dict, *, polled_at: float) -> GameInfo | None`. Returns `None` for rows without an id or either team abbrev. Every other missing field gets a default.
  - `def parse_situation(landing: dict) -> Situation | None`. Reads `situation.situationCode` (4 digits: away goalie, away skaters, home skaters, home goalie) plus `situation.secondsRemaining`. Returns `None` on any mismatch.
  - `def period_label(period: int, period_type: str) -> str`. Returns `1ST`/`2ND`/`3RD`, `OT` for the first OT, `2OT`, `3OT`… for later ones, and `SO`.
  - `def live_clock_seconds(game: GameInfo, now: float) -> int | None`. If running: `max(0, clock_seconds - int(now - polled_at))`. Otherwise `clock_seconds`.
  - `def live_pp_seconds(game: GameInfo, now: float) -> int | None`. Same rule applied to `situation.pp_seconds`. It only ticks while `clock_running`.
  - `def fmt_clock(seconds: int | None) -> str`. Returns `m:ss`, or `""` for `None`. Under one minute it is still `0:42`.
  - `def status_lines(game: GameInfo, now: float, tz: ZoneInfo) -> tuple[str, str]`:
    - live: `(period_label, fmt_clock)`
    - intermission: `(f"{period_label} INT", fmt_clock)`
    - final: `("FINAL", final_type or "")`
    - future: `(day_label, "7:00 PM")`
  - `def day_label(start_utc: datetime, now_utc: datetime, tz: ZoneInfo) -> str`. Returns `TODAY`, or `TONIGHT` when the local start hour ≥ 17 on the same local date. Otherwise `FRI OCT 23`.
  - `def winner(game: GameInfo) -> str | None`. Returns the team code with the higher score, only when `state == "final"`.
  - `def build_demo_games(now: float) -> list[GameInfo]`. Four PHI/NYI games:
    - live 2nd 12:34, PHI 2 NYI 1, SOG 18–22, NYI PP 1:42, with a PHI goal `KONECNY (5)` assisted by `MICHKOV`, `SANHEIM` at `2ND 7:26`
    - intermission
    - an OT final PHI 3 NYI 2
    - a future game Fri 7:00 PM at UBS Arena

- [ ] **Step 1: Write failing tests** in `test_models.py`:
  - `test_parse_live_fixture`: `score_live.json` → PHI/NYI game with `state == "live"`, scores 2/1, sog 18/22, `period_label(...) == "2ND"`, `clock_seconds == 754`.
  - `test_parse_final_ot`: `final_type == "OT"` and `winner(g) == "PHI"`.
  - `test_parse_game_sparse_rows_never_raise`: rows `{}`, `{"id": 1}`, a row with `gameState: "WEIRD"`, and a row missing `clock`. None raise. The first two return `None`; the WEIRD one has `state == "future"`.
  - `test_situation_pp_and_en`: `landing_pp.json` gives `pp_team == "NYI"` and `pp_seconds == 102`. `landing_en.json` gives `en_team == "PHI"`. `parse_situation({}) is None`.
  - `test_period_labels`: (1,REG)→`1ST`, (3,REG)→`3RD`, (4,OT)→`OT`, (5,OT)→`2OT`, (5,SO)→`SO`.
  - `test_clock_ticks_while_running`: polled 754 s at t=100, `now=110` → 744. Not running → 754. Never below 0.
  - `test_fmt_clock`: 754→`12:34`, 42→`0:42`, None→`""`.
  - `test_day_label`: a same-day 19:00 local start → `TONIGHT`; same-day 13:00 → `TODAY`; next day → `FRI OCT 23`.
  - `test_goal_key_and_names`: goal `scorer` upper-cased last name, `season_total` from `goalsToDate`, `empty_net` true when `goalModifier == "empty-net"`.
- [ ] **Step 2: Run.** `uv run pytest plugins/hockey/tests/test_models.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement `_models.py`.** Every dict read goes through `.get` with a default. Names come from `name.default`, or from `lastName.default` when present.
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit.** `git commit -m "feat(hockey): parse NHL score/landing payloads into GameInfo"`

---

### Task 3: Source: shared fetcher, cadence, goal baseline

**Files:**
- Create: `plugins/hockey/src/led_ticker_hockey/_source.py`
- Test: `plugins/hockey/tests/test_source.py`

**Interfaces:**
- Consumes `parse_game`, `parse_situation`, `GameInfo`, `Goal` (Task 2).
- Produces:
  - `LIVE_INTERVAL = 15`, `PREGAME_INTERVAL = 300`, `IDLE_INTERVAL = 3600`, `SEASON_INTERVAL = 6 * 3600`, `MIN_INTERVAL = 10`, `MAX_BACKOFF = 4 * 3600`, `REQUEST_TIMEOUT = 20`
  - `@dataclass class Snapshot: games: dict[int, GameInfo]; next_games: dict[str, GameInfo]; stale: bool; error: str | None`
  - `class NHLSource`:
    - `__init__(self, session, *, clock: Callable[[], float] = time.monotonic, wall: Callable[[], datetime] = lambda: datetime.now(UTC))`
    - `def want(self, *, teams: set[str], all_games: bool, tz: ZoneInfo, final_hold_hours: int) -> None` merges interest from every widget sharing the source.
    - `def note_displayed(self, game_ids: set[int]) -> None` limits landing calls to games on screen.
    - `async def poll(self) -> Snapshot` never raises.
    - `def next_delay(self) -> float`
    - `def new_goals(self, game_id: int) -> list[Goal]` returns and clears goals first observed since the previous poll. Goals present on first sight of a game are the silent baseline.
  - `_SHARED_SOURCES: dict[int, NHLSource]`, keyed by `id(session)`, capped at 8.
  - `def shared_source(session) -> NHLSource`

Poll algorithm (per `poll()`):
1. Fetch `/v1/score/{local_date}`. Also fetch `/v1/score/{local_date - 1}` while any final from yesterday is within `final_hold_hours`. Do the same during the first `final_hold_hours` after local midnight.
2. For each live wanted game in the displayed set, fetch `/v1/gamecenter/{id}/landing` and attach `parse_situation`.
3. For each wanted team with no game today, fetch `/v1/club-schedule/{TEAM}/month/now` for the first `FUT` game. If there is none, fetch `/v1/club-schedule-season/{TEAM}/now`, at most once per `SEASON_INTERVAL`.
4. On any HTTP error, JSON error or exception: keep the previous games and set `stale = True`. Backoff starts at `2 × base` and doubles, capped at `MAX_BACKOFF`. A success resets it.

`next_delay()` returns `LIVE_INTERVAL` if any wanted game is live, else `PREGAME_INTERVAL` if one is scheduled today, else `IDLE_INTERVAL`. The current backoff overrides all three.

- [ ] **Step 1: Write failing tests** in `test_source.py`. Use a fake aiohttp session that maps URL → (status, body), as in tennis `test_source.py`.
  - `test_poll_parses_today`: `score_live.json` → `snap.games` contains the PHI/NYI game, `stale is False`.
  - `test_failure_keeps_last_good_and_marks_stale`: a 500 after a success keeps the same game and sets `stale is True`.
  - `test_malformed_body_never_raises`: a body of `"nope"` or `{"games": "x"}` → no exception, `stale is True`.
  - `test_backoff_ladder`: consecutive failures give `next_delay()` of 30, 60, 120… capped at 14400.
  - `test_cadence_live_vs_idle`: a live wanted game → 15. Only a future game today → 300. Nothing → 3600.
  - `test_landing_only_for_displayed_live`: the landing URL is requested only after `note_displayed({id})`.
  - `test_first_sight_goals_are_baseline`: the first poll with 2 goals → `new_goals(id) == []`. The next poll with 3 goals → exactly the third. Calling again → `[]`.
  - `test_disallowed_goal_drops_from_baseline`: a goal that disappears from the feed is not re-reported if it returns with the same key.
  - `test_next_game_falls_back_to_season`: an empty month schedule makes a season request. A second poll within 6 h does not repeat it.
  - `test_yesterday_fetched_inside_hold_window`: `wall` = 00:30 local, `final_hold_hours = 6` → both dates requested.
  - `test_shared_source_is_per_session_and_capped`: same session → same object; a 9th session evicts the oldest.
- [ ] **Step 2: Run.** `uv run pytest plugins/hockey/tests/test_source.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement `_source.py`.** Use User-Agent `led-ticker-hockey (+https://github.com/JamesAwesome/led-ticker-plugins)` and `aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)`. Wrap every network/parse step in `try/except Exception` → `_fail()`.
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit.** `git commit -m "feat(hockey): shared NHL source with live cadence, backoff and goal baseline"`

---

### Task 4: Palette, paint helpers, scale-1 board and ticker wording

**Files:**
- Create: `plugins/hockey/src/led_ticker_hockey/{_palette.py,_paint.py,_scoreboard.py}`
- Create: `plugins/hockey/src/led_ticker_hockey/layouts/{__init__.py,crawl.py}`
- Test: `plugins/hockey/tests/{test_scoreboard.py,test_layout_crawl.py,test_resolve_layout.py}`

**Interfaces:**
- Consumes `GameInfo`, `status_lines`, `live_pp_seconds`, `fmt_clock`, `winner` (Task 2) and `team` (Task 1).
- Produces:
  - `_palette.py`: the Global Constraints colors as `Color` constants via `make_color`, plus `def chip(abbrev) -> tuple[Color, Color]` and `def dim(color, factor) -> Color`.
  - `_paint.py`: copy tennis `_paint.py` as-is, plus `def rect(real, x0, y0, x1, y1, color) -> None` (inclusive bounds, clipped to the canvas).
  - `layouts/__init__.py`: `VALID_LAYOUTS = ("auto", "scoreboard", "ticker")` and `def resolve_layout(cfg_layout: str, scale: int, phys_w: int) -> str` (`auto` → `scoreboard`).
  - `layouts/crawl.py`: `def segments(game: GameInfo, now: float, tz) -> list[tuple[str, Color]]`. This is the single wording source.
    - Live: `PHI 2 · NYI 1 · 2ND 12:34 · NYI PP 1:42 · SOG 18-22`
    - Final: `PHI 3 · NYI 2 · FINAL/OT`
    - Future: `PHI @ NYI · FRI OCT 23 7:00 PM · UBS ARENA`
    - Plus `def render_crawl(canvas, game, now, tz, cursor_pos, *, y_offset=0, hold_padding=6) -> int` (logical width), the tennis crawl contract.
  - `_scoreboard.py`:
    - `class HockeyBandBoard(FrameAwareBase)` with `game`, `now_fn`, `tz`, `highlight: tuple[str, float] | None = None` (team, 0–1 fade toward white). Its `draw()` returns `(canvas, canvas.width)`.
    - `def build_ticker_message(game, now, tz, *, font, bg_color, font_color) -> SegmentMessage`, built by joining `segments()`.
  - The band board geometry is the mockup's: chip `x0–2`; abbrev `x5`; score `x28`; `SOG` dim at `x40` and its value at `x60`; `PP m:ss` amber at `x84` on the PP team's band, or `EN` amber at `x84` when that team's goalie is pulled. Period is right-aligned in the top band and clock right-aligned in the bottom band. Away band rows `0–7`, home band `8–15`. Use core `FONT_SMALL` (5×8) via the same draw path as the tennis legacy board.

- [ ] **Step 1: Write failing tests:**
  - `test_resolve_layout_auto_is_scoreboard_everywhere`: (auto,1,160), (auto,4,256), (auto,4,512) all → `scoreboard`. `ticker` stays `ticker`.
  - `test_segments_live_wording`: the joined text equals the live string above for the demo live game at `now = polled_at`.
  - `test_segments_final_and_future`: the final and future strings above.
  - `test_band_board_lights_both_bands_and_right_column` (smallsign fixture): lit pixels exist in rows 0–7 and 8–15. Pixels in the `PHI` orange exist at x≤2 in rows 0–7. Lit pixels exist in the right-most 30 columns of both bands.
  - `test_band_board_pp_on_home_band_only`: amber pixels exist in x 84–124 in rows 8–15, and none there in rows 0–7.
  - `test_band_board_final_winner_green`: `GREEN` pixels exist in the score column of the winner's band only.
  - `test_band_board_highlight_score`: with `highlight="NYI"`, the NYI score column is drawn in `AMBER`, not `WHITE`.
- [ ] **Step 2: Run.** `uv run pytest plugins/hockey/tests -q -k "scoreboard or crawl or resolve"`. Expected: FAIL.
- [ ] **Step 3: Implement** the files above. `render_crawl` mirrors tennis `layouts/crawl.py`, painting `segments()` in hi-res.
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit.** `git commit -m "feat(hockey): scale-1 band board and single-source ticker wording"`

---

### Task 5: Widget: config, modes, story selection

**Files:**
- Modify: `plugins/hockey/src/led_ticker_hockey/scores.py` (replace the stub)
- Create: `plugins/hockey/src/led_ticker_hockey/_card.py`. Minimal for now: holds a `GameInfo`, dispatches scale-1 to `HockeyBandBoard` or the ticker message, and scale>1 to `render_crawl` or a placeholder `layouts.scoreboard.render_scoreboard` that Task 7 fills in.
- Test: `plugins/hockey/tests/{test_scores.py,test_card_dispatch.py}`

**Interfaces:**
- Consumes `shared_source`, `NHLSource.want/poll/note_displayed/new_goals/next_delay` (Task 3), `build_demo_games` (Task 2) and `normalize_team`/`NHL_TEAMS` (Task 1).
- Produces:
  - `@attrs.define class HockeyScoreMonitor`. Fields: `session`, `mode: str = "teams"`, `teams: list[str] = []`, `max_games: int = 8`, `final_hold_hours: int = 6`, `timezone: str = "America/New_York"`, `padding: int = 6`, `hold_time: float = 0.0`, `demo: bool = False`, plus kw-only `bg_color`, `font_color`, `font`, `small_font`, `layout = "auto"`. Also `feed_stories: list` and a private `_cards: dict[int | str, HockeyGameCard]`, keyed by game id or by `f"next:{TEAM}"`.
  - `@classmethod validate_config(cls, cfg) -> list[str]` checks:
    - `mode` is one of `teams`/`league`/`live`.
    - `teams` is a list of str, every one known (else `hockey.scores teams has unknown code 'PHL'. Did you mean 'PHI'?`, via `difflib` over `NHL_TEAMS`).
    - `teams` is non-empty when `mode == "teams"`.
    - `layout` is in `VALID_LAYOUTS` (tennis wording).
    - `timezone` is IANA. `max_games` is int ≥ 1. `final_hold_hours` is int ≥ 0. `demo` is bool. `update_interval` is int ≥ 1.
  - `@classmethod async start(cls, session, update_interval: int = LIVE_INTERVAL, **kwargs) -> Self`. Demo loads `build_demo_games`. Otherwise it registers `want(...)`, does one `update()`, then calls `spawn_tracked(run_monitor_loop(widget, interval))`, where `interval = max(MIN_INTERVAL, update_interval)` and the loop sleeps `source.next_delay()` when that is longer. Mirror tennis `start()`.
  - `async def update(self) -> None` polls, then rebuilds `feed_stories` by reusing or creating `HockeyGameCard`s, updating `card.game` in place. It queues `source.new_goals(id)` onto cards (Task 6 consumes them), calls `note_displayed(...)`, and logs INFO `hockey.scores updated: N stories`.
  - `class HockeyGameCard(FrameAwareBase)` (`_card.py`). Fields: `game: GameInfo`, `tz`, `cfg_layout`, `padding`, `now_fn = time.monotonic`, `tracked: frozenset[str]`, `stale: bool = False`, `base_hold: float = 0.0` (widget `hold_time`), plus kw-only fonts and colors.

Story selection (pure helper `select_stories(games, next_games, *, mode, teams, max_games, now_wall, final_hold_hours) -> list[GameInfo]`):
- **`teams`:** for each tracked team in config order, pick its live game today if any. Else a final inside the hold. Else a future game today. Else its next game. Dedupe by `game_id`, so PHI-vs-NYI appears once.
- **`league`:** tracked-team games first (ordered as for `teams`, excluding next-game cards), then other live games, then finals inside the hold, then future games today by start time. Capped at `max_games`.
- **`live`:** only live games, tracked teams first, capped at `max_games`. An empty result gives an empty `feed_stories`.
- **Stale:** when `snap.stale`, cards keep their last game and gain `stale=True`. Renderers draw `STALE` in `DIM` beside the status column (Task 7 places it; scale-1 replaces the `SOG` label with `STALE`).
- **Nothing in `teams` mode:** no stories at all, which is the offseason case.

- [ ] **Step 1: Write failing tests:**
  - `test_validate_unknown_team_suggests`: `teams=["PHL"]` → a message containing `Did you mean 'PHI'?`.
  - `test_validate_teams_mode_requires_teams`, `test_validate_bad_mode`, `test_validate_bad_layout_suggests`.
  - `test_select_teams_mode_dedupes_head_to_head`: PHI@NYI live with `teams=["PHI","NYI"]` → 1 story.
  - `test_select_teams_mode_final_replaces_next_until_hold_expires`: a final 2 h ago with hold 6 → final card. 7 h ago → next-game card.
  - `test_select_teams_mode_game_later_today`: a future game today → that game, which renders as next-game with `TONIGHT`.
  - `test_select_league_order`: tracked live, then other live, then finals, then future, and the cap is honored.
  - `test_select_live_mode_empty_when_nothing_live`: → `[]`.
  - `test_update_reuses_cards_across_polls`: two `update()` calls keep the same card object for the same game id.
  - `test_demo_builds_four_stories_without_network`: `demo=True`, `session=None` → 4 stories, no source.
  - `test_card_dispatch_scale1_vs_scale4`: on smallsign the card delegates to `HockeyBandBoard`; on bigsign it calls `render_scoreboard` (monkeypatched spy). Held layouts return `cursor == canvas.width`.
- [ ] **Step 2: Run.** `uv run pytest plugins/hockey/tests/test_scores.py plugins/hockey/tests/test_card_dispatch.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** `scores.py` and `_card.py` (frame hooks forward to the legacy story, as in tennis `_card.py`).
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit.** `git commit -m "feat(hockey): hockey.scores widget with teams/league/live modes"`

---

### Task 6: Goal celebration timeline and consumption

**Files:**
- Create: `plugins/hockey/src/led_ticker_hockey/_celebration.py`
- Modify: `plugins/hockey/src/led_ticker_hockey/_card.py`, `plugins/hockey/src/led_ticker_hockey/scores.py`
- Test: `plugins/hockey/tests/test_celebration.py`

**Interfaces:**
- Consumes `Goal` (Task 2), `HockeyGameCard` and `update()` (Task 5), and `_paint.rect`/`hires` (Task 4).
- Produces:
  - `FLASH_FRAMES = 12` (3 × on 2 frames / off 2 frames at the engine's 50 ms tick). `CELEBRATION_FRAMES = 80` (4 s). `MAX_QUEUED = 3`. `HIGHLIGHT_FRAMES = 40`.
  - `def phase_at(frame: int, n_goals: int) -> tuple[int, str, int] | None` returns `(goal_index, "flash_on" | "flash_off" | "detail", frame_in_goal)`, or `None` once `frame >= n_goals * CELEBRATION_FRAMES`.
  - `def pulse(frame: int) -> float` = `0.55 + 0.45 * (0.5 + 0.5 * cos(frame * 50 / 180))`, the mockup's pulse.
  - `def render_flash(canvas, color: Color, on: bool) -> None` fills the whole real canvas with `color` when `on` and knocks out `GOAL` (unlit). Smallsign uses the bitmap font, centered; scale>1 uses hi-res 40 px (bigsign) or 44 px (longboi), centered.
  - `def render_detail(canvas, game: GameInfo, goal: Goal, frame: int) -> None`, per sign per `states.html` §1:
    - smallsign: top band `GOAL` in team color, then `PHI 2 NYI 1` at the right with the scorer's score pulsing. Bottom band `KONECNY (5)` white, plus `2ND 7:26` dim at the right.
    - bigsign: chip plus `GOAL` 26 px; a compact score at the top right; a divider; scorer 17 px plus `(5)` gray; assists cyan 9 px; time dim at the right.
    - longboi: chip plus `GOAL` 40 px on the left; scorer 24 px with assists below in the center; a stacked score on the right; time dim at the bottom right.
  - `HockeyGameCard`:
    - `pending: list[Goal]` (cap `MAX_QUEUED`, oldest dropped)
    - `highlight: tuple[str, int] | None` (team, frames left)
    - `def queue_goals(self, goals: list[Goal]) -> None` sends tracked-team goals to `pending` and any other goal to `highlight = (team, HIGHLIGHT_FRAMES)`
    - `@property hold_time -> float` returns `base_hold + len(pending) * CELEBRATION_FRAMES * 0.05` while `pending`, else `base_hold`. `base_hold` is the widget's `hold_time`, passed to the card.
  - In `draw()`: if `pending` and `phase_at(self._frame_count, len(pending))` is not `None`, render the celebration. Otherwise render the board, passing `highlight` with a fade from AMBER to WHITE over `HIGHLIGHT_FRAMES`.
  - In `reset_frame()` (visit entry), **before** calling super: if `self._frame_count > 0 and self.pending`, clear `pending` (consumed). If a highlight was shown, clear it.
  - An overturned goal (`update()` sees a score go down for a game) drops `pending` goals whose `away_score`/`home_score` exceed the new score.

- [ ] **Step 1: Write failing tests** in `test_celebration.py`:
  - `test_phase_timeline`: frame 0 → flash_on; 2 → flash_off; 12 → detail; 79 → detail; 80 with 1 goal → `None`; 80 with 2 goals → `(1, "flash_on", 0)`.
  - `test_flash_fills_team_color_and_knocks_out_goal` (bigsign): at frame 0 most real pixels are PHI orange, and some pixels inside the central band are unlit.
  - `test_detail_draws_scorer_band` (all three sign fixtures): frame 20 lights white pixels in the scorer region, and the smallsign frame lights rows 8–15.
  - `test_hold_time_extends_while_celebration_pending`: card `hold_time` with base 3.0 and 1 pending goal → 7.0. With none → 3.0.
  - `test_celebration_consumed_after_one_visit`: queue 1; draw 5 frames via `advance_frame` + `draw`; `reset_frame()`; `pending == []`; the next draw renders the board (spy on `render_scoreboard`).
  - `test_reset_without_drawing_keeps_pending`: `reset_frame()` at frame 0 keeps it.
  - `test_untracked_goal_highlights_instead`: with `tracked={"PHI"}`, an NYI goal → `pending == []` and `highlight[0] == "NYI"`.
  - `test_queue_caps_at_three`: 5 goals → the last 3 are kept.
  - `test_overturned_goal_drops_pending`: a goal at 3–1, then the feed shows 2–1 → `pending` is empty.
  - `test_paused_frames_do_not_advance_celebration`: `pause_frame()`, then `advance_frame()` ×10 → `_frame_count` is unchanged (compositing safety).
- [ ] **Step 2: Run.** `uv run pytest plugins/hockey/tests/test_celebration.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** `_celebration.py` and the card/widget changes.
- [ ] **Step 4: Run** `uv run pytest plugins/hockey -q`. Expected: PASS.
- [ ] **Step 5: Commit.** `git commit -m "feat(hockey): goal celebration on the card's next turn, consumed once"`

---

### Task 7: Physical scoreboard: bigsign and longboi

**Files:**
- Create/replace: `plugins/hockey/src/led_ticker_hockey/layouts/scoreboard.py`
- Test: `plugins/hockey/tests/test_layout_scoreboard.py`

**Interfaces:**
- Consumes `GameInfo` and the helpers (Task 2), `_paint`/`_palette` (Task 4), and `team()` (Task 1).
- Produces `def render_scoreboard(canvas, game: GameInfo, now: float, tz, *, y_offset: int = 0, stale: bool = False, highlight: tuple[str, float] | None = None) -> None`, where `highlight` is (team, 0–1 fade toward white). Geometry is chosen by `real.width`: `_LONG` (≥ 400) or `_BIG` (< 400). There is no tennis-style story-index paging.

Arrangement is fixed by `live-board.html`/`states.html`. Sizes are starting values; shrink through ladders to satisfy the invariant.
- **`_BIG` (256×64):**
  - Two rows of 32 px with a dotted `DIM` divider at y=32, x 0–195.
  - Each row: chip `x3–8` (secondary color as the bottom 4 rows), abbrev 22 px at `x14` in team primary, score 26 px right-aligned at `x108`, `SOG nn` 11 px cyan at `x144`.
  - `PP` badge: an amber rect `x114–136`, unlit 11 px text, on the PP team's row. `EN` uses the same badge geometry in amber on the en team's row. If both apply to one row, `EN` wins (the goalie is pulled on the PP team).
  - Right status column right-aligned at `x251`: line 1 is 15 px amber (`status_lines[0]`), line 2 is 18 px white (`status_lines[1]`), line 3 is 12 px amber (`PP m:ss`) when there's a PP.
  - Final: status `FINAL` 16 px white and `OT`/`SO` 16 px amber; scores `GREEN`/`LOSER`.
  - Next game: top row `PHI @ NYI` (22 px names, 14 px gray `@`) with `NEXT GAME` 9 px gray at the top right; bottom row `day_label` 15 px amber on the left, time 15 px white on the right, venue 8 px dim.
  - `STALE` goes 9 px dim above the status column.
- **`_LONG` (512×64):**
  - Away on the left: chip `x6–13`, abbrev 28 px at `x22`, `SOG` 13 px cyan below, score 46 px right-aligned at `x168`. Home mirrors it: chip `x498–505`, abbrev right-aligned at `x490`, score left-aligned at `x344`.
  - Center at x=256: period 15 px amber, clock 26 px white, then the `PP` badge plus `TEAM m:ss` 12 px amber.
  - Final: `FINAL` 24 px white plus `OT` 16 px amber in the center.
  - Next game: nicknames 12 px (team primary dimmed 0.6–0.7) under the abbrevs; center `day_label` 14 px amber, time 26 px white, venue 10 px dim.
  - `STALE` 9 px dim at the top center-right of the status.

- [ ] **Step 1: Write failing tests** in `test_layout_scoreboard.py`. Spy on `_paint.hires` to record (text, x, y_top, size, width), as in tennis.
  - `test_worst_case_keeps_min_clearance`: parametrized over bigsign/longboi × {live with NYI PP and PHI EN, scores 10–10, SOG 99–99; final SO; next game for `CBJ` vs `VGK` with the nickname `BLUE JACKETS`}. Every pair of recorded texts whose vertical extents overlap keeps ≥ 6 px horizontal clearance between advance extents. Every text lies within `[0, real.width)`.
  - `test_pp_badge_on_pp_team_row` (bigsign): amber pixels in `x114–136` within the home row band (y 33–63) and none in the away row.
  - `test_final_scores_colored`: the winner's score pixels are `GREEN` and the loser's are `LOSER`.
  - `test_next_game_shows_day_and_venue`: recorded texts include `TONIGHT` (for a same-day 19:00 start) and `UBS ARENA`.
  - `test_stale_label_beside_status`: `stale=True` records a `STALE` text and the status line is still recorded.
  - `test_sparse_game_never_raises`: a `GameInfo` with `None` SOG, a `None` clock and no situation renders without exception on both signs.
- [ ] **Step 2: Run.** `uv run pytest plugins/hockey/tests/test_layout_scoreboard.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** `layouts/scoreboard.py`, following tennis's right-to-left measured layout and ladder pattern.
- [ ] **Step 4: Run** `uv run pytest plugins/hockey -q`. Expected: PASS.
- [ ] **Step 5: Commit.** `git commit -m "feat(hockey): physical held scoreboard for bigsign and longboi"`

---

### Task 8: Docs, examples, demo render check

**Files:**
- Create: `plugins/hockey/README.md`, `plugins/hockey/CLAUDE.md`
- Create: `plugins/hockey/examples/config.hockey-{demo,live}.{smallsign,bigsign,longboi}.toml`. Copy the tennis examples' `[display]`/`[web]` blocks, including longboi's FM6126A tuning.
- Test: `plugins/hockey/tests/test_examples.py`

**Interfaces:**
- Consumes the whole widget surface.

- [ ] **Step 1: Write failing tests:**
  - `test_examples_validate`: each example TOML loads with `tomllib`, and every `hockey.scores` widget block passes `HockeyScoreMonitor.validate_config(...) == []`.
  - `test_examples_use_example_teams`: each live example's `teams` equals `["PHI", "NYI"]`.
  - `test_readme_lists_every_option`: every attrs field of `HockeyScoreMonitor` that is user-facing appears in the README options table. Excluded fields: `session`, `feed_stories`, `_cards` and other private fields.
- [ ] **Step 2: Run.** `uv run pytest plugins/hockey/tests/test_examples.py -q`. Expected: FAIL.
- [ ] **Step 3: Write the README** in the tennis README's section order:
  - Disclosure that the feed is unofficial and undocumented, and may change.
  - Install. No key is needed.
  - Options table.
  - Modes.
  - Layouts per sign.
  - Goal celebration, including the note that a section's hold is extended automatically while a celebration is pending.
  - Polling cadence.
  - Offseason note: a section holding only `teams` mode can go dark.
  - The TV-delay caveat.
- [ ] **Step 4: Write `CLAUDE.md`** in the tennis CLAUDE.md shape. Its invariants:
  - Import purity.
  - The source never raises.
  - First-sight goal baseline in the source; the celebrated state lives on the card.
  - `reset_frame` consumption.
  - The `hold_time` property mechanism and its core line reference.
  - The `segments()` single wording source.
  - The layout tripwire.
  - Cards are persistent per game id, never rebuilt per poll.
- [ ] **Step 5: Run.** `uv run pytest plugins/hockey --cov=plugins/hockey/src --cov-report=term-missing && uv run ruff check plugins/hockey && uv run ruff format --check plugins/hockey && uv run pyright plugins/hockey/src`. Expected: all PASS, coverage ≥ 90 %.
- [ ] **Step 6: Visual check.** Render the three demo examples headlessly with the core repo's `make render-demo` (see the `making-a-gif` skill for duration). Compare against the mockups. Render the PNG/GIF to `/tmp` and Read it to inspect (the pixel-art iteration memory). Fix any clipping and re-run Step 5.
- [ ] **Step 7: Commit.** `git commit -m "docs(hockey): README, CLAUDE.md and per-sign example configs"`
