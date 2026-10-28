# Basketball Scores Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `led-ticker-basketball`: a `basketball.scores` widget with live NBA scores on a horizontal arena-style board (bundled team logos on bigsign/longboi, one band on smallsign), a final-buzzer win celebration, finals and next-game cards, a `:basketball.ball:` emoji — released to PyPI and documented on the docs site.

**Architecture:** A new uv workspace member `plugins/basketball/` cloned from `plugins/football/` file for file. `_source.py` is football's never-raising shared ESPN fetcher on hockey's **day** model (today + yesterday's slate), emitting one `FinalEvent` per game that went final after first sight. `_models.py` holds pure parsing (leaders, linescores, clutch). `scores.py` is the Container widget with one persistent `BasketballGameCard` per game; `_card.py` reuses football's celebration plumbing verbatim with `ScoringPlay` → `FinalEvent`. New: `_logos.py` decodes bundled 64×64 PNGs into cached sprites; `emoji.py` ships the ball. Renderers in `_scoreboard.py` (scale 1) and `layouts/` (scale > 1) are new designs, not football's.

**Tech Stack:** Python 3.14, attrs, aiohttp, Pillow (via core), `led_ticker.plugin` public surface, pytest + pytest-asyncio, ruff, pyright.

**Spec:** `docs/superpowers/specs/2026-10-28-basketball-scores-design.md`

**Read before starting:**
- The spec's "Basketball in one page" if you do not follow the sport.
- `plugins/football/CLAUDE.md` and `plugins/hockey/CLAUDE.md` — every invariant is inherited unless this plan says otherwise.
- `plugins/football/src/led_ticker_football/` — the whole package. Where a step says "as football", copy that function and adapt names. `plugins/hockey/src/led_ticker_hockey/_source.py` for the `_yesterday_ids` day model.
- `plugins/football/tests/{conftest.py,test_source.py,test_celebration.py,test_layout_scoreboard.py}`.
- `docs/superpowers/plans/2026-10-26-football-scores.md` — the sibling plan this one is shaped after.

**Branches.** Plugins repo: `feat/basketball-scores` in a worktree (`git worktree add ../led-ticker-plugins-basketball -b feat/basketball-scores`), PR to `main`. Core repo (Task 10): `docs/basketball-scores` in a worktree, PR to `main`. Never commit to `main`; never merge without James's per-PR go-ahead.

**Network.** The sandbox cannot reach ESPN. Task 1's two scripts (logo fetch, fixture capture) must be run by James; the plan marks those steps **HUMAN**. Everything after uses committed files only.

## Global Constraints

- Python **3.14+**; `led-ticker-core>=4.31`, `aiohttp>=3.12`; **no `from __future__ import annotations`**.
- Import `led_ticker` **only** from `led_ticker.plugin` (AST tripwire `test_import_purity.py`).
- Package `led-ticker-basketball`, module `led_ticker_basketball`, entry point `basketball = "led_ticker_basketball:register"`, widget `basketball.scores`, emoji `:basketball.ball:`, hatch-vcs tag match `basketball-v*`.
- Hosts, in order: `https://site.api.espn.com`, `https://site.web.api.espn.com`. Path prefix `/apis/site/v2/sports/basketball/nba`. No API key. `User-Agent: led-ticker-basketball (+https://github.com/JamesAwesome/led-ticker-plugins)`.
- Example teams are `PHI` (76ers) and `NY` (Knicks) in every doc, demo and example. Nicknames `76ERS` / `KNICKS`.
- Coverage `fail_under = 90`; ruff check + format check; pyright on `src` clean.
- Layout invariant: measured widths, ≥ **6 px** clearance between texts/shapes sharing a vertical band, row-uniform name ladders, ellipsis at the floor. Hi-res text never pixel-pinned in tests. Logo sprites are shapes for the clearance test.
- Never raise into the poll loop or the render loop. Never infer a final from a vanished game. First sight is a silent baseline. Clocks are **not** ticked locally. No network on any render or poll path other than the two ESPN JSON endpoints.
- Palette (0–255): `WHITE (255,255,255)` score/clock; `AMBER (255,180,0)` period/date/tip-off; `CYAN (0,200,220)` leader lines; `RED (230,40,40)` clutch clock; `ORANGE (255,120,30)` emoji + longboi linescore strip; `DIM (70,70,70)` labels/dividers; `GREEN (0,220,90)` winner; `LOSER (120,120,120)`; `GRAY (110,110,110)` `@`/records.
- Mode names `teams` / `league` / `live`. Layouts `auto` / `scoreboard` / `ticker`; `auto` → `scoreboard` at every scale. `final_hold_hours` default **6**. `GAME_LENGTH` 2 h 30 min.
- Cadence: `LIVE_INTERVAL 15`, `TIPOFF_INTERVAL 60` (within `TIPOFF_WINDOW` 30 min), `PREGAME_INTERVAL 300`, `IDLE_INTERVAL 3600`, `SCHEDULE_INTERVAL 6*3600`, `MIN_INTERVAL 10`, `MAX_BACKOFF 4*3600`, `LIVE_GRACE 30*60`.
- Celebration: `FLASH_FRAMES 12`, `CELEBRATION_FRAMES 80`, `CELEBRATION_SECONDS 4.0`, `MAX_QUEUED 1`, `BOARD_FLOOR 4.0`, `DEMO_EVERY 3`. Score pulse `HIGHLIGHT_FRAMES 30`. Clutch: `period >= 4`, clock ≤ 120 s, margin ≤ 5.
- Logos: assets `src/led_ticker_basketball/assets/logos/{ABBREV}.png` 64×64 RGBA; `LOGO_BIG 36`, `LOGO_LONG 48`, `ALPHA_MIN 128`, `DARK_FLOOR 40`. Smallsign never paints a logo.
- `small_font` is **not** a config key (rejected as unknown); the smallsign board uses `font` (default `FONT_DEFAULT`).

## Review Focus

1. **An ESPN clock under a minute reads `"45.3"`, and `"0.0"` at a buzzer** — the board shows it as given, `is_clutch` parses it (45 s ≤ 120), and `END Q3` shows no clock. Owned by Task 2 (`test_is_clutch_parses_tenths`, `test_status_lines_end_period_hides_zero_clock`).
2. **A competitor with no `leaders` (pregame, or a sparse payload)** — `away_leader is None`, every renderer omits the line, nothing raises. Owned by Task 2 (`test_parse_event_without_leaders`) and Task 8 (`test_sparse_game_never_raises`).
3. **A game first seen as final (boot after the buzzer, hot reload)** — no celebration. Owned by Task 3 (`test_first_sight_final_is_silent`) and Task 6 (`test_reload_with_surviving_source_is_silent`).
4. **A West-coast game still live after midnight Eastern** drops out of today's scoreboard — yesterday's slate is fetched and the card stays live at live cadence. Owned by Task 3 (`test_yesterday_feed_keeps_late_game`).
5. **A team whose logo asset is missing or corrupt** (a future expansion team, a bad wheel) — the chip fallback paints, nothing raises, one DEBUG log. Owned by Task 4 (`test_missing_logo_falls_back_to_chip`, `test_corrupt_logo_falls_back_to_chip`).

---

### Task 1: Scaffold, teams table, logo + fixture tools, release allowlist

**Files:**
- Create: `plugins/basketball/{pyproject.toml,Makefile,LICENSE}` — copy football's; swap name, description (`"Live NBA basketball scores widget for led-ticker, fed by ESPN's public scoreboard API (no key). Bundled team logos."`), keywords (`basketball`, `nba`), `basketball-v*` tag match, wheel package path; core floor `>=4.31`. Add `[tool.hatch.build.targets.wheel] packages = ["src/led_ticker_basketball"]` (keeps `assets/`).
- Create: `plugins/basketball/src/led_ticker_basketball/__init__.py` — `register(api)` → `api.widget("scores")(BasketballScoreMonitor)`; emoji registration is added in Task 4. Until Task 6 `scores.py` holds `class BasketballScoreMonitor: pass`.
- Create: `plugins/basketball/src/led_ticker_basketball/teams.py`
- Create: `plugins/basketball/tools/fetch_logos.py`, `plugins/basketball/tools/capture_fixtures.py` (both stdlib `urllib` + Pillow; neither imported by the package).
- Create: `plugins/basketball/src/led_ticker_basketball/assets/logos/MANIFEST.txt` (+ 30 PNGs, HUMAN step).
- Create: `plugins/basketball/tests/{conftest.py,test_import_purity.py,test_smoke.py,test_teams.py}` — football's; conftest resets `led_ticker_basketball._source._SHARED_SOURCES` and `_logos.sprite.cache_clear()`.
- Modify: root `README.md` (row `| Basketball / NBA | `led-ticker-basketball` | `basketball.scores` (+ `:basketball.ball:` emoji) | ESPN public scoreboard API (no key); bundled logos |` after Football; add `basketball` to the original-plugins list), `RELEASING.md` publishable list, `scripts/check_release.py` `PUBLISHABLE_PLUGINS` (+ comment), `tests/test_check_release.py` (`test_basketball_is_publishable` mirroring football's).

**Interfaces:**
- Produces `teams.py`:
  - `@dataclass(frozen=True) class TeamInfo: abbrev: str; espn_id: str; city: str; nickname: str; primary: Color; secondary: Color` (`Color = tuple[int, int, int]`).
  - `NBA_TEAMS: dict[str, TeamInfo]` — all 30 with ESPN abbreviations: `ATL BOS BKN CHA CHI CLE DAL DEN DET GS HOU IND LAC LAL MEM MIA MIL MIN NO NY OKC ORL PHI PHX POR SA SAC TOR UTAH WSH`. ESPN ids (verify against the captured payload, fix any that differ): ATL 1, BOS 2, NO 3, CHI 4, CLE 5, DAL 6, DEN 7, DET 8, GS 9, HOU 10, IND 11, LAC 12, LAL 13, MIA 14, MIL 15, MIN 16, BKN 17, NY 18, ORL 19, PHI 20, PHX 21, POR 22, SAC 23, SA 24, OKC 25, UTAH 26, WSH 27, TOR 28, MEM 29, CHA 30. Colours from ESPN's `color`/`alternateColor` in the captured payload, lifted so `max(channel) >= 90`; near-black primaries (`BKN`, `SA`) use the lifted secondary as `primary`. Pinned: `PHI` primary `(0, 107, 182)`, secondary `(237, 23, 76)`; `NY` primary `(245, 132, 38)`, secondary `(0, 107, 182)`.
  - `def team(abbrev: str) -> TeamInfo` (unknown → neutral `(200,200,200)`, never raises), `def normalize_team(code: str) -> str | None`, `def team_by_id(espn_id: str) -> str | None`.
- Produces `tools/fetch_logos.py`: `python tools/fetch_logos.py [--out src/led_ticker_basketball/assets/logos]` — for every `NBA_TEAMS` abbrev GET `https://a.espncdn.com/i/teamlogos/nba/500/{abbrev.lower()}.png` (UA `Mozilla/5.0 led-ticker-basketball-tools`), `Image.open(...).convert("RGBA")`, `thumbnail((64, 64), LANCZOS)`, paste centred on a transparent 64×64, save `{ABBREV}.png`; write `MANIFEST.txt` lines `{ABBREV}\t{url}\t{YYYY-MM-DD}`. Exit non-zero listing any team that failed.
- Produces `tools/capture_fixtures.py`: `python tools/capture_fixtures.py [--date YYYYMMDD] --out tests/fixtures` — GET `{HOST}{PATH}/scoreboard` (`?dates=` when given) and `{PATH}/teams/PHI/schedule`; write `scoreboard_{date}.json` **trimmed** to at most one event per state (`pre`, `in`, `post`, plus a `post` with `period > 4` if any) keeping `events[].{id,date,shortName,season,status,competitions[0].{competitors,venue,broadcasts,neutralSite,status}}` whole, and `schedule_phi.json` trimmed to `events[:6]` plus top-level `team`/`season`. Both raw payloads are also saved under `tests/fixtures/raw/` (gitignored).
- Produces fixtures (committed): `scoreboard_YYYYMMDD.json`, `schedule_phi.json`, and — if no game was live at capture — `event_live.json` hand-written from the captured `post` event with `status.type.{name:"STATUS_IN_PROGRESS",state:"in"}`, `period 4`, `displayClock "2:13"`, scores `98`/`101`, `leaders` for both teams, flagged `"_handwritten": true`. Plus `logo_synthetic.png` (a 64×64 RGBA test image: a filled circle of `(0,107,182)` alpha 255 on transparent, with a 4×4 patch of `(20,20,20)` alpha 255 and a 4×4 patch of `(255,255,255)` alpha 60), generated by `tests/conftest.py` into `tmp_path` rather than committed.

- [ ] **Step 1: Write failing tests** in `test_teams.py`: `test_all_30_teams_present`, `test_sixers_and_knicks_colors` (`team("phi").primary == (0,107,182)`, `team("NY").primary == (245,132,38)`), `test_knicks_code_is_ny` (`normalize_team("NYK") is None`, `normalize_team("ny") == "NY"`), `test_unknown_team_is_neutral`, `test_colors_are_led_visible`, `test_team_by_id` (`"20"` → `"PHI"`, `"999"` → `None`).
- [ ] **Step 2: Run** `uv run pytest plugins/basketball -q`. Expected: FAIL (import error).
- [ ] **Step 3: Implement** `teams.py`, the stub `scores.py`, `__init__.py`, the two tools, the root/release edits. `uv sync --extra dev` at the repo root.
- [ ] **Step 4 (HUMAN, network):** from `plugins/basketball/`: `uv run python tools/fetch_logos.py` and `uv run python tools/capture_fixtures.py --out tests/fixtures`. Then check `team.id` values in the capture against `NBA_TEAMS` and fix any id that differs. If a game is live at capture time, drop the hand-written `event_live.json` plan and use the capture; otherwise write it as specified. Open two logo PNGs with the Read tool to confirm they are centred RGBA artwork.
- [ ] **Step 5: Run** `uv run pytest plugins/basketball tests -q && uv run ruff check plugins/basketball && uv run ruff format --check plugins/basketball`. Expected: PASS incl. `test_import_purity`, `test_smoke`, `tests/test_check_release.py`.
- [ ] **Step 6: Commit** `git add plugins/basketball README.md RELEASING.md scripts tests uv.lock && git commit -m "feat(basketball): scaffold led-ticker-basketball with the 30-team table, bundled logos and ESPN fixtures"`

---

### Task 2: Models: parsing, leaders, linescores, status lines, clutch, finals, demo

**Files:**
- Create: `plugins/basketball/src/led_ticker_basketball/_models.py`
- Test: `plugins/basketball/tests/test_models.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class Leader: name: str; points: int` — `name` is ESPN `athlete.shortName` upper-cased (`"J. EMBIID"`).
  - `@dataclass(frozen=True) class FinalEvent: key: str; game_id: str; winner: str; loser: str; away_score: int; home_score: int; final_ot: bool; leader: Leader | None` — `key == game_id`; `leader` is the winner's points leader.
  - `@dataclass(frozen=True) class GameInfo: game_id: str; state: str; status: str; away: str; home: str; away_score: int; home_score: int; period: int; clock: str; start_utc: datetime | None; time_tbd: bool; venue: str; broadcast: str; away_record: str; home_record: str; final_ot: bool; neutral_site: bool; away_leader: Leader | None = None; home_leader: Leader | None = None; away_linescores: tuple[int, ...] = (); home_linescores: tuple[int, ...] = (); polled_at: float = 0.0`
  - `def parse_event(e: dict, *, polled_at: float) -> GameInfo | None` — football's rules (string or object scores, `pre/in/post`, `STATUS_POSTPONED` → future + `time_tbd`, `STATUS_CANCELED` → final, `final_ot = final and (period > 4 or "OT" in detail)`, `time_tbd` on `TBD`); plus `leaders`: the entry whose `name == "pointsLeader"`, its `leaders[0].athlete.shortName` and `int(displayValue)`; `linescores`: `tuple(int(ls.value) for ls in linescores)`.
  - `def period_label(period: int, status: str) -> str` — `HALF`, `END Q{n}`, `DELAY`, `SUSP`, else `Q1`–`Q4`, `OT`, `2OT`….
  - `def status_lines(game, now: float, tz) -> tuple[str, str]` — as football, with an EMPTY clock for `HALF`/`END Qn`/`DELAY` even when `displayClock` is `"0.0"`.
  - `def clock_seconds(clock: str) -> float | None` — `"2:13"` → 133.0, `"45.3"` → 45.3, `"0.0"` → 0.0, `""`/junk → `None`.
  - `def is_clutch(game: GameInfo) -> bool` — live, `STATUS_IN_PROGRESS`, `period >= 4`, `clock_seconds <= 120`, `abs(away - home) <= 5`.
  - `def leader_text(leader: Leader | None, *, style: str) -> str` — `style="full"` → `"J. EMBIID 31 PTS"`, `"short"` → `"EMBIID 31"` (initial stripped), `None` → `""`.
  - `def final_event(game: GameInfo) -> FinalEvent | None` — `None` unless `state == "final"` with a decided winner (`winner(game)`), else the event with the winner's leader.
  - `day_label`, `winner`, `final_in_hold`, `GAME_LENGTH = timedelta(hours=2, minutes=30)` — as football.
  - `def build_demo_games(now: float) -> tuple[list[GameInfo], FinalEvent]` — the spec's four cards (ids `demo-live`, `demo-half`, `demo-final-ot`, `demo-next`) and the demo final `FinalEvent(key="demo-live", winner="PHI", loser="NY", 112, 108, False, Leader("J. EMBIID", 31))`. Live card: PHI 98 at NY 101, Q4 `2:13`, leaders `J. EMBIID 31` / `J. BRUNSON 28`, linescores `(24,26,25,23)` / `(28,24,27,22)`, venue `Madison Square Garden`. Next: tomorrow 19:30 local, records `5-2`/`4-3`, broadcast `ESPN`.

- [ ] **Step 1: Write failing tests**: `test_parse_scheduled_event`, `test_parse_final_event` (winner, records, `final_ot`), `test_parse_live_event_leaders_and_linescores` (`away_leader.name` upper-cased, `points == 31`, `len(away_linescores) == 4`), `test_parse_event_without_leaders` (leaders key absent → both `None`), `test_parse_event_sparse_never_raises`, `test_period_labels`, `test_status_lines_end_period_hides_zero_clock` (`STATUS_END_PERIOD`, `displayClock "0.0"` → `("END Q3", "")`), `test_clock_seconds` (parametrized), `test_is_clutch_parses_tenths` (Q4 `"45.3"` margin 3 → True; `"2:01"` → False; Q3 → False; margin 6 → False), `test_leader_text_styles`, `test_final_event_requires_winner` (tie/no winner → None), `test_demo_games_cover_states` (four games, states `{live, live, final, future}`, the demo final's `winner == "PHI"`, live card `is_clutch`).
- [ ] **Step 2: Run** `uv run pytest plugins/basketball/tests/test_models.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** `_models.py` (every dict read via football's `_dict`/`_list`/`_str`/`_int`).
- [ ] **Step 4: Run** the same. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "feat(basketball): parse ESPN NBA events into GameInfo with leaders, linescores, clutch and finals"`

---

### Task 3: Source: shared fetcher on the day model, final baseline, schedule

**Files:**
- Create: `plugins/basketball/src/led_ticker_basketball/_source.py`
- Test: `plugins/basketball/tests/test_source.py` (football's `FakeSession`/`Clock`; routes keyed by URL suffix incl. `?dates=`)

**Interfaces:**
- Consumes Task 2.
- Produces (football's `ESPNSource` with the week model replaced by hockey's day model):
  - Constants from Global Constraints; `HOSTS`, `PATH = "/apis/site/v2/sports/basketball/nba"`.
  - `Snapshot(games, next_games, stale, error)` — no `bye_teams`/`week`.
  - `ESPNSource.want(*, teams, all_games, tz, final_hold_hours, live_interval)`, `note_displayed` (no-op), `poll()`, `next_delay()`, `_get` with host fallback — as football.
  - `_poll`: GET `{PATH}/scoreboard`; parse into `fetched`; **yesterday**: when any cached live game id is missing from `fetched`, also GET `{PATH}/scoreboard?dates={yesterday:%Y%m%d}` (soft: a failure logs DEBUG and is not a `_fail`) and merge, tracking `_yesterday_ids` as hockey; `_latest_ids`, `_games`, `_last_seen`, hold pruning, `LIVE_GRACE` in `_active()` as football; then `_track_final(game)`.
  - `_track_final(game)`: `_seen_state[gid]` records the state at first sight; on a transition from a non-final seen state to `final` with a winner, `_finals[gid] = final_event(game)`. A game first seen `final` never gets an entry. `def final_after_baseline(game_id) -> FinalEvent | None` (non-consuming).
  - `_cadence()`: live → `max(MIN_INTERVAL, live_interval)`; a future relevant game within ±`TIPOFF_WINDOW` → `TIPOFF_INTERVAL`; a future relevant game today (local date) → `PREGAME_INTERVAL`; else `IDLE_INTERVAL`.
  - `_refresh_next`: football's (`SCHEDULE_INTERVAL`, `SCHEDULE_TIMEOUT`, retry rules, held finals still fetch) against `{PATH}/teams/{TEAM}/schedule`; no bye handling.
  - `shared_source(session)`, `_SHARED_SOURCES` as football.

- [ ] **Step 1: Write failing tests**: `test_poll_parses_today` (the captured fixture → N games, not stale), `test_host_fallback_on_403`, `test_both_hosts_fail_is_stale`, `test_malformed_payload_keeps_last_games`, `test_cadence_ladder` (live 15; tip-off in 20 min 60; later today 300; nothing 3600; `live_interval=10` → 10), `test_first_sight_final_is_silent` (fixture final on first poll → `final_after_baseline is None`), `test_live_to_final_emits_final_event` (live fixture then the same id as final 112–108 → event with `winner == "PHI"`, `leader.points == 31`), `test_final_event_is_non_consuming`, `test_yesterday_feed_keeps_late_game` (poll 1 has live game G; poll 2's today payload lacks G and `?dates=yesterday` returns G still live → `games[G].state == "live"`, cadence 15, exactly one `?dates=` request), `test_vanished_game_keeps_state_until_hold`, `test_next_game_from_schedule` (tracked PHI with nothing today → `next_games["PHI"]` is the first `pre` schedule event; not refetched within 6 h), `test_today_pre_game_beats_schedule`, `test_shared_source_is_per_session`, `test_poll_never_raises`, `test_first_poll_failure_backs_off_from_live_interval`.
- [ ] **Step 2: Run** `uv run pytest plugins/basketball/tests/test_source.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** `_source.py`.
- [ ] **Step 4: Run** the same. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "feat(basketball): shared ESPN source on the day model with a final-buzzer baseline"`

---

### Task 4: Logos and the ball emoji

**Files:**
- Create: `plugins/basketball/src/led_ticker_basketball/{_logos.py,emoji.py}`
- Modify: `__init__.py` — `api.emoji("ball", BALL)`, `api.hires_emoji("ball", BALL_HIRES)`.
- Test: `plugins/basketball/tests/{test_logos.py,test_emoji.py}`; extend `test_smoke.py`.

**Interfaces:**
- Produces `_logos.py`:
  - `LOGO_BIG = 36`, `LOGO_LONG = 48`, `ALPHA_MIN = 128`, `DARK_FLOOR = 40`.
  - `@dataclass(frozen=True) class LogoSprite: size: int; pixels: tuple[tuple[int, int, int, int, int], ...]` (`(x, y, r, g, b)`, `0 <= x, y < size`).
  - `@functools.cache def sprite(abbrev: str, size: int) -> LogoSprite | None` — opens `importlib.resources.files("led_ticker_basketball") / "assets" / "logos" / f"{abbrev.upper()}.png"`; `None` (one `logger.debug`) when the file is missing, Pillow raises, or `abbrev` is not in `NBA_TEAMS`. Decode: `convert("RGBA")` → `resize((size, size), LANCZOS)` → keep pixels with `a >= ALPHA_MIN` and `max(r, g, b) >= DARK_FLOOR`, composited over black (`c * a // 255`).
  - `def _decode(data: bytes, size: int) -> LogoSprite` — the pure decode, used by `sprite` and by tests with the synthetic PNG.
  - `def paint_logo(real, sprite: LogoSprite, x: int, y: int) -> None` — `SetPixel` each pixel at `(x + px, y + py)` through `_paint.px` (clipped; works on `ShiftedReal`).
- Produces `emoji.py`: `BALL: PixelData` (8×8: fill `(255,120,30)`, seams `(110,50,20)` — one vertical and one horizontal centre seam plus two curved side seams; no black), `BALL_HIRES: HiResEmoji` from `_generate_basketball_hires() -> HiResEmoji` (32×32 disc, same colours, seams 2 px wide; baseball's `_generate_baseball_hires` is the template).

- [ ] **Step 1: Write failing tests**: `test_logos.py`: `test_all_team_logos_decode` (every `NBA_TEAMS` abbrev at 36 and 48 → sprite with `len(pixels) > 0`, all coords inside `size`), `test_logo_pixels_respect_floor_and_alpha` (synthetic PNG via `_decode`: no pixel from the `(20,20,20)` patch, none from the alpha-60 patch, the disc present), `test_missing_logo_falls_back_to_chip` (`sprite("ZZZ", 36) is None`, no raise), `test_corrupt_logo_falls_back_to_chip` (monkeypatch the resource to 10 junk bytes → `None`), `test_sprite_is_cached` (same object twice), `test_paint_logo_clips_on_shifted_real` (paint at x = −20 on a 256×64 real → no raise, some pixels lit). `test_emoji.py`: `test_ball_lowres_has_no_black_and_fits_8x8`, `test_ball_hires_is_32_square_disc`. `test_smoke.py`: `:basketball.ball:` resolves via `led_ticker.plugin.emoji_slugs()` after plugin load.
- [ ] **Step 2: Run** `uv run pytest plugins/basketball/tests/test_logos.py plugins/basketball/tests/test_emoji.py plugins/basketball/tests/test_smoke.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** both modules and the registration.
- [ ] **Step 4: Run** the same. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "feat(basketball): bundled logo sprites and the :basketball.ball: emoji"`

---

### Task 5: Palette, paint helpers, smallsign band board, ticker wording, layout resolver

**Files:**
- Create: `plugins/basketball/src/led_ticker_basketball/{_palette.py,_paint.py,_scoreboard.py}`, `layouts/__init__.py`, `layouts/crawl.py`
- Test: `plugins/basketball/tests/{test_scoreboard.py,test_layout_crawl.py,test_resolve_layout.py}`

**Interfaces:**
- Consumes Task 2 and `teams.team`.
- Produces:
  - `_palette.py`: the Global Constraints colours (incl. `ORANGE`); `chip`, `dim`, `lerp` as football.
  - `_paint.py`: football's (`js_round`, `cap_top`, `ShiftedReal`, `phys_wrap`, `hires`, `text_width`, `fit_size`, `fit_text`, `px`, `rect`); drop `triangle`/`pips`.
  - `_scoreboard.py`: `BasketballBandBoard(FrameAwareBase)` — **one 16-row band**, baseline from `compute_baseline_for_band(font, canvas.height, scale, valign="center")`. Live/final columns, left to right, each a MINIMUM pushed right by `_GAP = 6` past the previous: away chip (3 px, `x0..x2`, full height), away abbrev (team primary) `X_ABBREV = 5`, away score (`_score_color`), centre text (`Q4 2:13`: period AMBER, clock WHITE or RED when `is_clutch`; `HALF`/`END Q3`; final `FINAL` WHITE + `/OT` AMBER) **centred** on the canvas, home score, home abbrev, home chip at the right edge. Shrink order when the run overflows: centre drops to the clock alone (`2:13`), then `FINAL/OT` → `F/OT`, then the centre ellipsizes. `STALE` DIM replaces the centre when stale and nothing else fits, else sits after it. Future: `PHI @ NY` (`VS` neutral) in team colours left, day label AMBER + tip-off WHITE right-aligned (football's future band, one row, venue dropped). `highlight: dict[str, float]` (team → fade 0..1 from team primary toward the rest colour). `shape_extents` records both chips.
  - `build_ticker_message(game, now, tz, *, font, bg_color, font_color, stale) -> SegmentMessage` — as football minus `bye`.
  - `layouts/__init__.py`: `VALID_LAYOUTS`, `resolve_layout` (football's).
  - `layouts/crawl.py`: `segments(game, now, tz, *, stale=False) -> list[tuple[str, Color]]` — live: `PHI 98 · NY 101 · Q4 2:13 · J. EMBIID 31 · J. BRUNSON 28` (period AMBER, clock WHITE/RED on clutch, leaders CYAN, each only when present); final: `… · FINAL/OT`; future: `PHI 5-2 @ NY 4-3 · SAT NOV 1 7:30 PM · ESPN · MADISON SQUARE GARDEN`; `STALE` as football. `render_crawl` as football.

- [ ] **Step 1: Write failing tests**: `test_scoreboard.py`: `test_band_board_live_columns` (one band; away chip at x0–2 and home chip at x157–159; abbrevs in team colours; centre text contains `Q4`), `test_band_board_clutch_clock_is_red` (clock drawn in `pal.RED`; a non-clutch game draws it `pal.WHITE`), `test_band_board_final_colors_and_ot`, `test_band_board_future_row`, `test_band_board_worst_case_clearance` (`UTAH 148` vs `WSH 148`, `2OT 0:00.0`; every text ≥ 6 px from its neighbour and inside 160 px; the centre has shrunk to the clock), `test_band_board_honours_cursor_pos`, `test_band_board_highlight_fades_toward_rest_color`. `test_layout_crawl.py`: `test_segments_live_wording` (joined text equals the spec line), `test_segments_omit_missing_leaders`, `test_segments_final_ot`, `test_segments_future_with_records`, `test_render_crawl_held_when_fits`. `test_resolve_layout.py`: football's.
- [ ] **Step 2: Run** the three test files. Expected: FAIL.
- [ ] **Step 3: Implement** the five modules.
- [ ] **Step 4: Run** the same. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "feat(basketball): palette, smallsign single-band board and ticker wording"`

---

### Task 6: Widget: config, modes, selection, persistent cards, score pulse

**Files:**
- Create: `plugins/basketball/src/led_ticker_basketball/scores.py`, `_card.py` (board-only; Task 7 adds the celebration)
- Test: `plugins/basketball/tests/{test_scores.py,test_card_dispatch.py}`

**Interfaces:**
- Consumes Tasks 2–5.
- Produces:
  - `select_stories(games, next_games, *, mode, teams, max_games, now_wall, final_hold_hours, tz) -> list[GameInfo]` — football's with "later this week" → "later today" (any `future` game in `games`).
  - `@attrs.define class BasketballScoreMonitor` — football's fields minus `small_font`, plus `logos: bool = attrs.field(default=True, kw_only=True)`; `final_hold_hours` default 6; `validate_config` messages prefixed `basketball.scores`, `NYK` → `Did you mean 'NY'?`, `logos` must be a bool, and **`small_font` present → message `basketball.scores does not accept small_font: the smallsign board uses font`**; `_LIST_FIELD_HINTS` for `mode`, `teams`, `layout`, `logos`, `timezone`, `padding`, `update_interval`; `start`/`update`/`_rebuild` as football (`splay=False`); `_queue_finals(source, snap, cards)`: per game, `ev = source.final_after_baseline(gid)`; first sight of a gid seeds `_celebrated` with `{ev.key}` if `ev` exists (silent); later, an `ev` whose key is not in `_celebrated[gid]` is added and, when `ev.winner in self.teams`, `card.queue_final(ev)`. **Score pulse:** in `_rebuild`, before `card.game = game`, compare `card.game.{away,home}_score` with the new game's and call `card.pulse(team)` for each team whose score changed.
  - `@attrs.define class BasketballGameCard(FrameAwareBase)` — football's card with: `ScoringPlay` → `FinalEvent`; `logos: bool = True`; no `bye`, no `_swap`/`replace_plays`/`drop_overturned`; `pending: list[FinalEvent]` capped at `MAX_QUEUED = 1`; `demo_final: FinalEvent | None`; `highlights: dict[str, int]` (team → frames left) with `def pulse(self, team: str) -> None` setting `HIGHLIGHT_FRAMES` and `_board_highlight() -> dict[str, float] | None` ticking every entry once per live frame (football's single-entry logic generalised); `draw` dispatches scale ≤ 1 → `BasketballBandBoard` / ticker, scale > 1 → `render_crawl` / `render_scoreboard(canvas, game, now, tz, *, y_offset, stale, highlight, logos, x_offset)` (Task 8; a stub that clears is acceptable until then).

- [ ] **Step 1: Write failing tests**: `test_scores.py`: `test_validate_unknown_team_suggests` (`["NYK"]` → `Did you mean 'NY'?`), `test_validate_rejects_small_font`, `test_validate_logos_bool`, `test_teams_mode_selection_order` (live > final in hold > later today > next game; head-to-head → one card), `test_final_hold_default_6h`, `test_league_mode_order_and_cap`, `test_live_mode_empty_when_nothing_live`, `test_demo_builds_four_cards_and_queues_final`, `test_cards_persist_across_polls`, `test_stale_marks_cards`, `test_score_change_pulses_that_team` (second `_rebuild` with PHI 98→100 → `card.highlights == {"PHI": 30}`; both change → both keys), `test_tracked_win_queues_final` (FakeSource returns a `FinalEvent` for a known gid → `card.pending == [ev]`), `test_untracked_win_does_not_queue`, `test_reload_with_surviving_source_is_silent` (a fresh widget on a source that already has the event → nothing pending). `test_card_dispatch.py`: football's (`test_scale1_uses_band_board`, `test_scale4_calls_render_scoreboard`, `test_ticker_layout_adds_padding`, `test_scale1_ticker_delegates_to_segment_message`, `test_has_play_shape_is_sync_draw`, `test_scale4_scoreboard_scrolls_with_cursor_pos`).
- [ ] **Step 2: Run** both files. Expected: FAIL.
- [ ] **Step 3: Implement** `scores.py` and `_card.py`.
- [ ] **Step 4: Run** `uv run pytest plugins/basketball -q`. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "feat(basketball): basketball.scores widget — modes, selection, persistent cards, score pulse"`

---

### Task 7: Final-buzzer win celebration

**Files:**
- Create: `plugins/basketball/src/led_ticker_basketball/_celebration.py`
- Modify: `_card.py` (football's celebration plumbing: `pending`, `_playing`, `_shown`, `_run_start`/`_run_pos`/`_x_shift`, `hold_time`, `reset_frame`, demo re-arm via `demo_final`)
- Test: `plugins/basketball/tests/test_celebration.py`

**Interfaces:**
- Consumes `FinalEvent`, `GameInfo`, `_paint`, `_palette`, `_logos`.
- Produces: `FLASH_FRAMES`, `CELEBRATION_FRAMES`, `CELEBRATION_SECONDS`, `MAX_QUEUED = 1`, `HIGHLIGHT_FRAMES = 30`, `phase_at`, `pulse` as football; `def win_word(ev: FinalEvent, max_w: int, size: int) -> str` (`f"{team(ev.winner).nickname.upper()} WIN"`, falling back to `f"{ev.winner} WIN"` when the measured width exceeds `max_w`; at scale 1 the bitmap measure); `def render_flash(canvas, color, on, word, *, y_offset=0)` as football; `def render_detail(canvas, game, ev, frame, *, y_offset=0, font=None, logos=True)` — bigsign/longboi: winner logo (36/48, when `logos` and a sprite exists, else the chip) at the left, `PHI 112 NY 108` run with the winner's score pulsing in team colour, `FINAL` / `FINAL/OT` AMBER, `leader_text(ev.leader, style="full")` CYAN on the bottom row; smallsign: `PHI 112 NY 108 · FINAL` one row with the winner pulsing.
- Card: `queue_final(ev)` (tracked only; replaces any pending entry), `demo_final`, consumption/self-start/freeze logic copied verbatim from football's `_card.py` with the play names swapped.

- [ ] **Step 1: Write failing tests**: football's suite renamed, minus follow-up/overturn tests: `test_phase_timeline`, `test_win_word_falls_back_to_abbrev`, `test_flash_knocks_out_word` (bigsign + smallsign), `test_detail_draws_scores_final_and_leader` (all three signs), `test_detail_pulses_winner_score`, `test_detail_uses_logo_when_available_and_chip_when_not` (bigsign; monkeypatch `sprite` → None), `test_detail_texts_keep_clearance_worst_case` (`UTAH 148 WSH 147`, `FINAL/OT`, `G. ANTETOKOUNMPO 50 PTS`), `test_hold_time_extends_while_celebration_pending` (base 3.0 + 1 → 7.0), `test_celebration_consumed_after_one_visit`, `test_reset_without_drawing_keeps_pending`, `test_queue_caps_at_one`, `test_paused_frames_do_not_advance_celebration`, `test_demo_rearms_every_third_visit`, `test_scroll_mode_starts_pending_celebration_on_first_live_draw`, `test_scroll_mode_run_freezes_cursor_until_next_pass`, `test_takeover_clears_preceding_widget`, `test_core_fill_of_bg_color_survives_every_scale`.
- [ ] **Step 2: Run** `uv run pytest plugins/basketball/tests/test_celebration.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** `_celebration.py` and the card plumbing.
- [ ] **Step 4: Run** `uv run pytest plugins/basketball -q`. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "feat(basketball): final-buzzer win celebration on the card's next turn"`

---

### Task 8: Physical scoreboard: horizontal arena board with logos (bigsign, longboi)

**Files:**
- Create: `plugins/basketball/src/led_ticker_basketball/layouts/scoreboard.py`
- Test: `plugins/basketball/tests/test_layout_scoreboard.py`

**Interfaces:**
- Consumes Tasks 2, 4, 5.
- Produces `def render_scoreboard(canvas, game, now, tz, *, y_offset=0, stale=False, highlight: dict[str, float] | None = None, logos=True, x_offset=0) -> None`; `_Geom` by `real.width` (`_LONG ≥ 400`, else `_BIG`). Starting constants (the clearance test, not these numbers, is the contract; tune within ±8 px):
  - **`_BIG` (256×64):** away logo `LOGO_BIG` at `x 4`, `y 14` (vertically centred); away score right edge `x 104`, size 30, baseline 46, `_score_color` (highlight: team primary → rest, as the band board); centre column centred on `x 128`: period AMBER size 14 baseline 22, clock WHITE/RED size 20 baseline 46 (`HALF`/`END Q3`/`FINAL` take the clock slot at size 18; `OT` under `FINAL` AMBER size 12 baseline 60); home score left edge `x 152`; home logo at `x 216`. Leader lines CYAN size 9 baseline 61: away left-aligned at `x 4`, home right-aligned at `x 251`, `leader_text(style="short")`, each fitted to half the width minus the centre column's measured extent minus `_MIN_GAP`; dropped before ellipsizing below 7 px. **Chip fallback** (no logo or `logos=False`): a 6-px chip at the logo's x plus the abbreviation in team colour, size ladder (22…14), in the logo's slot. `STALE` DIM size 9 at top-right `x 251` baseline 8.
  - **`_LONG` (512×64):** logos `LOGO_LONG` at `x 8` / `x 456`, `y 8`; scores size 46 right edge `x 190` / left edge `x 322`, baseline 50; under each score one line size 10 baseline 62: abbrev (team colour) + record (GRAY) + ` · ` + `leader_text(style="full")` (CYAN), fitted to the side's budget with the leader ellipsized first, then the record dropped; centre `x 256`: period AMBER size 15 baseline 16, clock size 26 baseline 42, **linescore strip** ORANGE size ladder (10, 9, 8) baseline 60: `24-28 · 26-24 · 25-27 · 23-22` (away-home per period, OT periods appended), dropped when it does not fit the centre budget at the floor; omitted for future games.
  - **Next game** (both): logos (or chips) on each side, `PHI @ NY` / `VS` with records GRAY, day AMBER, tip-off WHITE (`TBD` DIM), venue DIM, label `NEXT GAME` / `PPD` GRAY top-right; longboi adds nicknames (football's `_long_next` shape).
  - Logo sprites are recorded as shapes `("LOGO", x0, x1, y0, y1)` for the clearance spy; `highlight`/`stale` as football.

- [ ] **Step 1: Write failing tests** (spy `_paint.hires`, `rect`, `_logos.paint_logo` as football's spies): `test_worst_case_keeps_min_clearance` parametrized over bigsign/longboi × {live `UTAH 148 @ WSH 148` Q4 `0:00.0` clutch, leaders `G. ANTETOKOUNMPO 50` / `S. GILGEOUS-ALEXANDER 49`, six linescores, `STALE`; `END Q3`; final `2OT` 148–147 `STALE`; next game `UTAH 10-7 @ WSH 10-7` `TBD` long venue} → ≥ 6 px between recorded texts/shapes sharing rows, all inside the panel; `test_logos_painted_on_both_sides` (two `paint_logo` calls at the geometry's x); `test_logos_false_paints_chips_and_abbrevs`; `test_missing_sprite_falls_back_to_chip`; `test_clutch_clock_is_red`; `test_final_scores_colored_and_ot_shown`; `test_leader_lines_present_and_cyan` (bigsign short style, longboi full style); `test_longboi_linescore_strip_orange_and_dropped_when_narrow`; `test_next_game_shows_records_day_and_label`; `test_stale_label`; `test_sparse_game_never_raises` (no leaders, no linescores, no clock, unknown teams); `test_y_offset_shifts_content`; `test_highlight_fades_score_toward_rest`.
- [ ] **Step 2: Run** `uv run pytest plugins/basketball/tests/test_layout_scoreboard.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** `layouts/scoreboard.py`.
- [ ] **Step 4: Run** `uv run pytest plugins/basketball -q`. Expected: PASS.
- [ ] **Step 5: Visual check.** Render the four demo cards on bigsign and longboi to PNGs in the scratchpad (a short script over `HeadlessBackend` + `render_scoreboard`, upscale ×4 for viewing) and Read them: both logos legible, scores not touching the centre, leader lines inside the panel, the red clutch clock. Adjust constants; re-run Step 4.
- [ ] **Step 6: Commit** `git commit -m "feat(basketball): horizontal arena scoreboard with team logos for bigsign and longboi"`

---

### Task 9: README, CLAUDE.md, examples, full-suite gate

**Files:**
- Create: `plugins/basketball/README.md`, `plugins/basketball/CLAUDE.md`
- Create: `plugins/basketball/examples/config.basketball-{demo,live}.{smallsign,bigsign,longboi}.toml` — football's six with `type = "basketball.scores"`, `teams = ["PHI", "NY"]`, header "Check the logos, the score, the clock and the leader lines."
- Test: `plugins/basketball/tests/test_examples.py` (football's with the new names; `_NOT_USER_FACING = {"session", "feed_stories"}`).

- [ ] **Step 1: Write failing tests** (`test_all_six_examples_exist`, `test_examples_validate`, `test_examples_use_example_teams`, `test_readme_lists_every_option` incl. `logos` and `update_interval`).
- [ ] **Step 2: Run** `uv run pytest plugins/basketball/tests/test_examples.py -q`. Expected: FAIL.
- [ ] **Step 3: Write the README** in football's section order: lead (what the board shows, the win celebration, logos bundled), disclosure (ESPN unofficial; not affiliated with ESPN or the NBA; logos are the teams' marks, bundled for display on your own sign), prerequisites, install, "Reading the board" (quarters, OT, the clock, clutch, leaders, linescores), options table, modes (day-based), layouts per sign (horizontal board with logos; one-band smallsign; ticker line), the win celebration (once per game, wins only, first-sight baseline, hold extension, scroll-mode notes from football), polling cadence (15/60/300/3600, schedule 6 h, yesterday's slate, no local tick), sign checks, known limitations (unofficial feed; sign runs ahead of TV; NBA only; logos at 36 px lose fine detail), data, development.
- [ ] **Step 4: Write `CLAUDE.md`** in football's shape; invariants: import purity; source never raises + host fallback; one shared source + `splay=False`; **day model with yesterday's slate** (never infer a final from a vanished game); **`FinalEvent` baseline lives in the source, celebrated keys on the widget**; cards persistent; `reset_frame` consumption / self-start / freeze (football's paragraphs, renamed); `hold_time` property; `segments()` single wording source; `draw()` returns absolute ends; **logos are bundled assets decoded once per `(team, size)` via `_logos.sprite`, never fetched; tuning lives in `_logos.py`, refresh via `tools/fetch_logos.py` + `MANIFEST.txt`**; `small_font` rejected; the layout tripwire with logos as shapes; hi-res never pixel-pinned; palette one hue per field (`RED` reserved for the clutch clock, `ORANGE` for the ball and the linescore strip).
- [ ] **Step 5: Run** `uv run pytest plugins/basketball --cov=plugins/basketball/src --cov-report=term-missing && uv run ruff check plugins/basketball && uv run ruff format --check plugins/basketball && uv run pyright plugins/basketball/src`. Expected: PASS, coverage ≥ 90.
- [ ] **Step 6: Commit** `git commit -m "docs(basketball): README, CLAUDE.md and per-sign example configs"`, push the branch, open a draft PR (`open-pr` skill) and watch CI.

---

### Task 10: Core repo: catalog, docs page, demo GIFs, drift test

**Files (led-ticker repo, branch `docs/basketball-scores`):**
- Modify: `src/led_ticker/plugins_catalog.json` — entry after football: `name/namespace "basketball"`, summary (`"Live NBA scores from ESPN's public site API (no key) — a horizontal arena board with bundled team logos on the big panels, score, quarter and clock, points leaders, a final-buzzer win celebration, final and next-game cards; :basketball.ball: emoji; modes teams, league and live."`), `provides.widgets ["basketball.scores"]`, `provides.emoji [":basketball.ball:"]` (if the schema has the key; check football's/flair's entries), sources PyPI `led-ticker-basketball` + git ref `basketball-v0.1.0` subdirectory `plugins/basketball`.
- Modify: `tests/test_plugins/test_catalog.py` — add `"basketball"` to the expected names.
- Create: `docs/site/demos-pinned/basketball-scoreboard-{smallsign,bigsign,longboi}.toml` — football's three with `type = "basketball.scores"`, `teams = ["PHI", "NY"]`, `demo = true`, headers describing the horizontal board; `# render-duration:` from `make plan-gif` (four cards × 6 s hold + celebration ≈ 36; use the planner's number).
- Create: `docs/site/public/demos-pinned/basketball-scoreboard-{smallsign,bigsign,longboi}.gif` — rendered via `uv run --project ../led-ticker-plugins python tools/render_demo/render.py <toml> -o <gif> --duration <N>` (bigsign TOML uses `rows = 64, cols = 64, chain_length = 4` as football's pinned one).
- Create: `docs/site/src/content/docs/widgets/basketball.mdx` per `docs/DOCS-STYLE.md`, football's page as the model: frontmatter (`title: Live NBA basketball scores`), lead paragraph, `DemoGif` longboi + caption, core floor `>= 4.31`, unofficial-feed `Aside`, "What you'll need", "The smallest config that works" (the pinned longboi block verbatim), "Reading the board (if you don't follow basketball)", `OptionsTable source="widgets/basketball"`, modes, layouts (with the bigsign + smallsign GIFs), the win celebration, polling, limitations, `RelatedPages`.
- Create: `docs/content-source/widgets/basketball.md` — the options table (every `BasketballScoreMonitor` field + `update_interval`, `logos`; note `small_font` is not accepted).
- Modify: `docs/site/src/content/docs/plugins/available.mdx` (section + `<PluginCatalog name="basketball" />` after football), `docs/site/src/content/docs/widgets/index.mdx` (catalog row + the live-data list), `docs/site/astro.config.mjs` (sidebar entry after football), `docs/site/scripts/check-llms.mjs` (`SMALL_BUDGET_BYTES` re-measured + ~9% if the build trips it; update the comment).
- Create: `tests/test_docs_basketball_demo_drift.py` — football's drift test with `basketball` / `basketball-scoreboard-longboi`.

- [ ] **Step 1: Write failing tests** — the drift test and the catalog name; run `uv run pytest tests/test_docs_basketball_demo_drift.py tests/test_plugins/test_catalog.py -q`. Expected: FAIL.
- [ ] **Step 2: Render the three GIFs** (making-a-gif skill, docs mode; pnpm/node via nvm per project memory). Read a mid frame of each: logos on the big panels, one band on smallsign, the `76ERS WIN` flash present.
- [ ] **Step 3: Write** the page, the content-source table, the catalog entry and the wiring edits.
- [ ] **Step 4: Run** `uv run pytest tests/test_docs_basketball_demo_drift.py tests/test_docs_config_options_drift.py tests/test_plugins -q && make docs-build && make docs-check-llms`. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "docs(basketball): widget page for basketball.scores, catalog entry, demo GIFs on all three sign shapes"`, push, open a draft PR, watch CI. Note in the PR body that it depends on `basketball-v0.1.0` being on PyPI (Task 11).

---

### Task 11: Release `basketball-v0.1.0`

**HUMAN steps (James):** register the pending Trusted Publisher for `led-ticker-basketball` on PyPI (core runbook §A.2) before the first Release; merge the plugins PR; approve the `release` environment gate.

- [ ] **Step 1 (after the plugins PR is merged):** `uv run python scripts/cut_release.py basketball minor --notes <notes file>` from the monorepo root on `main`'s tip (per `RELEASING.md`; never a precomputed version).
- [ ] **Step 2 (HUMAN):** approve the `release` deployment in Actions.
- [ ] **Step 3: Verify** `https://pypi.org/project/led-ticker-basketball/` shows `0.1.0`; `pip download led-ticker-basketball==0.1.0 --no-deps -d /tmp/x && unzip -l /tmp/x/*.whl | grep assets/logos | wc -l` → 31 (30 PNGs + MANIFEST).
- [ ] **Step 4:** mark the core-repo PR (Task 10) ready for review.
