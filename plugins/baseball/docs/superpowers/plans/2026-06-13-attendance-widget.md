# baseball.attendance Widget Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A dual-mode `baseball.attendance` widget — league-wide daily attendance superlatives (biggest/smallest crowd, fullest/emptiest park) when no `team` is set, or one team's game (attendance + fill % + venue + weather) when it is.

**Architecture:** New `MLBAttendanceMonitor` in `src/led_ticker_baseball/attendance.py`, mirroring `statcast.py` (schedule-gated stateless re-derive, today→yesterday→probe fallbacks) and `promotions.py` (per-team, validate_config). One shared schedule gate; league mode fans out lightweight boxscore fetches for attendance, team mode does one live-feed fetch. Spec: `docs/superpowers/specs/2026-06-13-attendance-widget-design.md`.

**Tech Stack:** Python 3.14, attrs, aiohttp, pytest (`asyncio_mode = "auto"`), uv, ruff (E/F/I/UP/B/SIM + format), pyright, coverage ≥90. Core imports ONLY from `led_ticker.plugin`. NO `from __future__ import annotations`.

**Branch discipline:** work on `attendance-widget` only; never checkout/switch branches; never commit to main.

**Gates — run all four before EVERY commit** (run `uv run ruff format src tests` first if the check fails):

```bash
uv run pytest -q
uv run ruff check src tests
uv run ruff format --check src tests
uv run pyright src
```

**Imports grow per task** so ruff's unused-import check stays green at every commit; each task lists its additions. Do not add imports a task's code doesn't use yet.

**File map:**

- Create: `src/led_ticker_baseball/attendance.py`
- Create: `tests/test_attendance.py`
- Modify: `src/led_ticker_baseball/__init__.py` (register widget + docstring)
- Modify: `tests/test_smoke.py` (assert registration)
- Modify: `README.md`, `CLAUDE.md` (docs)

---

### Task 1: Pure parse/format helpers

**Files:**
- Create: `src/led_ticker_baseball/attendance.py`
- Create: `tests/test_attendance.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_attendance.py` (no imports yet — these tests need none; later tasks add imports as they become needed):

```python
"""Tests for the MLB attendance widget (league superlatives + team mode)."""


class TestParseAttendance:
    def test_parses_att_with_commas_and_period(self):
        from led_ticker_baseball.attendance import _parse_attendance

        box = {"info": [{"label": "Att", "value": "19,587."}]}
        assert _parse_attendance(box) == 19587

    def test_missing_att_returns_none(self):
        from led_ticker_baseball.attendance import _parse_attendance

        box = {"info": [{"label": "Weather", "value": "Cloudy."}]}
        assert _parse_attendance(box) is None

    def test_empty_box_returns_none(self):
        from led_ticker_baseball.attendance import _parse_attendance

        assert _parse_attendance({}) is None

    def test_unparseable_value_returns_none(self):
        from led_ticker_baseball.attendance import _parse_attendance

        box = {"info": [{"label": "Att", "value": "n/a"}]}
        assert _parse_attendance(box) is None


class TestFillPct:
    def test_rounds_to_int_percent(self):
        from led_ticker_baseball.attendance import _fill_pct

        assert _fill_pct(19587, 38753) == 51

    def test_capacity_zero_or_missing_returns_none(self):
        from led_ticker_baseball.attendance import _fill_pct

        assert _fill_pct(19587, 0) is None
        assert _fill_pct(19587, None) is None


class TestFormatWeather:
    def test_formats_temp_condition_wind(self):
        from led_ticker_baseball.attendance import _format_weather

        w = {"condition": "Clear", "temp": "72", "wind": "5 mph, In From CF"}
        assert _format_weather(w) == "72° Clear, wind 5 mph, In From CF"

    def test_empty_weather_returns_none(self):
        from led_ticker_baseball.attendance import _format_weather

        assert _format_weather({}) is None
        assert _format_weather(None) is None

    def test_partial_weather_omits_missing_pieces(self):
        from led_ticker_baseball.attendance import _format_weather

        # No wind → just temp + condition; no temp → condition only.
        assert _format_weather({"condition": "Clear", "temp": "72"}) == "72° Clear"
        assert _format_weather({"condition": "Clear"}) == "Clear"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_attendance.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'led_ticker_baseball.attendance'`

- [ ] **Step 3: Create the module**

Create `src/led_ticker_baseball/attendance.py`:

```python
"""MLB ballpark attendance widget — league superlatives + team mode.

Two modes (chosen by whether ``team`` is configured): league-wide daily
attendance superlatives (biggest/smallest crowd, fullest/emptiest park by
capacity), or one tracked team's game (attendance + fill % + venue + weather).
All data is from the StatsAPI the plugin already uses; attendance exists only
once a game is Final (schedule has venue/capacity/state, the live feed has
weather, the boxscore carries the attendance string). Stateless: every refresh
re-derives, schedule-gated so off-hours ticks are cheap.
"""

import logging
import re
from typing import Any

logger: logging.Logger = logging.getLogger(__name__)

_DIGITS_RE: re.Pattern[str] = re.compile(r"\d")


def _parse_attendance(boxscore: dict[str, Any]) -> int | None:
    """Attendance from a boxscore's info[] 'Att' entry; None if absent/bad.

    The value is a formatted string like ``"19,587."`` — keep only digits.
    """
    for entry in boxscore.get("info", []):
        if entry.get("label") == "Att":
            digits = "".join(_DIGITS_RE.findall(entry.get("value", "")))
            return int(digits) if digits else None
    return None


def _fill_pct(attendance: int, capacity: int | None) -> int | None:
    """Rounded attendance/capacity percentage; None when capacity is 0/missing."""
    if not capacity:
        return None
    return round(attendance / capacity * 100)


def _format_weather(weather: dict[str, Any] | None) -> str | None:
    """'72° Clear, wind 5 mph, In From CF' from a feed weather dict.

    Returns None for empty/absent weather (future-day previews). Each piece is
    optional: temp+condition, or condition alone, etc.
    """
    if not weather:
        return None
    temp = weather.get("temp")
    condition = weather.get("condition")
    wind = weather.get("wind")
    head = f"{temp}° {condition}" if temp and condition else (condition or "")
    if not head:
        return None
    return f"{head}, wind {wind}" if wind else head
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_attendance.py -v`
Expected: all PASS

- [ ] **Step 5: Run full gates and commit**

```bash
uv run pytest -q && uv run ruff check src tests && uv run ruff format --check src tests && uv run pyright src
git add src/led_ticker_baseball/attendance.py tests/test_attendance.py
git commit -m "feat: attendance parse/format helpers"
```

---

### Task 2: Schedule parsing → GameVenue

**Files:**
- Modify: `src/led_ticker_baseball/attendance.py`
- Modify: `tests/test_attendance.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_attendance.py`:

```python
def sched_game(
    pk, state, home="PIT", away="MIA", venue="PNC Park", capacity=38753, game_number=1
):
    """A schedule game shaped like hydrate=venue(fieldInfo),team."""
    return {
        "gamePk": pk,
        "gameNumber": game_number,
        "status": {"abstractGameState": state},
        "teams": {
            "home": {"team": {"abbreviation": home}},
            "away": {"team": {"abbreviation": away}},
        },
        "venue": {"name": venue, "fieldInfo": {"capacity": capacity}},
    }


def schedule(*games):
    return {"dates": [{"games": list(games)}]}


class TestParseScheduleGames:
    def _parse(self, data):
        from led_ticker_baseball.attendance import _parse_schedule_games

        return _parse_schedule_games(data)

    def test_parses_fields(self):
        games = self._parse(schedule(sched_game(1, "Final")))
        g = games[0]
        assert (g.game_pk, g.state, g.home_abbr, g.away_abbr) == (1, "Final", "PIT", "MIA")
        assert (g.venue, g.capacity, g.game_number) == ("PNC Park", 38753, 1)

    def test_missing_capacity_is_zero(self):
        data = schedule(
            {
                "gamePk": 2,
                "gameNumber": 1,
                "status": {"abstractGameState": "Final"},
                "teams": {
                    "home": {"team": {"abbreviation": "ATH"}},
                    "away": {"team": {"abbreviation": "LAA"}},
                },
                "venue": {"name": "Sutter Health Park", "fieldInfo": {}},
            }
        )
        assert self._parse(data)[0].capacity == 0

    def test_empty_schedule(self):
        assert self._parse({"dates": []}) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_attendance.py -v`
Expected: TestParseScheduleGames FAIL with `ImportError: cannot import name '_parse_schedule_games'`

- [ ] **Step 3: Implement**

In `attendance.py`, add `from dataclasses import dataclass` to the imports (above `import logging`... ruff isort orders stdlib alphabetically: `from dataclasses import dataclass` then `import logging` then `import re` then `from typing import Any` — let the formatter sort; just add the line). Then append:

```python
@dataclass(frozen=True)
class GameVenue:
    game_pk: int
    state: str  # abstractGameState: Preview / Live / Final
    game_number: int
    home_abbr: str
    away_abbr: str
    venue: str
    capacity: int  # 0 when the venue has no listed capacity


def _parse_schedule_games(data: dict[str, Any]) -> list[GameVenue]:
    """Flatten a hydrate=venue(fieldInfo),team schedule into GameVenue rows."""
    games: list[GameVenue] = []
    for date_entry in data.get("dates", []):
        for g in date_entry.get("games", []):
            teams = g.get("teams", {})
            home = teams.get("home", {}).get("team", {})
            away = teams.get("away", {}).get("team", {})
            venue = g.get("venue", {})
            games.append(
                GameVenue(
                    game_pk=g.get("gamePk", 0),
                    state=g.get("status", {}).get("abstractGameState", "Preview"),
                    game_number=g.get("gameNumber", 1),
                    home_abbr=home.get("abbreviation", ""),
                    away_abbr=away.get("abbreviation", ""),
                    venue=venue.get("name", ""),
                    capacity=venue.get("fieldInfo", {}).get("capacity", 0) or 0,
                )
            )
    return games
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_attendance.py -v`
Expected: all PASS

- [ ] **Step 5: Run full gates and commit**

```bash
uv run pytest -q && uv run ruff check src tests && uv run ruff format --check src tests && uv run pyright src
git add src/led_ticker_baseball/attendance.py tests/test_attendance.py
git commit -m "feat: attendance schedule parsing (GameVenue)"
```

---

### Task 3: League superlative derivation

**Files:**
- Modify: `src/led_ticker_baseball/attendance.py`
- Modify: `tests/test_attendance.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_attendance.py`:

```python
class TestDeriveSuperlatives:
    def _derive(self, pairs, stats=None):
        from led_ticker_baseball.attendance import _STAT_KEYS, _derive_superlatives

        return _derive_superlatives(pairs, list(stats or _STAT_KEYS))

    def _pairs(self):
        # (GameVenue, attendance) for three final games of varying fill.
        return [
            (sched_gv(1, "Dodger Stadium", "LAD", 56000), 45123),  # 81%
            (sched_gv(2, "Wrigley Field", "CHC", 41649), 41600),   # ~100%
            (sched_gv(3, "PNC Park", "PIT", 38753), 8201),         # 21%
        ]

    def test_biggest_and_smallest_crowd(self):
        recs = self._derive(self._pairs())
        assert recs["biggest_crowd"].value == 45123
        assert recs["biggest_crowd"].venue == "Dodger Stadium"
        assert recs["smallest_crowd"].value == 8201
        assert recs["smallest_crowd"].venue == "PNC Park"

    def test_fullest_and_emptiest_pct(self):
        recs = self._derive(self._pairs())
        assert recs["fullest"].value == 100  # 41600/41649
        assert recs["fullest"].venue == "Wrigley Field"
        assert recs["emptiest"].value == 21  # 8201/38753
        assert recs["emptiest"].venue == "PNC Park"

    def test_pct_skips_zero_capacity_but_crowd_counts_it(self):
        pairs = [
            (sched_gv(1, "PNC Park", "PIT", 38753), 20000),
            (sched_gv(2, "Sutter Health", "ATH", 0), 9000),  # no capacity
        ]
        recs = self._derive(pairs)
        # Smallest crowd still considers the no-capacity game...
        assert recs["smallest_crowd"].value == 9000
        # ...but emptiest/fullest only consider games with capacity.
        assert recs["emptiest"].venue == "PNC Park"
        assert recs["fullest"].venue == "PNC Park"

    def test_record_carries_home_abbr(self):
        recs = self._derive(self._pairs())
        assert recs["biggest_crowd"].home_abbr == "LAD"

    def test_tie_keeps_first(self):
        pairs = [
            (sched_gv(1, "A Park", "PIT", 40000), 30000),
            (sched_gv(2, "B Park", "CHC", 40000), 30000),
        ]
        assert self._derive(pairs)["biggest_crowd"].venue == "A Park"

    def test_unrequested_stats_not_derived(self):
        recs = self._derive(self._pairs(), stats=["biggest_crowd"])
        assert set(recs) == {"biggest_crowd"}

    def test_empty_pairs(self):
        assert self._derive([]) == {}
```

Add the `sched_gv` helper near the top of the file (after `schedule(...)`):

```python
def sched_gv(pk, venue, home, capacity, away="OPP", state="Final"):
    from led_ticker_baseball.attendance import GameVenue

    return GameVenue(
        game_pk=pk,
        state=state,
        game_number=1,
        home_abbr=home,
        away_abbr=away,
        venue=venue,
        capacity=capacity,
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_attendance.py -v`
Expected: TestDeriveSuperlatives FAIL with `ImportError` on `_STAT_KEYS`/`_derive_superlatives`

- [ ] **Step 3: Implement**

In `attendance.py`, after `_format_weather` (and before `GameVenue`, or after it — keep `CrowdRecord`/derivation grouped together after `GameVenue`), add the stat constants near the top after `logger`:

```python
_STAT_KEYS: tuple[str, ...] = (
    "biggest_crowd",
    "smallest_crowd",
    "fullest",
    "emptiest",
)

_STAT_LABELS: dict[str, str] = {
    "biggest_crowd": "Biggest crowd",
    "smallest_crowd": "Smallest crowd",
    "fullest": "Fullest",
    "emptiest": "Emptiest",
}
```

After `GameVenue` / `_parse_schedule_games`, add:

```python
@dataclass(frozen=True)
class CrowdRecord:
    value: int  # raw attendance for crowd stats, percent for fullest/emptiest
    venue: str
    home_abbr: str
    is_pct: bool  # True → render value as "NN%"


def _derive_superlatives(
    pairs: list[tuple[GameVenue, int]], stats: list[str]
) -> dict[str, CrowdRecord]:
    """Best record per requested superlative over (game, attendance) pairs.

    Crowd stats use raw attendance over all pairs; fullest/emptiest use
    attendance/capacity over pairs with capacity > 0. Strict comparisons keep
    the first pair on ties (schedule order).
    """
    records: dict[str, CrowdRecord] = {}

    def consider(key: str, value: int, gv: GameVenue, *, lower: bool) -> None:
        cur = records.get(key)
        if cur is not None and (value >= cur.value if lower else value <= cur.value):
            return
        is_pct = key in ("fullest", "emptiest")
        records[key] = CrowdRecord(
            value=value, venue=gv.venue, home_abbr=gv.home_abbr, is_pct=is_pct
        )

    for gv, att in pairs:
        if "biggest_crowd" in stats:
            consider("biggest_crowd", att, gv, lower=False)
        if "smallest_crowd" in stats:
            consider("smallest_crowd", att, gv, lower=True)
        pct = _fill_pct(att, gv.capacity)
        if pct is not None:
            if "fullest" in stats:
                consider("fullest", pct, gv, lower=False)
            if "emptiest" in stats:
                consider("emptiest", pct, gv, lower=True)
    return records
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_attendance.py -v`
Expected: all PASS

- [ ] **Step 5: Run full gates and commit**

```bash
uv run pytest -q && uv run ruff check src tests && uv run ruff format --check src tests && uv run pyright src
git add src/led_ticker_baseball/attendance.py tests/test_attendance.py
git commit -m "feat: attendance league superlative derivation"
```

---

### Task 4: Widget skeleton, title, colors, gate

**Files:**
- Modify: `src/led_ticker_baseball/attendance.py`
- Modify: `tests/test_attendance.py`

- [ ] **Step 1: Write the failing tests**

Add to the top of `tests/test_attendance.py`:

```python
import datetime as dt
import unittest.mock as mock
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
TODAY = dt.date(2026, 6, 13)
```

Append:

```python
def make_widget(**kwargs):
    from led_ticker_baseball.attendance import MLBAttendanceMonitor

    widget = MLBAttendanceMonitor(session=kwargs.pop("session", mock.Mock()), **kwargs)
    widget._tz = NY
    return widget


class TestSkeleton:
    def test_default_is_league_mode_all_stats(self):
        from led_ticker_baseball.attendance import _STAT_KEYS

        w = make_widget()
        assert w.team == ""
        assert w.stats == list(_STAT_KEYS)

    def test_team_mode_when_team_set(self):
        assert make_widget(team="tor").team == "tor"  # not upper-cased until start()

    def test_default_title(self):
        w = make_widget()
        w._set_title()
        assert w.feed_title.text == "Attendance"

    def test_title_override(self):
        w = make_widget(title="Turnstiles")
        w._set_title()
        assert w.feed_title.text == "Turnstiles"

    def test_font_color_selected_for_body(self):
        from led_ticker.plugin import make_color

        c = make_color(255, 0, 0)
        w = make_widget(font_color=c)
        assert w._body_color() is c
        assert w._plain_body_color() is c

    def test_default_body_color_is_white(self):
        from led_ticker.colors import RGB_WHITE

        w = make_widget()
        assert w._body_color() is RGB_WHITE
        assert w._plain_body_color() is RGB_WHITE


class TestShouldSkip:
    def test_no_prior_derive_never_skips(self):
        assert make_widget()._should_skip(TODAY, (0, 5)) is False

    def test_gate_failure_fails_open(self):
        w = make_widget()
        w._last_derive = (TODAY, 5)
        assert w._should_skip(TODAY, None) is False

    def test_skips_when_unchanged(self):
        w = make_widget()
        w._last_derive = (TODAY, 5)
        assert w._should_skip(TODAY, (0, 5)) is True

    def test_live_forces_derive(self):
        w = make_widget()
        w._last_derive = (TODAY, 5)
        assert w._should_skip(TODAY, (1, 5)) is False

    def test_new_final_forces_derive(self):
        w = make_widget()
        w._last_derive = (TODAY, 5)
        assert w._should_skip(TODAY, (0, 6)) is False

    def test_date_rollover_forces_derive(self):
        w = make_widget()
        w._last_derive = (TODAY - dt.timedelta(days=1), 5)
        assert w._should_skip(TODAY, (0, 5)) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_attendance.py -v`
Expected: new tests FAIL with `ImportError: cannot import name 'MLBAttendanceMonitor'`

- [ ] **Step 3: Implement**

In `attendance.py`, replace the import block (keep the module docstring) with:

```python
import logging
import re
from dataclasses import dataclass
from datetime import date
from typing import Any
from zoneinfo import ZoneInfo

import aiohttp
import attrs

from led_ticker.plugin import (
    FONT_DEFAULT,
    Color,
    ColorProvider,
    Font,
    SegmentMessage,
    TickerMessage,
    colors,
)
```

Append at the end of the file:

```python
@attrs.define
class MLBAttendanceMonitor:
    """Ballpark attendance — league superlatives, or one team's game."""

    session: aiohttp.ClientSession
    team: str = ""  # "" → league mode; else team mode
    stats: list[str] = attrs.field(factory=lambda: list(_STAT_KEYS))
    title: str = "Attendance"
    timezone: str = "America/New_York"
    padding: int = 6
    hold_time: float = 0.0
    bg_color: Color | None = attrs.field(default=None, kw_only=True)
    font_color: Color | ColorProvider | None = attrs.field(default=None, kw_only=True)
    font: Font = attrs.field(default=FONT_DEFAULT, kw_only=True)
    _tz: ZoneInfo | None = attrs.field(init=False, default=None)
    _team_id: int = attrs.field(init=False, default=0)
    # (local date, Final count) at the last successful derive; None until the
    # first success (and after any error/fallback).
    _last_derive: tuple[date, int] | None = attrs.field(init=False, default=None)
    feed_title: TickerMessage | SegmentMessage | None = attrs.field(
        init=False, default=None
    )
    feed_stories: list[TickerMessage | SegmentMessage] = attrs.field(
        init=False, factory=list
    )

    def _body_color(self) -> Color | ColorProvider:
        return self.font_color if self.font_color is not None else colors.RGB_WHITE

    def _plain_body_color(self) -> Color | ColorProvider:
        """Body-text color for per-segment use; a plain Color tints body text
        while callout segments keep their colors, a provider passes through and
        overrides every segment in core (same as the sibling widgets)."""
        if self.font_color is not None and not hasattr(self.font_color, "color_for"):
            return self.font_color
        return colors.RGB_WHITE

    def _set_title(self) -> None:
        self.feed_title = TickerMessage(
            self.title,
            font_color=self._body_color(),
            center=True,
            bg_color=self.bg_color,
        )

    def _should_skip(self, today: date, counts: tuple[int, int] | None) -> bool:
        """Skip refetch when nothing changed since the last successful derive.

        Re-derive when the gate fetch failed, no prior derive, the date rolled,
        any game is live, or the Final count moved.
        """
        if counts is None or self._last_derive is None:
            return False
        snap_day, snap_final = self._last_derive
        live, final = counts
        return snap_day == today and live == 0 and final == snap_final
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_attendance.py -v`
Expected: all PASS

- [ ] **Step 5: Run full gates and commit**

```bash
uv run pytest -q && uv run ruff check src tests && uv run ruff format --check src tests && uv run pyright src
git add src/led_ticker_baseball/attendance.py tests/test_attendance.py
git commit -m "feat: MLBAttendanceMonitor skeleton + gate decision"
```

---

### Task 5: League story building

**Files:**
- Modify: `src/led_ticker_baseball/attendance.py`
- Modify: `tests/test_attendance.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_attendance.py`:

```python
def crowd_rec(value, venue="Dodger Stadium", home="LAD", is_pct=False):
    from led_ticker_baseball.attendance import CrowdRecord

    return CrowdRecord(value=value, venue=venue, home_abbr=home, is_pct=is_pct)


def line_text(story):
    return "".join(seg[0] for seg in story.segments)


class TestBuildLeagueStories:
    def test_crowd_line_format(self):
        w = make_widget(stats=["biggest_crowd"])
        recs = {"biggest_crowd": crowd_rec(45123)}
        stories = w._build_league_stories(recs, "Today")
        assert line_text(stories[0]) == "Today · Biggest crowd 45,123 — Dodger Stadium"

    def test_pct_line_format(self):
        w = make_widget(stats=["emptiest"])
        recs = {"emptiest": crowd_rec(51, venue="PNC Park", home="PIT", is_pct=True)}
        stories = w._build_league_stories(recs, "Today")
        assert line_text(stories[0]) == "Today · Emptiest 51% — PNC Park"

    def test_stats_order_controls_display(self):
        w = make_widget(stats=["emptiest", "biggest_crowd"])
        recs = {
            "biggest_crowd": crowd_rec(45123),
            "emptiest": crowd_rec(51, is_pct=True),
        }
        stories = w._build_league_stories(recs, "Today")
        assert "Emptiest" in line_text(stories[0])
        assert "Biggest crowd" in line_text(stories[1])

    def test_missing_stat_omits_line(self):
        w = make_widget()
        stories = w._build_league_stories({"biggest_crowd": crowd_rec(45123)}, "Today")
        assert len(stories) == 1

    def test_colors_day_grey_value_amber_venue_branded(self):
        from led_ticker.colors import RGB_WHITE

        w = make_widget(stats=["biggest_crowd"])
        stories = w._build_league_stories({"biggest_crowd": crowd_rec(45123)}, "Today")
        segs = stories[0].segments
        day_c, value_c, venue_c = segs[0][1], segs[2][1], segs[-1][1]
        assert (day_c.red, day_c.green, day_c.blue) == (150, 150, 150)
        assert (value_c.red, value_c.green, value_c.blue) == (255, 200, 60)
        from led_ticker_baseball.teams import _team_color

        lad = _team_color("LAD")
        assert (venue_c.red, venue_c.green, venue_c.blue) == (lad.red, lad.green, lad.blue)

    def test_stories_centered(self):
        w = make_widget(stats=["biggest_crowd"])
        stories = w._build_league_stories({"biggest_crowd": crowd_rec(45123)}, "Today")
        assert stories[0].center is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_attendance.py -v`
Expected: TestBuildLeagueStories FAIL with `AttributeError: ... '_build_league_stories'`

- [ ] **Step 3: Implement**

In `attendance.py`, add `make_color` to the `led_ticker.plugin` import block, and below it add:

```python
from led_ticker_baseball.teams import _team_color
```

Add this method to `MLBAttendanceMonitor`:

```python
    def _fmt_value(self, rec: CrowdRecord) -> str:
        return f"{rec.value}%" if rec.is_pct else f"{rec.value:,}"

    def _build_league_stories(
        self, records: dict[str, CrowdRecord], day_label: str
    ) -> list[TickerMessage | SegmentMessage]:
        """One centered line per superlative: 'Today · Biggest crowd 45,123 — Dodger Stadium'.

        Day label grey, value amber, venue in the home team's brand color.
        ``self.stats`` order is display order; missing stats are omitted.
        """
        grey = make_color(150, 150, 150)
        amber = make_color(255, 200, 60)
        body_c = self._plain_body_color()

        stories: list[TickerMessage | SegmentMessage] = []
        for key in self.stats:
            rec = records.get(key)
            if rec is None:
                continue
            segments: list[tuple[str, Color | ColorProvider]] = [
                (f"{day_label} · ", grey),
                (f"{_STAT_LABELS[key]} ", body_c),
                (self._fmt_value(rec), amber),
                (" — ", body_c),
                (rec.venue, _team_color(rec.home_abbr)),
            ]
            stories.append(
                SegmentMessage(
                    segments,
                    center=True,
                    bg_color=self.bg_color,
                    font=self.font,
                    font_color=self.font_color,
                )
            )
        return stories
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_attendance.py -v`
Expected: all PASS

- [ ] **Step 5: Run full gates and commit**

```bash
uv run pytest -q && uv run ruff check src tests && uv run ruff format --check src tests && uv run pyright src
git add src/led_ticker_baseball/attendance.py tests/test_attendance.py
git commit -m "feat: attendance league story lines"
```

---

### Task 6: Team line building

**Files:**
- Modify: `src/led_ticker_baseball/attendance.py`
- Modify: `tests/test_attendance.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_attendance.py`:

```python
class TestBuildTeamLine:
    def _w(self):
        w = make_widget(team="TOR")
        return w

    def test_final_line_has_attendance_pct_and_weather(self):
        w = self._w()
        story = w._build_team_line(
            venue="Rogers Centre",
            attendance=41212,
            capacity=46000,
            weather={"condition": "Clear", "temp": "72", "wind": "5 mph, In From CF"},
            day_label="",
        )
        assert line_text(story) == (
            "TOR · Rogers Centre 41,212 (90%) · 72° Clear, wind 5 mph, In From CF"
        )

    def test_pregame_line_omits_attendance(self):
        w = self._w()
        story = w._build_team_line(
            venue="Rogers Centre",
            attendance=None,
            capacity=46000,
            weather={"condition": "Clear", "temp": "72"},
            day_label="",
        )
        assert line_text(story) == "TOR · Rogers Centre · 72° Clear"

    def test_capacity_missing_drops_pct(self):
        w = self._w()
        story = w._build_team_line(
            venue="Sutter Health Park",
            attendance=9000,
            capacity=0,
            weather=None,
            day_label="",
        )
        assert line_text(story) == "TOR · Sutter Health Park 9,000"

    def test_missing_weather_omitted(self):
        w = self._w()
        story = w._build_team_line(
            venue="Rogers Centre", attendance=None, capacity=46000,
            weather=None, day_label="",
        )
        assert line_text(story) == "TOR · Rogers Centre"

    def test_yesterday_prefixes_short_date(self):
        w = self._w()
        story = w._build_team_line(
            venue="Rogers Centre", attendance=41212, capacity=46000,
            weather=None, day_label="6/12",
        )
        assert line_text(story) == "6/12 · TOR · Rogers Centre 41,212 (90%)"

    def test_team_prefix_brand_color(self):
        from led_ticker.colors import RGB_WHITE
        from led_ticker_baseball.teams import _team_color

        w = self._w()
        story = w._build_team_line(
            venue="Rogers Centre", attendance=None, capacity=0,
            weather=None, day_label="",
        )
        prefix_c = story.segments[0][1]
        tor = _team_color("TOR")
        assert (prefix_c.red, prefix_c.green, prefix_c.blue) == (tor.red, tor.green, tor.blue)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_attendance.py -v`
Expected: TestBuildTeamLine FAIL with `AttributeError: ... '_build_team_line'`

- [ ] **Step 3: Implement**

Add this method to `MLBAttendanceMonitor`:

```python
    def _build_team_line(
        self,
        *,
        venue: str,
        attendance: int | None,
        capacity: int,
        weather: dict[str, Any] | None,
        day_label: str,
    ) -> SegmentMessage:
        """The tracked team's single game line.

        '[<6/12> · ]TOR · <venue>[ <att> (<pct>%)][ · <weather>]'. Attendance
        appears only when known (Final); the percent only with a capacity; the
        weather segment only when present. ``day_label`` prefixes the short date
        on the yesterday fallback (empty string for today).
        """
        grey = make_color(150, 150, 150)
        amber = make_color(255, 200, 60)
        body_c = self._plain_body_color()

        segments: list[tuple[str, Color | ColorProvider]] = []
        if day_label:
            segments.append((f"{day_label} · ", grey))
        segments.append((f"{self.team} ", _team_color(self.team)))

        venue_text = f"· {venue}" if venue else "·"
        if attendance is not None:
            pct = _fill_pct(attendance, capacity)
            att_text = f" {attendance:,}" + (f" ({pct}%)" if pct is not None else "")
            segments.append((venue_text, body_c))
            segments.append((att_text, amber))
        else:
            segments.append((venue_text, body_c))

        weather_text = _format_weather(weather)
        if weather_text:
            segments.append((f" · {weather_text}", body_c))

        return SegmentMessage(
            segments,
            center=True,
            bg_color=self.bg_color,
            font=self.font,
            font_color=self.font_color,
        )
```

Note: the venue segment leads with `· ` so the line reads `TOR · Rogers Centre`. The team prefix is `"TOR "` (trailing space), so concatenation yields `TOR · Rogers Centre` — matches the tests.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_attendance.py -v`
Expected: all PASS

- [ ] **Step 5: Run full gates and commit**

```bash
uv run pytest -q && uv run ruff check src tests && uv run ruff format --check src tests && uv run pyright src
git add src/led_ticker_baseball/attendance.py tests/test_attendance.py
git commit -m "feat: attendance team line"
```

---

### Task 7: Async fetchers

**Files:**
- Modify: `src/led_ticker_baseball/attendance.py`
- Modify: `tests/test_attendance.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_attendance.py`:

```python
def _ctx(payload):
    resp = mock.AsyncMock()
    resp.raise_for_status = mock.Mock()
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


def boxscore(att):
    info = [{"label": "Att", "value": att}] if att is not None else []
    return {"info": info}


class TestFetchSchedule:
    async def test_returns_games_and_counts(self):
        session = make_session(
            {
                "hydrate=venue(fieldInfo),team": schedule(
                    sched_game(1, "Live"),
                    sched_game(2, "Final"),
                    sched_game(3, "Preview"),
                )
            }
        )
        w = make_widget(session=session)
        games, counts = await w._fetch_schedule(TODAY)
        assert counts == (1, 1)  # (live, final)
        assert len(games) == 3

    async def test_failure_returns_none(self):
        session = mock.MagicMock()
        session.get.side_effect = RuntimeError("down")
        w = make_widget(session=session)
        assert await w._fetch_schedule(TODAY) == (None, None)


class TestFetchAttendance:
    async def test_parses_boxscore(self):
        session = make_session({"/boxscore": boxscore("19,587.")})
        w = make_widget(session=session)
        assert await w._fetch_attendance(823370) == 19587

    async def test_missing_returns_none(self):
        session = make_session({"/boxscore": boxscore(None)})
        w = make_widget(session=session)
        assert await w._fetch_attendance(823370) is None

    async def test_failure_returns_none(self):
        session = mock.MagicMock()
        session.get.side_effect = RuntimeError("down")
        w = make_widget(session=session)
        assert await w._fetch_attendance(1) is None


class TestFetchGameData:
    async def test_returns_attendance_weather_venue_capacity(self):
        feed = {
            "gameData": {
                "gameInfo": {"attendance": 19587},
                "weather": {"condition": "Clear", "temp": "72", "wind": "5 mph"},
                "venue": {"name": "PNC Park", "fieldInfo": {"capacity": 38753}},
            }
        }
        session = make_session({"/feed/live": feed})
        w = make_widget(session=session)
        att, weather, venue, cap = await w._fetch_game_data(823370)
        assert att == 19587
        assert weather["condition"] == "Clear"
        assert venue == "PNC Park"
        assert cap == 38753

    async def test_pregame_attendance_none(self):
        feed = {
            "gameData": {
                "gameInfo": {},
                "weather": {"condition": "Clear", "temp": "72"},
                "venue": {"name": "PNC Park", "fieldInfo": {}},
            }
        }
        session = make_session({"/feed/live": feed})
        w = make_widget(session=session)
        att, weather, venue, cap = await w._fetch_game_data(823370)
        assert att is None
        assert cap == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_attendance.py -v`
Expected: new tests FAIL with `AttributeError` on the fetcher methods.

- [ ] **Step 3: Implement**

In `attendance.py`: add `MLB_API` and `_MLB_LIVE_API` to the teams import (`from led_ticker_baseball.teams import MLB_API, _MLB_LIVE_API, _team_color`). Add these methods to `MLBAttendanceMonitor`:

```python
    async def _fetch_schedule(
        self, day: date
    ) -> tuple[list[GameVenue] | None, tuple[int, int] | None]:
        """Gated schedule fetch → (games, (live, final) counts). (None, None)
        on failure (fail open)."""
        url = (
            f"{MLB_API}/schedule?sportId=1&date={day.isoformat()}"
            f"&hydrate=venue(fieldInfo),team"
        )
        try:
            async with self.session.get(url) as resp:
                data = await resp.json()
        except Exception:
            logger.debug("MLB Attendance schedule fetch failed")
            return None, None
        games = _parse_schedule_games(data)
        live = sum(g.state == "Live" for g in games)
        final = sum(g.state == "Final" for g in games)
        return games, (live, final)

    async def _fetch_attendance(self, game_pk: int) -> int | None:
        """Boxscore attendance for one game; None on failure or absence."""
        url = f"{MLB_API}/game/{game_pk}/boxscore"
        try:
            async with self.session.get(url) as resp:
                data = await resp.json()
        except Exception:
            logger.debug("MLB Attendance boxscore fetch failed for %s", game_pk)
            return None
        return _parse_attendance(data)

    async def _fetch_game_data(
        self, game_pk: int
    ) -> tuple[int | None, dict[str, Any] | None, str, int]:
        """Live feed → (attendance, weather, venue_name, capacity).

        Raises on fetch failure — the caller owns the error state.
        """
        url = f"{_MLB_LIVE_API}/game/{game_pk}/feed/live"
        async with self.session.get(url) as resp:
            data = await resp.json()
        gd = data.get("gameData", {})
        att = gd.get("gameInfo", {}).get("attendance")
        weather = gd.get("weather") or None
        venue = gd.get("venue", {})
        return (
            att if isinstance(att, int) else None,
            weather,
            venue.get("name", ""),
            venue.get("fieldInfo", {}).get("capacity", 0) or 0,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_attendance.py -v`
Expected: all PASS

- [ ] **Step 5: Run full gates and commit**

```bash
uv run pytest -q && uv run ruff check src tests && uv run ruff format --check src tests && uv run pyright src
git add src/led_ticker_baseball/attendance.py tests/test_attendance.py
git commit -m "feat: attendance schedule/boxscore/feed fetchers"
```

---

### Task 8: Error + no-games (probe) states

**Files:**
- Modify: `src/led_ticker_baseball/attendance.py`
- Modify: `tests/test_attendance.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_attendance.py`:

```python
class TestFallbackStates:
    def test_error_state(self):
        w = make_widget()
        w._set_error_state()
        assert w.feed_stories[0].text == "No Data"

    async def test_probe_finds_next_game_team_mode(self):
        # Team mode → "Next game: <date>".
        session = make_session(
            {"startDate": {"dates": [{"date": "2027-03-26"}]}}
        )
        w = make_widget(session=session, team="TOR")
        w._team_id = 141
        await w._set_no_games_state(TODAY)
        assert w.feed_stories[0].text == "Next game: Mar 26"

    async def test_probe_empty_says_no_games_soon(self):
        session = make_session({"startDate": {"dates": []}})
        w = make_widget(session=session, team="TOR")
        w._team_id = 141
        await w._set_no_games_state(TODAY)
        assert w.feed_stories[0].text == "No games soon"

    async def test_probe_league_mode_no_games_soon(self):
        # League mode (no team) → always "No games soon" (no single next game).
        session = make_session(
            {"startDate": {"dates": [{"date": "2027-03-26"}]}}
        )
        w = make_widget(session=session)
        await w._set_no_games_state(TODAY)
        assert w.feed_stories[0].text == "Next games: Mar 26"

    async def test_probe_failure_degrades(self):
        session = mock.MagicMock()
        session.get.side_effect = RuntimeError("down")
        w = make_widget(session=session, team="TOR")
        w._team_id = 141
        await w._set_no_games_state(TODAY)
        assert w.feed_stories[0].text == "No games soon"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_attendance.py -v`
Expected: TestFallbackStates FAIL with `AttributeError`.

- [ ] **Step 3: Implement**

In `attendance.py`, change the datetime import to `from datetime import date, timedelta`. Add to `MLBAttendanceMonitor`:

```python
    # Contract: the _set_*_state setters manage feed_stories only. update()
    # calls _set_title() first, so feed_title is always set, including on error.

    def _set_error_state(self) -> None:
        self.feed_stories = [
            TickerMessage(
                "No Data", font_color=self._body_color(), bg_color=self.bg_color
            ),
        ]
        logger.info("MLB Attendance updated: %d stories (no data)", len(self.feed_stories))

    async def _set_no_games_state(self, today: date) -> None:
        """Off-day / offseason probe (30 days). Team mode names the next game
        date; league mode names the next slate. Failed probe → 'No games soon'.
        """
        start = today.isoformat()
        end = (today + timedelta(days=30)).isoformat()
        team_q = f"&teamId={self._team_id}" if self.team else ""
        url = (
            f"{MLB_API}/schedule?sportId=1&startDate={start}&endDate={end}"
            f"&gameType=R{team_q}"
        )
        data: dict[str, Any] = {}
        try:
            async with self.session.get(url) as resp:
                data = await resp.json()
        except Exception:
            logger.debug("MLB Attendance probe failed")
        next_date: date | None = None
        for date_entry in data.get("dates", []):
            raw = date_entry.get("date")
            if not raw:
                continue
            try:
                next_date = date.fromisoformat(raw)
                break
            except ValueError:
                continue
        if next_date is None:
            text = "No games soon"
        elif self.team:
            text = f"Next game: {next_date.strftime('%b %-d')}"
        else:
            text = f"Next games: {next_date.strftime('%b %-d')}"
        self.feed_stories = [
            TickerMessage(
                text, font_color=self._body_color(), center=True, bg_color=self.bg_color
            ),
        ]
        logger.info("MLB Attendance updated: fallback (%s)", text)
```

Date formats mirror the shipped statcast widget exactly: the probe "Next
game(s)" line uses `%b %-d` ("Mar 26"), while the yesterday fallback label
(Task 9) uses `%-m/%-d` ("6/12"). The Task 8 tests above already expect the
`%b %-d` form ("Mar 26").

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_attendance.py -v`
Expected: all PASS

- [ ] **Step 5: Run full gates and commit**

```bash
uv run pytest -q && uv run ruff check src tests && uv run ruff format --check src tests && uv run pyright src
git add src/led_ticker_baseball/attendance.py tests/test_attendance.py
git commit -m "feat: attendance error + no-games probe states"
```

---

### Task 9: update() + start()

**Files:**
- Modify: `src/led_ticker_baseball/attendance.py`
- Modify: `tests/test_attendance.py`

- [ ] **Step 1: Write the failing tests**

Add `import asyncio` and `import logging` to the top of `tests/test_attendance.py` (alphabetical with the others). `update()` uses real wall-clock today, so freeze it. Append:

```python
def _freeze_today():
    now = dt.datetime.now(NY)
    frozen = mock.Mock(wraps=dt.datetime)
    frozen.now.return_value = now
    patcher = mock.patch("led_ticker_baseball.attendance.datetime", frozen)
    return patcher, now.date()


def feed(att=None, condition="Clear", temp="72", venue="Rogers Centre", cap=46000):
    gi = {"attendance": att} if att is not None else {}
    return {
        "gameData": {
            "gameInfo": gi,
            "weather": {"condition": condition, "temp": temp, "wind": "5 mph"},
            "venue": {"name": venue, "fieldInfo": {"capacity": cap}},
        }
    }


class TestUpdateLeague:
    def _widget(self, routes, **kwargs):
        w = make_widget(session=make_session(routes), **kwargs)
        w._tz = NY
        return w

    async def test_today_finals_build_superlatives(self):
        patcher, today = _freeze_today()
        sched = schedule(
            sched_game(11, "Final", home="LAD", venue="Dodger Stadium", capacity=56000),
            sched_game(22, "Final", home="PIT", venue="PNC Park", capacity=38753),
        )
        routes = {
            "hydrate=venue(fieldInfo),team": sched,
            "/game/11/boxscore": boxscore("45,123."),
            "/game/22/boxscore": boxscore("8,201."),
        }
        w = self._widget(routes, stats=["biggest_crowd", "smallest_crowd"])
        with patcher:
            await w.update()
        assert line_text(w.feed_stories[0]) == (
            "Today · Biggest crowd 45,123 — Dodger Stadium"
        )
        assert line_text(w.feed_stories[1]) == (
            "Today · Smallest crowd 8,201 — PNC Park"
        )
        assert w._last_derive == (today, 2)

    async def test_no_finals_today_falls_back_to_yesterday(self):
        patcher, today = _freeze_today()
        yest = today - dt.timedelta(days=1)
        empty = schedule(sched_game(1, "Preview"))
        ysched = schedule(
            sched_game(33, "Final", home="CHC", venue="Wrigley Field", capacity=41649)
        )
        # Route schedule by date param so today vs yesterday differ.
        routes = {
            f"date={today.isoformat()}": empty,
            f"date={yest.isoformat()}": ysched,
            "/game/33/boxscore": boxscore("41,600."),
        }
        w = self._widget(routes, stats=["biggest_crowd"])
        with patcher:
            await w.update()
        assert line_text(w.feed_stories[0]).startswith(f"{yest.strftime('%-m/%-d')} · ")

    async def test_error_sets_no_data(self):
        patcher, today = _freeze_today()

        def side_effect(url, *args, **kwargs):
            if "/boxscore" in url:
                raise RuntimeError("boxscore down")
            return _ctx(schedule(sched_game(11, "Final")))

        session = mock.MagicMock()
        session.get.side_effect = side_effect
        w = make_widget(session=session)
        w._tz = NY
        with patcher:
            await w.update()
        # A single boxscore failure is skipped (not fatal); with the only game's
        # attendance unavailable, there are no superlatives → yesterday probe.
        # Yesterday also empty here → no-games fallback.
        assert w.feed_stories  # something rendered, not a crash


class TestUpdateTeam:
    def _widget(self, routes, **kwargs):
        w = make_widget(session=make_session(routes), team="TOR", **kwargs)
        w._tz = NY
        w._team_id = 141
        return w

    async def test_team_final_line(self):
        patcher, today = _freeze_today()
        sched = schedule(
            sched_game(99, "Final", home="TOR", away="BOS", venue="Rogers Centre", capacity=46000)
        )
        routes = {
            "hydrate=venue(fieldInfo),team": sched,
            "/game/99/feed/live": feed(att=41212),
        }
        w = self._widget(routes)
        with patcher:
            await w.update()
        assert line_text(w.feed_stories[0]).startswith("TOR · Rogers Centre 41,212")

    async def test_team_no_game_today_then_probe(self):
        patcher, today = _freeze_today()
        yest = today - dt.timedelta(days=1)
        routes = {
            f"date={today.isoformat()}": schedule(sched_game(1, "Final", home="NYY", away="BOS")),
            f"date={yest.isoformat()}": schedule(sched_game(2, "Final", home="NYY", away="BOS")),
            "startDate": {"dates": [{"date": "2026-06-20"}]},
        }
        w = self._widget(routes)
        with patcher:
            await w.update()
        assert w.feed_stories[0].text == "Next game: Jun 20"

    async def test_update_logs_info(self, caplog):
        patcher, today = _freeze_today()
        sched = schedule(sched_game(99, "Final", home="TOR", venue="Rogers Centre"))
        routes = {
            "hydrate=venue(fieldInfo),team": sched,
            "/game/99/feed/live": feed(att=41212),
        }
        w = self._widget(routes)
        with (
            patcher,
            caplog.at_level(logging.INFO, logger="led_ticker_baseball.attendance"),
        ):
            await w.update()
        assert any(
            r.levelno == logging.INFO and "attendance" in r.message.lower()
            for r in caplog.records
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_attendance.py -v`
Expected: TestUpdateLeague / TestUpdateTeam FAIL with `AttributeError: ... 'update'`

- [ ] **Step 3: Implement**

In `attendance.py`: change the datetime import to `from datetime import date, datetime, timedelta`; change typing to `from typing import Any, Self`; add `run_monitor_loop` and `spawn_tracked` to the plugin import; add `resolve_team_id` to the teams import. Add `import asyncio` to the stdlib imports. Below `logger`, add `_INTERVAL_THIRTY_MIN: int = 1800`.

Add the two pickers + start() + update() to `MLBAttendanceMonitor`:

```python
    def _pick_team_game(self, games: list[GameVenue]) -> GameVenue | None:
        """The tracked team's game for the day (doubleheader rule: Live first,
        else gameNumber 2 when both Final, else gameNumber 1)."""
        mine = [g for g in games if self.team in (g.home_abbr, g.away_abbr)]
        if not mine:
            return None
        live = [g for g in mine if g.state == "Live"]
        if live:
            return live[0]
        return max(mine, key=lambda g: g.game_number)

    async def _league_pairs(
        self, games: list[GameVenue]
    ) -> list[tuple[GameVenue, int]]:
        """Concurrent boxscore fetches for Final games; (game, attendance)
        pairs, skipping games with no announced attendance."""
        finals = [g for g in games if g.state == "Final"]
        atts = await asyncio.gather(*(self._fetch_attendance(g.game_pk) for g in finals))
        return [(g, a) for g, a in zip(finals, atts, strict=False) if a is not None]

    @classmethod
    async def start(
        cls,
        session: aiohttp.ClientSession,
        update_interval: int = _INTERVAL_THIRTY_MIN,
        **kwargs: Any,
    ) -> Self:
        logger.debug("MLBAttendanceMonitor.start")
        widget = cls(session=session, **kwargs)
        widget._tz = ZoneInfo(widget.timezone)
        if widget.team:
            widget.team = widget.team.upper()
            widget._team_id = await resolve_team_id(session, widget.team) or 0
        await widget.update()
        logger.info("MLB Attendance: %d stories", len(widget.feed_stories))
        spawn_tracked(run_monitor_loop(widget, update_interval))
        return widget

    async def update(self) -> None:
        """Re-derive attendance (schedule-gated); league or team mode."""
        tz = self._tz or ZoneInfo(self.timezone)
        today = datetime.now(tz).date()
        self._set_title()

        games, counts = await self._fetch_schedule(today)
        if self._should_skip(today, counts):
            logger.debug("MLB Attendance: gate skip")
            return

        try:
            if self.team:
                await self._update_team(today, games)
            else:
                await self._update_league(today, games)
        except Exception:
            logger.exception("MLB Attendance fetch/derive error")
            self._last_derive = None
            self._set_error_state()
            return

        if counts is not None:
            self._last_derive = (today, counts[1])

    async def _update_league(self, today: date, games: list[GameVenue] | None) -> None:
        pairs = await self._league_pairs(games or [])
        label = "Today"
        if not pairs:
            yest = today - timedelta(days=1)
            ygames, _ = await self._fetch_schedule(yest)
            pairs = await self._league_pairs(ygames or [])
            label = yest.strftime("%-m/%-d")
        if not pairs:
            self._last_derive = None
            await self._set_no_games_state(today)
            return
        records = _derive_superlatives(pairs, self.stats)
        self.feed_stories = self._build_league_stories(records, label)
        logger.info("MLB Attendance updated: %d stories (%s)", len(self.feed_stories), label)

    async def _update_team(self, today: date, games: list[GameVenue] | None) -> None:
        game = self._pick_team_game(games or [])
        label = ""
        if game is None:
            yest = today - timedelta(days=1)
            ygames, _ = await self._fetch_schedule(yest)
            game = self._pick_team_game(ygames or [])
            label = yest.strftime("%-m/%-d")
        if game is None:
            self._last_derive = None
            await self._set_no_games_state(today)
            return
        att, weather, venue, cap = await self._fetch_game_data(game.game_pk)
        self.feed_stories = [
            self._build_team_line(
                venue=venue or game.venue,
                attendance=att,
                capacity=cap or game.capacity,
                weather=weather,
                day_label=label,
            )
        ]
        logger.info("MLB Attendance updated: team %s (%s)", self.team, label or "today")
```

(`start()` is untested-by-convention for behavior but gets a wiring test in Task 11-adjacent style — see Task 10's note. Actually start() IS tested below per the #11 convention; the team/league wiring is covered there.)

Wait — start() test belongs with the others. Add the start() tests in this task's test block:

Append to `tests/test_attendance.py`:

```python
class TestStart:
    async def test_league_mode_spawns_loop(self):
        import led_ticker_baseball.attendance as mod
        from led_ticker_baseball.attendance import MLBAttendanceMonitor

        session = make_session({"hydrate=venue(fieldInfo),team": schedule()})
        spawn = mock.Mock()
        loop = mock.Mock(return_value="LOOP")
        with (
            mock.patch.object(mod, "spawn_tracked", spawn),
            mock.patch.object(mod, "run_monitor_loop", loop),
        ):
            w = await MLBAttendanceMonitor.start(session, update_interval=55)
        assert isinstance(w, MLBAttendanceMonitor)
        assert w._tz is not None
        assert w._team_id == 0  # league mode: no resolution
        assert w.feed_stories
        loop.assert_called_once_with(w, 55)
        spawn.assert_called_once_with("LOOP")

    async def test_team_mode_resolves_id(self):
        import led_ticker_baseball.attendance as mod
        from led_ticker_baseball.attendance import MLBAttendanceMonitor

        routes = {
            "/teams": {"teams": [{"id": 141, "abbreviation": "TOR"}]},
            "hydrate=venue(fieldInfo),team": schedule(),
            "startDate": {"dates": []},
        }
        session = make_session(routes)
        spawn = mock.Mock()
        loop = mock.Mock(return_value="LOOP")
        with (
            mock.patch.object(mod, "spawn_tracked", spawn),
            mock.patch.object(mod, "run_monitor_loop", loop),
        ):
            w = await MLBAttendanceMonitor.start(session, team="tor", update_interval=55)
        assert w.team == "TOR"
        assert w._team_id == 141
        spawn.assert_called_once_with("LOOP")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_attendance.py -v`
Expected: all PASS

- [ ] **Step 5: Run full gates and commit**

```bash
uv run pytest -q && uv run ruff check src tests && uv run ruff format --check src tests && uv run pyright src
git add src/led_ticker_baseball/attendance.py tests/test_attendance.py
git commit -m "feat: attendance update() flow (both modes) + start()"
```

---

### Task 10: validate_config

**Files:**
- Modify: `src/led_ticker_baseball/attendance.py`
- Modify: `tests/test_attendance.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_attendance.py`:

```python
class TestValidateConfig:
    def _v(self, cfg):
        from led_ticker_baseball.attendance import MLBAttendanceMonitor

        return MLBAttendanceMonitor.validate_config(cfg)

    def test_empty_passes(self):
        assert self._v({}) == []

    def test_team_only_passes(self):
        assert self._v({"team": "TOR"}) == []

    def test_league_stats_pass(self):
        assert self._v({"stats": ["fullest", "emptiest"]}) == []

    def test_non_string_team_rejected(self):
        msgs = self._v({"team": 42})
        assert len(msgs) == 1
        assert "team" in msgs[0]

    def test_unknown_stat_named(self):
        msgs = self._v({"stats": ["fullest", "rowdiest"]})
        assert len(msgs) == 1
        assert "rowdiest" in msgs[0]
        assert "fullest" in msgs[0]  # valid keys listed

    def test_non_list_stats_rejected(self):
        msgs = self._v({"stats": "fullest"})
        assert len(msgs) == 1
        assert "stats" in msgs[0]

    def test_stats_with_team_warns(self):
        msgs = self._v({"team": "TOR", "stats": ["fullest"]})
        assert len(msgs) == 1
        assert "ignored" in msgs[0].lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_attendance.py -v`
Expected: TestValidateConfig FAIL with `AttributeError: ... 'validate_config'`

- [ ] **Step 3: Implement**

Add to `MLBAttendanceMonitor`, directly above `start()`:

```python
    @classmethod
    def validate_config(cls, cfg: dict[str, Any]) -> list[str]:
        """Pre-coercion config check (returns messages, never raises). Same
        contract as the sibling widgets."""
        msgs: list[str] = []

        team = cfg.get("team")
        if team is not None and not isinstance(team, str):
            msgs.append(f"attendance team={team!r} must be a string abbreviation.")

        stats = cfg.get("stats")
        if stats is not None:
            if not isinstance(stats, list) or not all(isinstance(s, str) for s in stats):
                msgs.append(
                    f"attendance stats={stats!r} must be a list of strings, "
                    f'e.g. stats = ["biggest_crowd"].'
                )
            else:
                bad = [s for s in stats if s not in _STAT_KEYS]
                if bad:
                    names = ", ".join(repr(s) for s in bad)
                    valid = ", ".join(repr(k) for k in _STAT_KEYS)
                    msgs.append(
                        f"attendance stats contains unknown key(s) {names}. "
                        f"Valid keys: {valid}."
                    )
            if isinstance(team, str) and team:
                msgs.append(
                    "attendance stats is ignored when team is set "
                    "(stats applies to league mode only)."
                )

        return msgs
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_attendance.py -v`
Expected: all PASS

- [ ] **Step 5: Run full gates and commit**

```bash
uv run pytest -q && uv run ruff check src tests && uv run ruff format --check src tests && uv run pyright src
git add src/led_ticker_baseball/attendance.py tests/test_attendance.py
git commit -m "feat: attendance validate_config guardrails"
```

---

### Task 11: Register the widget + smoke test

**Files:**
- Modify: `src/led_ticker_baseball/__init__.py`
- Modify: `tests/test_smoke.py`

- [ ] **Step 1: Write the failing test change**

In `tests/test_smoke.py`, add alongside the existing widget assertions:

```python
        assert get_widget_class("baseball.attendance") is not None
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_smoke.py -v`
Expected: FAIL (baseball.attendance not registered)

- [ ] **Step 3: Register**

In `src/led_ticker_baseball/__init__.py`:

(a) Add the import in isort order (alphabetical: `attendance` sorts before `emoji`/`promotions`/`scores`/`standings`/`statcast`/`transition`):

```python
from led_ticker_baseball.attendance import MLBAttendanceMonitor
```

(b) In `register()`, add (group with the other widgets; place it first or after statcast — order is cosmetic, but put it after statcast for readability):

```python
    api.widget("attendance")(MLBAttendanceMonitor)
```

(c) Extend the module docstring's widget list to include `"baseball.attendance"`.

- [ ] **Step 4: Run the full suite**

Run: `uv run pytest -q`
Expected: all PASS (smoke + import purity now cover the new module)

- [ ] **Step 5: Run full gates and commit**

```bash
uv run ruff check src tests && uv run ruff format --check src tests && uv run pyright src
git add src/led_ticker_baseball/__init__.py tests/test_smoke.py
git commit -m "feat: register baseball.attendance widget"
```

---

### Task 12: Docs + final verification

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: README widget section**

Add after the `baseball.statcast` section (mirror its heading level/table style; verify defaults against `attendance.py` before writing):

````markdown
### `baseball.attendance`

Ballpark attendance and conditions. Two modes, chosen by whether you set a
`team`:

- **League-wide** (no `team`): the day's attendance superlatives —
  `Today · Biggest crowd 45,123 — Dodger Stadium`, plus smallest crowd and
  fullest/emptiest park by capacity %. Venue name in the home team's brand
  color.
- **Team** (`team` set): that team's game —
  `TOR · Rogers Centre 41,212 (90%) · 72° Clear, wind 5 mph In From CF`.
  Attendance and fill % appear once the game is final; venue and weather show
  before that.

```toml
[[playlist.section.widget]]
type = "baseball.attendance"
# team = "TOR"   # set for team mode; omit for league-wide
```

**No required fields** — everything is optional tuning.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `team` | string | unset | Set → that team's game; omit → league-wide superlatives. |
| `stats` | list of strings | all four | League mode only, in display order: `"biggest_crowd"`, `"smallest_crowd"`, `"fullest"`, `"emptiest"`. |
| `update_interval` | int | `1800` | Seconds between refreshes (30 min). A ~47 KB schedule check skips the per-game fetches when nothing changed. |
| `title` | string | `"Attendance"` | Section title override. |
| `timezone` | string | `"America/New_York"` | IANA timezone for "Today" / day rollover. |
| `padding` | int | `6` | Horizontal padding (logical px) after each message. |
| `bg_color` | RGB list | none | Background fill behind all messages. |
| `font_color` | RGB list / string / table | unset | RGB list tints body text; the day label, amber value, and venue/team color keep their callout colors. A string/table provider overrides all text. |
| `font` | string | `"6x12"` | Display font. Hires name needs `font_size`. |

Fill % is omitted when a venue lists no capacity (spring sites). With nothing
final yet, the widget shows yesterday's data (short-date labeled, e.g.
`6/12 · …`); with no games at all it shows `Next game: Jun 20` (team) /
`No games soon`; a fetch failure shows `No Data`.
````

Also update the post-install summary sentence to include `baseball.attendance`.

- [ ] **Step 2: CLAUDE.md updates**

- Overview bullet list, after the statcast bullet:

```markdown
- `baseball.attendance` — ballpark attendance: league-wide daily superlatives
  (biggest/smallest crowd, fullest/emptiest park) or one team's game
  (attendance + fill % + venue + weather); schedule-gated.
```

- Package layout block, after `statcast.py` (align the `#` column):

```
  attendance.py   # baseball.attendance widget (MLBAttendanceMonitor); league superlatives + team mode; schedule-gated
```

- `register()` snippet: add `api.widget("attendance")(MLBAttendanceMonitor)` matching `__init__.py`.
- Tests/CI section: add `test_attendance.py` to the behavior+rendering coverage line.
- Bump the "All four widget modules import the shared tables from teams.py" sentence to "All five widget modules…".

- [ ] **Step 3: Final verification — all gates plus coverage**

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run pyright src
uv run pytest -q
uv run pytest --cov=src --cov-report=term-missing
```

Expected: lint/format/pyright clean; suite green; coverage ≥ 90% overall; `attendance.py` high (the `start()` body is covered by Task 9's wiring tests).

- [ ] **Step 4: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: baseball.attendance README section + CLAUDE.md file map"
```

---

## Spec coverage self-check (for the reviewer)

- Data sources, URLs, hydrate string, boxscore parse → Tasks 1, 7
- GameVenue / schedule parse, capacity-0 handling → Task 2
- Superlative derivation (4 keys, tie, pct skips no-capacity) → Task 3
- Widget skeleton, gate, title, colors → Task 4
- League line format (grey/amber/venue-brand), stats order → Task 5
- Team line (final/pre-game, capacity-missing, weather, yesterday prefix, doubleheader) → Tasks 6, 9
- Fetchers (schedule gate counts, boxscore, feed), raise contract → Task 7
- Error + probe (team "Next game" vs league "Next games"), short-date → Task 8
- update() both modes + yesterday fallback + start() (two modes) → Task 9
- validate_config (team type, stats list/keys, stats+team warning) → Task 10
- registration + smoke + import purity → Task 11
- README (source of truth) + CLAUDE.md → Task 12
