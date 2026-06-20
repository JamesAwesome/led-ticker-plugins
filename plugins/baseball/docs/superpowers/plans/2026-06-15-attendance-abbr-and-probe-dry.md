# Attendance team-code fix + shared next-game probe — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Athletics/D-backs work in `baseball.attendance` team mode (normalize schedule abbreviations to canonical OAK/ARI), and DRY the duplicated 30-day next-game probe into a shared `teams.next_game_date()` used by both statcast and attendance.

**Architecture:** Two follow-ups from the PR #14 review. (1) `attendance._parse_schedule_games` normalizes team abbreviations through the existing `teams.API_TO_CANONICAL_ABBR` map (the schedule-side mirror of what statcast's `_row_team` already does). (2) Extract the identical probe both widgets run into `teams.next_game_date()`; each widget keeps its own label/log; attendance's label gate moves from `self.team` to `self._team_id` (the twin of PR #14 finding #2). Spec: `docs/superpowers/specs/2026-06-15-attendance-abbr-and-probe-dry-design.md`.

**Tech Stack:** Python 3.14, attrs, aiohttp, pytest (`asyncio_mode = "auto"`), uv, ruff (E/F/I/UP/B/SIM + format), pyright, coverage ≥90. Core imports ONLY from `led_ticker.plugin`; shared helpers from `led_ticker_baseball.teams`. NO `from __future__ import annotations`.

**Branch:** work on `attendance-abbr-and-probe-dry` only; never checkout/switch branches; never commit to main.

**Gates — run all four before EVERY commit** (run `uv run ruff format src tests` first if the check fails):

```bash
uv run pytest -q
uv run ruff check src tests
uv run ruff format --check src tests
uv run pyright src
```

**Already in place (from merged PR #14):** `teams.py` has `API_TO_CANONICAL_ABBR = {"ATH": "OAK", "AZ": "ARI"}` and `_CANONICAL_TO_API_ABBR`, and `resolve_team_id` matches a canonical code against its API spelling. `teams.py` currently imports `logging`, `aiohttp`, and `from led_ticker.plugin import (Color, colors, make_color)`.

---

### Task 1: `teams.next_game_date()` shared probe

**Files:**
- Modify: `src/led_ticker_baseball/teams.py`
- Create: `tests/test_teams.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_teams.py`:

```python
"""Tests for shared helpers in led_ticker_baseball.teams."""

import datetime as dt
import unittest.mock as mock


def _ctx(payload):
    resp = mock.AsyncMock()
    resp.json.return_value = payload
    ctx = mock.AsyncMock()
    ctx.__aenter__.return_value = resp
    return ctx


def make_session(routes):
    session = mock.MagicMock()

    def side_effect(url, *args, **kwargs):
        for key, payload in routes.items():
            if key in url:
                return _ctx(payload)
        return _ctx({})

    session.get.side_effect = side_effect
    return session


TODAY = dt.date(2026, 6, 15)


class TestNextGameDate:
    async def test_returns_first_valid_date(self):
        from led_ticker_baseball.teams import next_game_date

        session = make_session(
            {"/schedule": {"dates": [{"date": "2026-06-20"}, {"date": "2026-06-21"}]}}
        )
        assert await next_game_date(session, TODAY) == dt.date(2026, 6, 20)

    async def test_team_scoped_url_has_teamid(self):
        captured = {}

        def side_effect(url, *args, **kwargs):
            captured["url"] = url
            return _ctx({"dates": [{"date": "2026-06-20"}]})

        session = mock.MagicMock()
        session.get.side_effect = side_effect
        from led_ticker_baseball.teams import next_game_date

        await next_game_date(session, TODAY, team_id=143)
        assert "teamId=143" in captured["url"]
        assert "gameType=R" in captured["url"]

    async def test_league_url_has_no_teamid(self):
        captured = {}

        def side_effect(url, *args, **kwargs):
            captured["url"] = url
            return _ctx({"dates": []})

        session = mock.MagicMock()
        session.get.side_effect = side_effect
        from led_ticker_baseball.teams import next_game_date

        await next_game_date(session, TODAY)
        assert "teamId" not in captured["url"]

    async def test_skips_malformed_date(self):
        from led_ticker_baseball.teams import next_game_date

        session = make_session(
            {"/schedule": {"dates": [{"date": ""}, {"date": "nope"}, {"date": "2026-06-22"}]}}
        )
        assert await next_game_date(session, TODAY) == dt.date(2026, 6, 22)

    async def test_empty_returns_none(self):
        from led_ticker_baseball.teams import next_game_date

        session = make_session({"/schedule": {"dates": []}})
        assert await next_game_date(session, TODAY) is None

    async def test_failure_returns_none(self):
        from led_ticker_baseball.teams import next_game_date

        session = mock.MagicMock()
        session.get.side_effect = RuntimeError("network down")
        assert await next_game_date(session, TODAY) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_teams.py -v`
Expected: FAIL — `cannot import name 'next_game_date'`.

- [ ] **Step 3: Implement**

In `src/led_ticker_baseball/teams.py`, add `from datetime import date, timedelta` to the imports (top of file, before `import logging`/after — let ruff sort; the line just needs to exist). Then append at the end of the file:

```python
async def next_game_date(
    session: aiohttp.ClientSession,
    today: date,
    *,
    team_id: int = 0,
    lookahead_days: int = 30,
) -> date | None:
    """Earliest scheduled regular-season game date in
    ``[today, today + lookahead_days]``, optionally scoped to ``team_id``.

    Returns None on fetch failure or when no game is found. Shared by the
    statcast and attendance off-day/offseason fallbacks.
    """
    start = today.isoformat()
    end = (today + timedelta(days=lookahead_days)).isoformat()
    team_q = f"&teamId={team_id}" if team_id else ""
    url = (
        f"{MLB_API}/schedule?sportId=1&startDate={start}&endDate={end}"
        f"&gameType=R{team_q}"
    )
    try:
        async with session.get(url) as resp:
            data = await resp.json()
    except Exception:
        logger.debug("next_game_date probe failed")
        return None
    for date_entry in data.get("dates", []):
        raw = date_entry.get("date")
        if not raw:
            continue
        try:
            return date.fromisoformat(raw)
        except ValueError:
            continue
    return None
```

(`teams.py` already imports `aiohttp` and defines `logger` and `MLB_API`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_teams.py -v`
Expected: all PASS.

- [ ] **Step 5: Run full gates and commit**

```bash
uv run pytest -q && uv run ruff check src tests && uv run ruff format --check src tests && uv run pyright src
git add src/led_ticker_baseball/teams.py tests/test_teams.py
git commit -m "feat: shared teams.next_game_date() probe"
```

---

### Task 2: Normalize attendance schedule abbreviations

**Files:**
- Modify: `src/led_ticker_baseball/attendance.py`
- Modify: `tests/test_attendance.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_attendance.py` (the `sched_game` and `schedule` helpers and the `make_widget`/`_team_color` patterns already exist there):

```python
class TestScheduleAbbrNormalization:
    def _parse(self, data):
        from led_ticker_baseball.attendance import _parse_schedule_games

        return _parse_schedule_games(data)

    def test_savant_api_abbrs_normalized_to_canonical(self):
        data = schedule(
            sched_game(1, "Final", home="ATH", away="AZ", venue="Sutter Health Park")
        )
        g = self._parse(data)[0]
        assert g.home_abbr == "OAK"
        assert g.away_abbr == "ARI"

    def test_other_abbrs_unchanged(self):
        g = self._parse(schedule(sched_game(2, "Final", home="TOR", away="NYY")))[0]
        assert (g.home_abbr, g.away_abbr) == ("TOR", "NYY")

    def test_team_mode_matches_canonical_for_athletics(self):
        # User configures canonical "OAK"; schedule says "ATH" → still matched.
        w = make_widget(team="OAK")
        games = self._parse(
            schedule(sched_game(3, "Final", home="ATH", away="SEA"))
        )
        assert w._pick_team_game(games) is not None

    def test_athletics_venue_uses_brand_color_not_white(self):
        from led_ticker.colors import RGB_WHITE
        from led_ticker_baseball.teams import _team_color

        w = make_widget(stats=["biggest_crowd"])  # league mode
        gv = self._parse(
            schedule(sched_game(4, "Final", home="ATH", away="SEA", capacity=46000))
        )[0]
        # Build a league story for that game's crowd; venue colored by home abbr.
        from led_ticker_baseball.attendance import CrowdRecord

        rec = CrowdRecord(value=10000, venue=gv.venue, home_abbr=gv.home_abbr, is_pct=False)
        story = w._build_league_stories({"biggest_crowd": rec}, "Today")[0]
        venue_c = story.segments[-1][1]
        oak = _team_color("OAK")
        assert (venue_c.red, venue_c.green, venue_c.blue) == (oak.red, oak.green, oak.blue)
        assert venue_c is not RGB_WHITE
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_attendance.py -k AbbrNormalization -v`
Expected: FAIL — `home_abbr`/`away_abbr` are the raw `ATH`/`AZ`.

- [ ] **Step 3: Implement**

In `src/led_ticker_baseball/attendance.py`, add `API_TO_CANONICAL_ABBR` to the `teams` import. The current import block is:

```python
from led_ticker_baseball.teams import (
    MLB_API,
    _MLB_LIVE_API,
    _team_color,
    resolve_team_id,
)
```

Change it to include `API_TO_CANONICAL_ABBR` (ruff will sort — uppercase sorts before the underscore/lowercase names):

```python
from led_ticker_baseball.teams import (
    API_TO_CANONICAL_ABBR,
    MLB_API,
    _MLB_LIVE_API,
    _team_color,
    resolve_team_id,
)
```

Then in `_parse_schedule_games`, normalize the two abbreviations when building `GameVenue`:

```python
            games.append(
                GameVenue(
                    game_pk=g.get("gamePk", 0),
                    state=g.get("status", {}).get("abstractGameState", "Preview"),
                    game_number=g.get("gameNumber", 1),
                    home_abbr=API_TO_CANONICAL_ABBR.get(
                        home.get("abbreviation", ""), home.get("abbreviation", "")
                    ),
                    away_abbr=API_TO_CANONICAL_ABBR.get(
                        away.get("abbreviation", ""), away.get("abbreviation", "")
                    ),
                    venue=venue.get("name", ""),
                    capacity=venue.get("fieldInfo", {}).get("capacity", 0) or 0,
                )
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_attendance.py -q`
Expected: all PASS.

- [ ] **Step 5: Run full gates and commit**

```bash
uv run pytest -q && uv run ruff check src tests && uv run ruff format --check src tests && uv run pyright src
git add src/led_ticker_baseball/attendance.py tests/test_attendance.py
git commit -m "fix: normalize attendance schedule abbrs to canonical (A's/D-backs)"
```

---

### Task 3: Route both widgets' no-games fallback through `next_game_date`

**Files:**
- Modify: `src/led_ticker_baseball/statcast.py`
- Modify: `src/led_ticker_baseball/attendance.py`
- Modify: `tests/test_attendance.py`

- [ ] **Step 1: Write the failing test (attendance honest-degrade)**

Append to `tests/test_attendance.py`:

```python
class TestProbeHonestDegrade:
    async def test_team_set_but_unresolved_says_next_games(self):
        # team configured but id failed to resolve (_team_id == 0): the label
        # and the (absent) teamId query must agree — league fallback, not a
        # mislabeled "Next game" over a league-wide date.
        captured = {}

        def side_effect(url, *args, **kwargs):
            captured["url"] = url
            return _ctx({"dates": [{"date": "2027-03-26"}]})

        session = mock.MagicMock()
        session.get.side_effect = side_effect
        widget = make_widget(session=session, team="TOR")
        widget._team_id = 0  # resolve failed
        await widget._set_no_games_state(TODAY)
        assert widget.feed_stories[0].text == "Next games: Mar 26"
        assert "teamId" not in captured["url"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_attendance.py -k HonestDegrade -v`
Expected: FAIL — attendance currently gates the label on `self.team`, so it says `"Next game: Mar 26"`.

- [ ] **Step 3: Implement — statcast**

In `src/led_ticker_baseball/statcast.py`, add `next_game_date` to the `teams` import (the block is `from led_ticker_baseball.teams import (API_TO_CANONICAL_ABBR, MLB_API, _team_color, resolve_team_id)`; add `next_game_date`). Replace the whole `_set_no_games_state` body with:

```python
    async def _set_no_games_state(self, today: date) -> None:
        """Off-day / offseason fallback line.

        Team mode names the next game, league mode the next slate; both gate on
        ``_team_id`` so a failed resolve degrades honestly to the league line.
        The 30-day probe lives in ``teams.next_game_date``.
        """
        next_date = await next_game_date(self.session, today, team_id=self._team_id)
        if next_date is None:
            text = "No games soon"
        elif self._team_id:
            text = f"Next game: {next_date.strftime('%b %-d')}"
        else:
            text = f"Next games: {next_date.strftime('%b %-d')}"
        self.feed_stories = [
            TickerMessage(
                text,
                font_color=self._body_color(),
                center=True,
                bg_color=self.bg_color,
            ),
        ]
        logger.info("MLB Statcast updated: fallback (%s)", text)
```

If `timedelta` is now unused anywhere else in `statcast.py`, leave the import as-is only if still referenced; verify with ruff (it is still used by `update()`'s yesterday fallback, so the import stays).

- [ ] **Step 4: Implement — attendance**

In `src/led_ticker_baseball/attendance.py`, add `next_game_date` to the `teams` import. Replace the whole `_set_no_games_state` body with:

```python
    async def _set_no_games_state(self, today: date) -> None:
        """Off-day / offseason fallback line. Team mode names the next game,
        league mode the next slate; both gate on ``_team_id`` so a failed
        resolve degrades honestly. The 30-day probe lives in
        ``teams.next_game_date``.
        """
        next_date = await next_game_date(self.session, today, team_id=self._team_id)
        if next_date is None:
            text = "No games soon"
        elif self._team_id:
            text = f"Next game: {next_date.strftime('%b %-d')}"
        else:
            text = f"Next games: {next_date.strftime('%b %-d')}"
        self.feed_stories = [
            TickerMessage(
                text,
                font_color=self._body_color(),
                center=True,
                bg_color=self.bg_color,
            ),
        ]
        logger.info("MLB Attendance updated: fallback (%s)", text)
```

(Note: the only changes vs. the old attendance body are (a) the probe is delegated to `next_game_date`, and (b) the label gate is `self._team_id` instead of `self.team`.)

- [ ] **Step 5: Run tests + verify both widgets' probe regressions**

Run: `uv run pytest tests/test_attendance.py tests/test_statcast.py -q`
Expected: all PASS — including the existing attendance probe tests (`test_probe_finds_next_game_team_mode` sets `_team_id`, so still `"Next game"`; `test_probe_league_mode_next_games` → `"Next games"`; failure → `"No games soon"`) and the existing statcast probe tests (unchanged behavior through the helper).

- [ ] **Step 6: Run full gates and commit**

```bash
uv run pytest -q && uv run ruff check src tests && uv run ruff format --check src tests && uv run pyright src
git add src/led_ticker_baseball/statcast.py src/led_ticker_baseball/attendance.py tests/test_attendance.py
git commit -m "refactor: route statcast + attendance fallback through next_game_date (fixes attendance label gate)"
```

---

### Task 4: Final verification + PR

**Files:** none (verification + PR)

- [ ] **Step 1: Full gates + coverage**

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run pyright src
uv run pytest -q
uv run pytest --cov=src --cov-report=term-missing
```

Expected: lint/format/pyright clean; suite green; coverage ≥ 90% overall. Report `teams.py`, `attendance.py`, `statcast.py` percentages.

- [ ] **Step 2: Confirm the duplication is gone**

```bash
grep -n "gameType=R" src/led_ticker_baseball/*.py
```

Expected: the `gameType=R` probe URL now appears ONLY in `teams.py` (`next_game_date`), not in `statcast.py` or `attendance.py`.

- [ ] **Step 3: Push and open the PR**

```bash
git push -u origin attendance-abbr-and-probe-dry
gh pr create --title "fix: attendance A's/D-backs team codes + DRY the next-game probe" --body "$(cat <<'EOF'
## Summary
Follow-ups from the independent review of #14.
- **Attendance A's/D-backs fix:** `_parse_schedule_games` now normalizes schedule abbreviations through `teams.API_TO_CANONICAL_ABBR` (ATH→OAK, AZ→ARI), so team-mode matching and `_team_color` work for the Athletics and D-backs (previously `team="OAK"` never matched the schedule's `ATH`, and the venue rendered white).
- **DRY:** extracted the identical 30-day next-game probe both widgets ran into `teams.next_game_date(session, today, *, team_id=0, lookahead_days=30)`. statcast and attendance now call it.
- **Twin of #14 finding #2 (attendance):** attendance's fallback label now gates on `_team_id` (not `self.team`), matching statcast — a failed resolve degrades honestly to `Next games:` instead of mislabeling a league date.

## Test Plan
- [x] `uv run pytest -q` — full suite green (new: `test_teams.py` for `next_game_date`; attendance abbr-normalization + honest-degrade tests; statcast probe regressions unchanged)
- [x] ruff check + format clean; pyright 0 errors
- [x] Coverage ≥90%
- [x] `gameType=R` probe URL now exists only in `teams.py`

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Spec coverage self-check (for the reviewer)

- Change 1 (attendance schedule-abbr normalization → team matching + color) → Task 2
- Change 2 (extract `teams.next_game_date`, both widgets call it) → Tasks 1, 3
- Attendance label gate `self.team` → `self._team_id` (twin of #14 #2) → Task 3
- statcast probe output unchanged (regression-guarded) → Task 3 Step 5
- No README/CLAUDE.md change (no surface change) → not needed
- Tests: next_game_date (6 cases), attendance normalization (4), honest-degrade (1), regressions → Tasks 1–3
