# baseball.statcast Widget Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A league-wide `baseball.statcast` widget showing the day's Statcast superlatives (longest HR, hardest-hit ball, fastest/slowest pitch), re-derived through the day from Baseball Savant's day CSV with a StatsAPI schedule gate.

**Architecture:** New `MLBStatcastMonitor` in `src/led_ticker_baseball/statcast.py`, mirroring `promotions.py`'s monitor shape (attrs class, `start()`/`update()`, title-first setter contract, `run_monitor_loop`). Stateless re-derive: each refresh pulls the full day CSV (~3 MB) and recomputes; a ~10 KB schedule check skips the pull when no game is live and no game newly final. Spec: `docs/superpowers/specs/2026-06-11-statcast-widget-design.md`.

**Tech Stack:** Python 3.14, attrs, aiohttp, stdlib `csv`, pytest (`asyncio_mode = "auto"`), uv, ruff (E/F/I/UP/B/SIM + format), pyright, coverage ≥90%. Core imports ONLY from `led_ticker.plugin`. NO `from __future__ import annotations`.

**Branch discipline:** work on `statcast-widget` only; never checkout/switch branches; never commit to main.

**Gates — run all four before EVERY commit** (run `uv run ruff format src tests` first if the check fails):

```bash
uv run pytest -q
uv run ruff check src tests
uv run ruff format --check src tests
uv run pyright src
```

**Imports grow per task** so ruff's unused-import check stays green at every commit; each task lists its additions. Do not add imports a task's code doesn't use yet.

**File map:**

- Create: `src/led_ticker_baseball/statcast.py`
- Create: `tests/test_statcast.py`
- Modify: `src/led_ticker_baseball/__init__.py` (register widget)
- Modify: `tests/test_smoke.py` (assert registration)
- Modify: `README.md`, `CLAUDE.md` (docs)

---

### Task 1: Pure helpers + record derivation

**Files:**
- Create: `src/led_ticker_baseball/statcast.py`
- Create: `tests/test_statcast.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_statcast.py` (no imports yet — this task's tests need none; later tasks add `datetime as dt`, `logging`, `unittest.mock as mock`, and `ZoneInfo` as they become needed, keeping ruff's unused-import check green at every commit):

```python
"""Tests for the MLB league-wide Statcast superlatives widget."""


def row(**kwargs):
    """A Savant-shaped row dict; only the columns the code reads."""
    base = {
        "events": "",
        "description": "",
        "release_speed": "",
        "launch_speed": "",
        "hit_distance_sc": "",
        "pitch_name": "",
        "batter": "1",
        "pitcher": "2",
        "home_team": "PHI",
        "away_team": "TOR",
        "inning_topbot": "Top",
    }
    base.update({k: str(v) for k, v in kwargs.items()})
    return base


def hr(dist, batter=10, **kwargs):
    return row(
        events="home_run",
        description="hit_into_play",
        hit_distance_sc=dist,
        launch_speed=100.0,
        release_speed=95.0,
        batter=batter,
        **kwargs,
    )


class TestRowHelpers:
    def test_to_float_parses(self):
        from led_ticker_baseball.statcast import _to_float

        assert _to_float({"x": "101.8"}, "x") == 101.8

    def test_to_float_blank_and_garbage_are_none(self):
        from led_ticker_baseball.statcast import _to_float

        assert _to_float({"x": ""}, "x") is None
        assert _to_float({"x": "null"}, "x") is None
        assert _to_float({}, "x") is None

    def test_to_id(self):
        from led_ticker_baseball.statcast import _to_id

        assert _to_id({"batter": "660271"}, "batter") == 660271
        assert _to_id({"batter": ""}, "batter") == 0
        assert _to_id({}, "batter") == 0

    def test_row_team_batter_top_is_away(self):
        from led_ticker_baseball.statcast import _row_team

        r = row(inning_topbot="Top")
        assert _row_team(r, "batter") == "TOR"
        assert _row_team(r, "pitcher") == "PHI"

    def test_row_team_batter_bottom_is_home(self):
        from led_ticker_baseball.statcast import _row_team

        r = row(inning_topbot="Bot")
        assert _row_team(r, "batter") == "PHI"
        assert _row_team(r, "pitcher") == "TOR"

    def test_format_value(self):
        from led_ticker_baseball.statcast import _format_value

        assert _format_value("longest_hr", 463.0) == "463 ft"
        assert _format_value("fastest_pitch", 101.84) == "101.8 mph"
        assert _format_value("hardest_hit", 113.4) == "113.4 mph"


class TestDeriveRecords:
    def _derive(self, rows, stats=None):
        from led_ticker_baseball.statcast import _STAT_KEYS, _derive_records

        return _derive_records(rows, list(stats or _STAT_KEYS))

    def test_longest_hr_takes_max_distance(self):
        records = self._derive([hr(415, batter=10), hr(463, batter=11)])
        rec = records["longest_hr"]
        assert rec.value == 463.0
        assert rec.person_id == 11

    def test_hardest_hit_only_counts_balls_in_play(self):
        rows = [
            row(description="hit_into_play", launch_speed=113.4, batter=20),
            row(description="foul", launch_speed=119.9, batter=21),
        ]
        assert self._derive(rows)["hardest_hit"].person_id == 20

    def test_pitch_records_use_pitcher_attribution(self):
        rows = [
            row(release_speed=101.8, pitcher=30, inning_topbot="Top"),
            row(release_speed=69.6, pitcher=31, pitch_name="Slow Curve"),
        ]
        records = self._derive(rows)
        fast, slow = records["fastest_pitch"], records["slowest_pitch"]
        assert (fast.person_id, fast.team_abbr) == (30, "PHI")
        assert slow.value == 69.6
        assert slow.pitch_name == "Slow Curve"

    def test_tie_keeps_first_row(self):
        records = self._derive([hr(440, batter=10), hr(440, batter=11)])
        assert records["longest_hr"].person_id == 10

    def test_missing_values_skipped(self):
        records = self._derive([row(events="home_run", hit_distance_sc="")])
        assert "longest_hr" not in records

    def test_unrequested_stats_not_derived(self):
        records = self._derive([hr(440)], stats=["fastest_pitch"])
        assert set(records) == {"fastest_pitch"}

    def test_empty_rows_empty_records(self):
        assert self._derive([]) == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_statcast.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'led_ticker_baseball.statcast'`

- [ ] **Step 3: Create the module**

Create `src/led_ticker_baseball/statcast.py`:

```python
"""MLB league-wide Statcast superlatives widget.

Derives the day's longest home run, hardest-hit ball, and fastest/slowest
pitch from Baseball Savant's day CSV — an undocumented website endpoint, so
requests carry a User-Agent and the default refresh is a polite 30 minutes,
gated on the (tiny) StatsAPI day schedule so off-hours refreshes skip the
3 MB pull. Stateless: every refresh re-derives from the full day so far.
"""

import logging
from dataclasses import dataclass
from typing import Any

logger: logging.Logger = logging.getLogger(__name__)

_STAT_KEYS: tuple[str, ...] = (
    "longest_hr",
    "hardest_hit",
    "fastest_pitch",
    "slowest_pitch",
)

_STAT_LABELS: dict[str, str] = {
    "longest_hr": "Longest HR",
    "hardest_hit": "Hardest hit",
    "fastest_pitch": "Fastest pitch",
    "slowest_pitch": "Slowest pitch",
}


def _to_float(row: dict[str, Any], key: str) -> float | None:
    """Float column value; None when missing, blank, or malformed."""
    try:
        return float(row.get(key) or "")
    except ValueError:
        return None


def _to_id(row: dict[str, Any], key: str) -> int:
    """Person-ID column value; 0 when missing or malformed."""
    try:
        return int(row.get(key) or 0)
    except ValueError:
        return 0


def _row_team(row: dict[str, Any], who: str) -> str:
    """Team abbreviation for ``who`` ('batter' / 'pitcher') on this row.

    Savant rows carry only home_team/away_team; ``inning_topbot`` says who is
    batting (Top = away batting). The batter's team follows topbot; the
    pitcher's team is the other one.
    """
    batting_away = row.get("inning_topbot") == "Top"
    if who == "batter":
        team = row.get("away_team") if batting_away else row.get("home_team")
    else:
        team = row.get("home_team") if batting_away else row.get("away_team")
    return team or ""


def _format_value(key: str, value: float) -> str:
    """'463 ft' for the HR distance, '101.8 mph' for speeds."""
    if key == "longest_hr":
        return f"{round(value)} ft"
    return f"{value:.1f} mph"


@dataclass
class StatRecord:
    value: float
    person_id: int
    team_abbr: str
    pitch_name: str = ""


def _derive_records(
    rows: list[dict[str, Any]], stats: list[str]
) -> dict[str, StatRecord]:
    """One pass over Savant rows → best record per requested stat key.

    Strict comparisons keep the first row on ties (CSV order). Rows missing
    the relevant value are skipped.
    """
    records: dict[str, StatRecord] = {}

    def consider(
        key: str,
        r: dict[str, Any],
        value: float | None,
        who: str,
        *,
        lower: bool = False,
    ) -> None:
        if value is None:
            return
        cur = records.get(key)
        if cur is not None and (value >= cur.value if lower else value <= cur.value):
            return
        records[key] = StatRecord(
            value=value,
            person_id=_to_id(r, who),
            team_abbr=_row_team(r, who),
            pitch_name=r.get("pitch_name") or "",
        )

    for r in rows:
        if "longest_hr" in stats and r.get("events") == "home_run":
            consider("longest_hr", r, _to_float(r, "hit_distance_sc"), "batter")
        if "hardest_hit" in stats and r.get("description") == "hit_into_play":
            consider("hardest_hit", r, _to_float(r, "launch_speed"), "batter")
        if "fastest_pitch" in stats:
            consider("fastest_pitch", r, _to_float(r, "release_speed"), "pitcher")
        if "slowest_pitch" in stats:
            consider(
                "slowest_pitch", r, _to_float(r, "release_speed"), "pitcher", lower=True
            )
    return records
```

Note: `_to_float({"x": "null"})` returns None because `float("null")` raises ValueError — no special-casing needed.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_statcast.py -v`
Expected: all PASS

- [ ] **Step 5: Run full gates and commit**

```bash
uv run pytest -q && uv run ruff check src tests && uv run ruff format --check src tests && uv run pyright src
git add src/led_ticker_baseball/statcast.py tests/test_statcast.py
git commit -m "feat: statcast row helpers + record derivation"
```

---

### Task 2: Widget skeleton, title, colors, gate decision

**Files:**
- Modify: `src/led_ticker_baseball/statcast.py`
- Modify: `tests/test_statcast.py`

- [ ] **Step 1: Write the failing tests**

Add to the imports at the top of `tests/test_statcast.py`:

```python
import datetime as dt
import unittest.mock as mock
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
```

Append:

```python
def make_widget(**kwargs):
    from led_ticker_baseball.statcast import MLBStatcastMonitor

    widget = MLBStatcastMonitor(session=kwargs.pop("session", mock.Mock()), **kwargs)
    widget._tz = NY
    return widget


TODAY = dt.date(2026, 6, 12)


class TestSkeleton:
    def test_default_stats_all_four_in_order(self):
        from led_ticker_baseball.statcast import _STAT_KEYS

        assert make_widget().stats == list(_STAT_KEYS)

    def test_default_title(self):
        widget = make_widget()
        widget._set_title()
        assert widget.feed_title.text == "Statcast"

    def test_title_override(self):
        widget = make_widget(title="Robot Numbers")
        widget._set_title()
        assert widget.feed_title.text == "Robot Numbers"

    def test_font_color_override_selected_for_body(self):
        from led_ticker.plugin import make_color

        c = make_color(255, 0, 0)
        widget = make_widget(font_color=c)
        assert widget._body_color() is c
        assert widget._plain_body_color() is c

    def test_default_body_color_is_white(self):
        from led_ticker.colors import RGB_WHITE

        widget = make_widget()
        assert widget._body_color() is RGB_WHITE
        assert widget._plain_body_color() is RGB_WHITE


class TestShouldSkip:
    def test_no_prior_derive_never_skips(self):
        assert make_widget()._should_skip(TODAY, (0, 5)) is False

    def test_gate_fetch_failure_fails_open(self):
        widget = make_widget()
        widget._last_derive = (TODAY, 5)
        assert widget._should_skip(TODAY, None) is False

    def test_skips_when_nothing_changed(self):
        widget = make_widget()
        widget._last_derive = (TODAY, 5)
        assert widget._should_skip(TODAY, (0, 5)) is True

    def test_live_game_forces_derive(self):
        widget = make_widget()
        widget._last_derive = (TODAY, 5)
        assert widget._should_skip(TODAY, (1, 5)) is False

    def test_new_final_forces_derive(self):
        widget = make_widget()
        widget._last_derive = (TODAY, 5)
        assert widget._should_skip(TODAY, (0, 6)) is False

    def test_date_rollover_forces_derive(self):
        widget = make_widget()
        widget._last_derive = (TODAY - dt.timedelta(days=1), 15)
        assert widget._should_skip(TODAY, (0, 15)) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_statcast.py -v`
Expected: new tests FAIL with `ImportError: cannot import name 'MLBStatcastMonitor'`; Task 1 tests pass.

- [ ] **Step 3: Implement**

In `src/led_ticker_baseball/statcast.py`, extend the import section to:

```python
import logging
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
class MLBStatcastMonitor:
    """League-wide daily Statcast superlatives."""

    session: aiohttp.ClientSession
    stats: list[str] = attrs.field(factory=lambda: list(_STAT_KEYS))
    title: str = "Statcast"
    timezone: str = "America/New_York"
    padding: int = 6
    hold_time: float = 0.0
    bg_color: Color | None = attrs.field(default=None, kw_only=True)
    font_color: Color | ColorProvider | None = attrs.field(default=None, kw_only=True)
    font: Font = attrs.field(default=FONT_DEFAULT, kw_only=True)
    _tz: ZoneInfo | None = attrs.field(init=False, default=None)
    # (local date, Final-game count) at the last successful derive; None
    # means no successful derive yet (first run, or the last update ended
    # in an error/fallback state).
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
        """Body-text color for per-segment use.

        A plain-Color ``font_color`` tints body text while callout segments
        (day label, amber value, team abbr) keep their colors. Providers
        (``color_for``) can't color a single segment; they pass through
        ``font_color=`` on the message instead, which overrides every
        segment in core — same as the sibling widgets.
        """
        if self.font_color is not None and not hasattr(self.font_color, "color_for"):
            return self.font_color
        return colors.RGB_WHITE

    def _set_title(self) -> None:
        """League-wide title; no team color (there is no team)."""
        self.feed_title = TickerMessage(
            self.title,
            font_color=self._body_color(),
            center=True,
            bg_color=self.bg_color,
        )

    def _should_skip(self, today: date, counts: tuple[int, int] | None) -> bool:
        """Skip the 3 MB pull when nothing changed since the last derive.

        Re-derive when: the gate fetch failed (fail open), no successful
        derive exists yet, the local date rolled over, any game is live, or
        the Final count moved.
        """
        if counts is None or self._last_derive is None:
            return False
        snap_day, snap_final = self._last_derive
        live, final = counts
        return snap_day == today and live == 0 and final == snap_final
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_statcast.py -v`
Expected: all PASS

- [ ] **Step 5: Run full gates and commit**

```bash
uv run pytest -q && uv run ruff check src tests && uv run ruff format --check src tests && uv run pyright src
git add src/led_ticker_baseball/statcast.py tests/test_statcast.py
git commit -m "feat: MLBStatcastMonitor skeleton + schedule-gate decision"
```

---

### Task 3: Story building

**Files:**
- Modify: `src/led_ticker_baseball/statcast.py`
- Modify: `tests/test_statcast.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_statcast.py`:

```python
def rec(value, person_id=10, team="TOR", pitch_name=""):
    from led_ticker_baseball.statcast import StatRecord

    return StatRecord(
        value=value, person_id=person_id, team_abbr=team, pitch_name=pitch_name
    )


def line_text(story):
    """Full visible text of a segment story line."""
    return "".join(seg[0] for seg in story.segments)


class TestBuildStatStories:
    def test_line_format_and_order(self):
        widget = make_widget()
        records = {
            "longest_hr": rec(463, person_id=10),
            "fastest_pitch": rec(101.8, person_id=30, team="MIL"),
        }
        stories = widget._build_stat_stories(records, "Today", {10: "Butler", 30: "Misiorowski"})
        assert line_text(stories[0]) == "Today · Longest HR 463 ft — Butler TOR"
        assert line_text(stories[1]) == "Today · Fastest pitch 101.8 mph — Misiorowski MIL"

    def test_stats_config_order_controls_display_order(self):
        widget = make_widget(stats=["fastest_pitch", "longest_hr"])
        records = {"longest_hr": rec(463), "fastest_pitch": rec(101.8)}
        stories = widget._build_stat_stories(records, "Today", {})
        assert "Fastest pitch" in line_text(stories[0])
        assert "Longest HR" in line_text(stories[1])

    def test_missing_stat_omits_line(self):
        widget = make_widget()
        stories = widget._build_stat_stories({"longest_hr": rec(463)}, "Today", {})
        assert len(stories) == 1

    def test_slowest_pitch_appends_pitch_name(self):
        widget = make_widget(stats=["slowest_pitch"])
        records = {"slowest_pitch": rec(69.6, person_id=31, team="KC", pitch_name="Slow Curve")}
        stories = widget._build_stat_stories(records, "Today", {31: "Pederson"})
        assert line_text(stories[0]) == (
            "Today · Slowest pitch 69.6 mph (Slow Curve) — Pederson KC"
        )

    def test_fastest_pitch_never_appends_pitch_name(self):
        widget = make_widget(stats=["fastest_pitch"])
        records = {"fastest_pitch": rec(101.8, pitch_name="4-Seam Fastball")}
        stories = widget._build_stat_stories(records, "Today", {})
        assert "4-Seam" not in line_text(stories[0])

    def test_unresolved_name_drops_name_keeps_team(self):
        widget = make_widget(stats=["longest_hr"])
        stories = widget._build_stat_stories({"longest_hr": rec(463)}, "Yest", {})
        assert line_text(stories[0]) == "Yest · Longest HR 463 ft — TOR"

    def test_colors_day_grey_value_amber_team_branded(self):
        from led_ticker.colors import RGB_WHITE

        widget = make_widget(stats=["longest_hr"])
        stories = widget._build_stat_stories(
            {"longest_hr": rec(463)}, "Today", {10: "Butler"}
        )
        segs = stories[0].segments
        day_c, value_c, team_c = segs[0][1], segs[2][1], segs[-1][1]
        assert (day_c.red, day_c.green, day_c.blue) == (150, 150, 150)
        assert (value_c.red, value_c.green, value_c.blue) == (255, 200, 60)
        assert team_c is not RGB_WHITE  # TOR brand color

    def test_plain_font_color_tints_body_not_callouts(self):
        from led_ticker.plugin import make_color

        c = make_color(0, 255, 0)
        widget = make_widget(stats=["longest_hr"], font_color=c)
        stories = widget._build_stat_stories(
            {"longest_hr": rec(463)}, "Today", {10: "Butler"}
        )
        segs = stories[0].segments
        assert segs[1][1] is c  # "Longest HR " label
        assert segs[3][1] is c  # " — Butler "
        assert (segs[2][1].red, segs[2][1].green, segs[2][1].blue) == (255, 200, 60)

    def test_stories_centered(self):
        widget = make_widget(stats=["longest_hr"])
        stories = widget._build_stat_stories({"longest_hr": rec(463)}, "Today", {})
        assert stories[0].center is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_statcast.py -v`
Expected: TestBuildStatStories FAIL with `AttributeError: ... '_build_stat_stories'`

- [ ] **Step 3: Implement**

In `statcast.py`: add `make_color` to the `led_ticker.plugin` import block, and add below it:

```python
from led_ticker_baseball.teams import _team_color
```

Add this method to `MLBStatcastMonitor` (after `_should_skip`):

```python
    def _build_stat_stories(
        self,
        records: dict[str, StatRecord],
        day_label: str,
        names: dict[int, str],
    ) -> list[TickerMessage | SegmentMessage]:
        """One centered line per stat: 'Today · Longest HR 463 ft — Butler ATH'.

        Lines are self-contained (day label, stat, value, record holder, team
        abbr in brand color) — stories scroll independently of the title.
        ``self.stats`` order is display order; stats with no record are
        omitted; an unresolved name degrades to value + team abbr.
        """
        grey = make_color(150, 150, 150)  # grey — day label
        amber = make_color(255, 200, 60)  # amber — the record value
        body_c = self._plain_body_color()

        stories: list[TickerMessage | SegmentMessage] = []
        for key in self.stats:
            record = records.get(key)
            if record is None:
                continue
            segments: list[tuple[str, Any]] = [
                (f"{day_label} · ", grey),
                (f"{_STAT_LABELS[key]} ", body_c),
                (_format_value(key, record.value), amber),
            ]
            if key == "slowest_pitch" and record.pitch_name:
                segments.append((f" ({record.pitch_name})", body_c))
            name = names.get(record.person_id, "")
            segments.append((f" — {name} " if name else " — ", body_c))
            segments.append((record.team_abbr, _team_color(record.team_abbr)))
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

Run: `uv run pytest tests/test_statcast.py -v`
Expected: all PASS

- [ ] **Step 5: Run full gates and commit**

```bash
uv run pytest -q && uv run ruff check src tests && uv run ruff format --check src tests && uv run pyright src
git add src/led_ticker_baseball/statcast.py tests/test_statcast.py
git commit -m "feat: statcast superlative story lines"
```

---

### Task 4: Async fetchers (schedule counts, day CSV, names)

**Files:**
- Modify: `src/led_ticker_baseball/statcast.py`
- Modify: `tests/test_statcast.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_statcast.py`:

```python
def _ctx(payload):
    """Async-context response mock: str payloads serve .text(), dicts .json()."""
    resp = mock.AsyncMock()
    if isinstance(payload, str):
        resp.text.return_value = payload
    else:
        resp.json.return_value = payload
    ctx = mock.AsyncMock()
    ctx.__aenter__.return_value = resp
    return ctx


def make_session(routes):
    """Mock aiohttp session routing by URL substring; first match wins."""
    session = mock.MagicMock()

    def side_effect(url, *args, **kwargs):
        for key, payload in routes.items():
            if key in url:
                return _ctx(payload)
        return _ctx({})

    session.get.side_effect = side_effect
    return session


_CSV_COLS = [
    "release_speed",
    "batter",
    "pitcher",
    "events",
    "description",
    "home_team",
    "away_team",
    "inning_topbot",
    "launch_speed",
    "hit_distance_sc",
    "pitch_name",
]


def make_csv(*rows):
    """Savant-shaped CSV text, BOM included like the real endpoint."""
    lines = [",".join(_CSV_COLS)]
    for r in rows:
        lines.append(",".join(str(r.get(c, "")) for c in _CSV_COLS))
    return "\ufeff" + "\n".join(lines) + "\n"


def sched_game(state):
    return {"status": {"abstractGameState": state}}


class TestFetchScheduleCounts:
    async def test_counts_live_and_final(self):
        session = make_session(
            {
                "sportId=1&date=": {
                    "dates": [
                        {
                            "games": [
                                sched_game("Live"),
                                sched_game("Final"),
                                sched_game("Final"),
                                sched_game("Preview"),
                            ]
                        }
                    ]
                }
            }
        )
        widget = make_widget(session=session)
        assert await widget._fetch_schedule_counts(TODAY) == (1, 2)

    async def test_failure_returns_none(self):
        session = mock.MagicMock()
        session.get.side_effect = RuntimeError("network down")
        widget = make_widget(session=session)
        assert await widget._fetch_schedule_counts(TODAY) is None


class TestDeriveDay:
    async def test_parses_bom_csv_and_derives(self):
        csv_text = make_csv(hr(463, batter=11), row(release_speed=101.8, pitcher=30))
        session = make_session({"statcast_search": csv_text})
        widget = make_widget(session=session)
        records = await widget._derive_day(TODAY)
        assert records["longest_hr"].value == 463.0
        assert records["fastest_pitch"].person_id == 30

    async def test_sends_user_agent(self):
        session = make_session({"statcast_search": make_csv()})
        widget = make_widget(session=session)
        await widget._derive_day(TODAY)
        savant_calls = [
            c for c in session.get.call_args_list if "statcast_search" in c.args[0]
        ]
        ua = savant_calls[0].kwargs["headers"]["User-Agent"]
        assert ua.startswith("led-ticker-baseball")

    async def test_requests_the_given_day(self):
        session = make_session({"statcast_search": make_csv()})
        widget = make_widget(session=session)
        await widget._derive_day(dt.date(2026, 6, 11))
        url = session.get.call_args_list[0].args[0]
        assert "game_date_gt=2026-06-11" in url
        assert "game_date_lt=2026-06-11" in url


class TestResolveNames:
    async def test_resolves_last_names(self):
        session = make_session(
            {
                "/people": {
                    "people": [
                        {"id": 10, "lastName": "Butler"},
                        {"id": 30, "lastName": "Misiorowski"},
                    ]
                }
            }
        )
        widget = make_widget(session=session)
        assert await widget._resolve_names({10, 30}) == {
            10: "Butler",
            30: "Misiorowski",
        }

    async def test_empty_ids_no_request(self):
        session = make_session({})
        widget = make_widget(session=session)
        assert await widget._resolve_names({0}) == {}
        session.get.assert_not_called()

    async def test_failure_returns_empty(self):
        session = mock.MagicMock()
        session.get.side_effect = RuntimeError("network down")
        widget = make_widget(session=session)
        assert await widget._resolve_names({10}) == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_statcast.py -v`
Expected: new tests FAIL with `AttributeError` on the three methods.

- [ ] **Step 3: Implement**

In `statcast.py`: add `import csv` and `import io` to the stdlib imports, and add the teams import for `MLB_API` (the block becomes `from led_ticker_baseball.teams import MLB_API, _team_color`). Below `logger`, add:

```python
SAVANT_CSV_URL: str = (
    "https://baseballsavant.mlb.com/statcast_search/csv"
    "?all=true&type=details&game_date_gt={day}&game_date_lt={day}"
)
_USER_AGENT: str = (
    "led-ticker-baseball (+https://github.com/JamesAwesome/led-ticker-baseball)"
)
```

Add these methods to `MLBStatcastMonitor` (after `_should_skip`):

```python
    async def _fetch_schedule_counts(self, day: date) -> tuple[int, int] | None:
        """(live, final) game counts for the day; None on failure (fail open)."""
        url = f"{MLB_API}/schedule?sportId=1&date={day.isoformat()}"
        try:
            async with self.session.get(url) as resp:
                data = await resp.json()
        except Exception:
            logger.debug("MLB Statcast schedule gate fetch failed")
            return None
        live = final = 0
        for date_entry in data.get("dates", []):
            for g in date_entry.get("games", []):
                state = g.get("status", {}).get("abstractGameState")
                live += state == "Live"
                final += state == "Final"
        return live, final

    async def _derive_day(self, day: date) -> dict[str, StatRecord]:
        """Fetch the Savant day CSV and derive the requested records.

        Raises on fetch failure — the caller owns the error state. The CSV
        ships a UTF-8 BOM; strip it before DictReader sees the header row.
        """
        url = SAVANT_CSV_URL.format(day=day.isoformat())
        async with self.session.get(url, headers={"User-Agent": _USER_AGENT}) as resp:
            text = await resp.text()
        rows = list(csv.DictReader(io.StringIO(text.lstrip("\ufeff"))))
        return _derive_records(rows, self.stats)

    async def _resolve_names(self, person_ids: set[int]) -> dict[int, str]:
        """Batched StatsAPI lookup: person id → last name; {} on failure."""
        ids = sorted(i for i in person_ids if i)
        if not ids:
            return {}
        url = f"{MLB_API}/people?personIds={','.join(map(str, ids))}"
        try:
            async with self.session.get(url) as resp:
                data = await resp.json()
        except Exception:
            logger.debug("MLB Statcast name lookup failed")
            return {}
        return {
            p["id"]: p.get("lastName", "")
            for p in data.get("people", [])
            if p.get("id")
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_statcast.py -v`
Expected: all PASS

- [ ] **Step 5: Run full gates and commit**

```bash
uv run pytest -q && uv run ruff check src tests && uv run ruff format --check src tests && uv run pyright src
git add src/led_ticker_baseball/statcast.py tests/test_statcast.py
git commit -m "feat: statcast savant fetch, schedule counts, name resolution"
```

---

### Task 5: Error + no-games fallback states

**Files:**
- Modify: `src/led_ticker_baseball/statcast.py`
- Modify: `tests/test_statcast.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_statcast.py`:

```python
class TestFallbackStates:
    def test_error_state(self):
        widget = make_widget()
        widget._set_error_state()
        assert widget.feed_stories[0].text == "No Data"

    async def test_no_games_probe_finds_next_date(self):
        session = make_session(
            {"startDate": {"dates": [{"date": "2027-03-26"}, {"date": "2027-03-27"}]}}
        )
        widget = make_widget(session=session)
        await widget._set_no_games_state(TODAY)
        assert widget.feed_stories[0].text == "Next games: Mar 26"

    async def test_no_games_probe_empty(self):
        session = make_session({"startDate": {"dates": []}})
        widget = make_widget(session=session)
        await widget._set_no_games_state(TODAY)
        assert widget.feed_stories[0].text == "No games soon"

    async def test_no_games_probe_failure_degrades(self):
        session = mock.MagicMock()
        session.get.side_effect = RuntimeError("network down")
        widget = make_widget(session=session)
        await widget._set_no_games_state(TODAY)
        assert widget.feed_stories[0].text == "No games soon"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_statcast.py -v`
Expected: TestFallbackStates FAIL with `AttributeError`.

- [ ] **Step 3: Implement**

In `statcast.py`: change the datetime import to `from datetime import date, timedelta`. Add to `MLBStatcastMonitor` (after `_build_stat_stories`):

```python
    # Contract for the state setters below: they manage feed_stories only.
    # update() calls _set_title() unconditionally before dispatching to any
    # of them, so feed_title is always set — including on error paths.

    def _set_error_state(self) -> None:
        """Set display to error state."""
        self.feed_stories = [
            TickerMessage(
                "No Data", font_color=self._body_color(), bg_color=self.bg_color
            ),
        ]
        logger.info(
            "MLB Statcast updated: %d stories (no data)", len(self.feed_stories)
        )

    async def _set_no_games_state(self, today: date) -> None:
        """Off-day / offseason: probe 30 days for the next league game date.

        Fallback lines are league-generic and self-explanatory, so they carry
        no team prefix. A failed probe degrades to 'No games soon' silently.
        """
        start = today.isoformat()
        end = (today + timedelta(days=30)).isoformat()
        url = (
            f"{MLB_API}/schedule?sportId=1&startDate={start}&endDate={end}&gameType=R"
        )
        data: dict[str, Any] = {}
        try:
            async with self.session.get(url) as resp:
                data = await resp.json()
        except Exception:
            logger.debug("MLB Statcast probe failed")
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
        if next_date is not None:
            text = f"Next games: {next_date.strftime('%b %-d')}"
        else:
            text = "No games soon"
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

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_statcast.py -v`
Expected: all PASS

- [ ] **Step 5: Run full gates and commit**

```bash
uv run pytest -q && uv run ruff check src tests && uv run ruff format --check src tests && uv run pyright src
git add src/led_ticker_baseball/statcast.py tests/test_statcast.py
git commit -m "feat: statcast error + no-games fallback states"
```

---

### Task 6: `update()` + `start()`

**Files:**
- Modify: `src/led_ticker_baseball/statcast.py`
- Modify: `tests/test_statcast.py`

- [ ] **Step 1: Write the failing tests**

Add `import logging` to the test-file imports. `update()` uses real wall-clock "today", so freeze it (same pattern as `test_promotions.py`) — fixtures and `update()` must agree on the date. Append:

```python
def _freeze_today():
    """(patcher, today) freezing statcast.datetime.now at the current time.

    The frozen mock wraps the real datetime so classmethods (fromisoformat)
    still work.
    """
    now = dt.datetime.now(NY)
    frozen = mock.Mock(wraps=dt.datetime)
    frozen.now.return_value = now
    patcher = mock.patch("led_ticker_baseball.statcast.datetime", frozen)
    return patcher, now.date()


PEOPLE = {"people": [{"id": 11, "lastName": "Butler"}]}
QUIET_SCHEDULE = {"dates": [{"games": [sched_game("Final")] * 3}]}


class TestUpdate:
    def _widget(self, routes, **kwargs):
        widget = make_widget(session=make_session(routes), **kwargs)
        widget._tz = NY
        return widget

    async def test_today_records_build_stories(self):
        patcher, today = _freeze_today()
        widget = self._widget(
            {
                "sportId=1&date=": QUIET_SCHEDULE,
                f"game_date_gt={today.isoformat()}": make_csv(hr(463, batter=11)),
                "/people": PEOPLE,
            },
            stats=["longest_hr"],
        )
        with patcher:
            await widget.update()
        assert line_text(widget.feed_stories[0]) == (
            "Today · Longest HR 463 ft — Butler TOR"
        )
        assert widget.feed_title is not None
        assert widget._last_derive == (today, 3)

    async def test_empty_today_falls_back_to_yesterday(self):
        patcher, today = _freeze_today()
        yest = today - dt.timedelta(days=1)
        widget = self._widget(
            {
                "sportId=1&date=": QUIET_SCHEDULE,
                f"game_date_gt={today.isoformat()}": make_csv(),
                f"game_date_gt={yest.isoformat()}": make_csv(hr(463, batter=11)),
                "/people": PEOPLE,
            },
            stats=["longest_hr"],
        )
        with patcher:
            await widget.update()
        assert line_text(widget.feed_stories[0]).startswith("Yest · ")

    async def test_both_days_empty_routes_to_no_games(self):
        patcher, today = _freeze_today()
        widget = self._widget(
            {
                "sportId=1&date=": {"dates": []},
                "statcast_search": make_csv(),
                "startDate": {"dates": []},
            }
        )
        with patcher:
            await widget.update()
        assert widget.feed_stories[0].text == "No games soon"
        assert widget._last_derive is None

    async def test_gate_skip_keeps_stories_and_skips_savant(self):
        patcher, today = _freeze_today()
        widget = self._widget({"sportId=1&date=": QUIET_SCHEDULE})
        widget._last_derive = (today, 3)
        sentinel = ["sentinel"]
        widget.feed_stories = sentinel
        with patcher:
            await widget.update()
        assert widget.feed_stories is sentinel
        savant_calls = [
            c for c in widget.session.get.call_args_list
            if "statcast_search" in c.args[0]
        ]
        assert savant_calls == []

    async def test_fetch_error_sets_no_data_and_clears_snapshot(self):
        patcher, today = _freeze_today()

        def side_effect(url, *args, **kwargs):
            if "statcast_search" in url:
                raise RuntimeError("savant down")
            return _ctx(QUIET_SCHEDULE)

        session = mock.MagicMock()
        session.get.side_effect = side_effect
        widget = make_widget(session=session)
        widget._tz = NY
        widget._last_derive = (today - dt.timedelta(days=1), 1)
        with patcher:
            await widget.update()
        assert widget.feed_stories[0].text == "No Data"
        assert widget._last_derive is None

    async def test_update_logs_info(self, caplog):
        patcher, today = _freeze_today()
        widget = self._widget(
            {
                "sportId=1&date=": QUIET_SCHEDULE,
                f"game_date_gt={today.isoformat()}": make_csv(hr(463, batter=11)),
                "/people": PEOPLE,
            },
            stats=["longest_hr"],
        )
        with (
            patcher,
            caplog.at_level(logging.INFO, logger="led_ticker_baseball.statcast"),
        ):
            await widget.update()
        matching = [
            r
            for r in caplog.records
            if r.levelno == logging.INFO and "statcast" in r.message.lower()
        ]
        assert matching, f"expected INFO log; got {[r.message for r in caplog.records]}"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_statcast.py -v`
Expected: TestUpdate FAIL with `AttributeError: ... 'update'`

- [ ] **Step 3: Implement**

In `statcast.py`: change the datetime import to `from datetime import date, datetime, timedelta`; change the typing import to `from typing import Any, Self`; add `run_monitor_loop` and `spawn_tracked` to the plugin import block. Below `logger`, add:

```python
_INTERVAL_THIRTY_MIN: int = 1800
```

Add to `MLBStatcastMonitor`, directly below the attrs fields (above `_body_color`):

```python
    @classmethod
    async def start(
        cls,
        session: aiohttp.ClientSession,
        update_interval: int = _INTERVAL_THIRTY_MIN,
        **kwargs: Any,
    ) -> Self:
        logger.debug("MLBStatcastMonitor.start")
        widget = cls(session=session, **kwargs)
        widget._tz = ZoneInfo(widget.timezone)
        await widget.update()
        logger.info("MLB Statcast: %d stories", len(widget.feed_stories))
        spawn_tracked(run_monitor_loop(widget, update_interval))
        return widget

    async def update(self) -> None:
        """Re-derive the day's superlatives (schedule-gated)."""
        tz = self._tz or ZoneInfo(self.timezone)
        today = datetime.now(tz).date()
        self._set_title()

        counts = await self._fetch_schedule_counts(today)
        if self._should_skip(today, counts):
            logger.debug("MLB Statcast: gate skip (no new game activity)")
            return

        try:
            records = await self._derive_day(today)
            label = "Today"
            if not records:
                records = await self._derive_day(today - timedelta(days=1))
                label = "Yest"
        except Exception:
            logger.exception("MLB Statcast fetch/derive error")
            self._last_derive = None
            self._set_error_state()
            return

        if not records:
            self._last_derive = None
            await self._set_no_games_state(today)
            return

        names = await self._resolve_names({r.person_id for r in records.values()})
        self.feed_stories = self._build_stat_stories(records, label, names)
        self._last_derive = (today, counts[1] if counts is not None else -1)
        logger.info(
            "MLB Statcast updated: %d stories (%s)", len(self.feed_stories), label
        )
```

(`counts[1] if counts is not None else -1`: a failed gate fetch stores Final = -1, which can never match a real count, so the next gate check re-derives — fail open carries forward. `start()` mirrors the untested-by-convention sibling `start()`s — do NOT add tests for it.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_statcast.py -v`
Expected: all PASS

- [ ] **Step 5: Run full gates and commit**

```bash
uv run pytest -q && uv run ruff check src tests && uv run ruff format --check src tests && uv run pyright src
git add src/led_ticker_baseball/statcast.py tests/test_statcast.py
git commit -m "feat: statcast update() flow + start() monitor loop"
```

---

### Task 7: `validate_config`

**Files:**
- Modify: `src/led_ticker_baseball/statcast.py`
- Modify: `tests/test_statcast.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_statcast.py`:

```python
class TestValidateConfig:
    def _validate(self, cfg):
        from led_ticker_baseball.statcast import MLBStatcastMonitor

        return MLBStatcastMonitor.validate_config(cfg)

    def test_clean_config_passes(self):
        assert self._validate({"stats": ["longest_hr", "fastest_pitch"]}) == []

    def test_stats_omitted_passes(self):
        assert self._validate({}) == []

    def test_unknown_key_named(self):
        msgs = self._validate({"stats": ["longest_hr", "biggest_yeet"]})
        assert len(msgs) == 1
        assert "biggest_yeet" in msgs[0]
        assert "longest_hr" in msgs[0]  # valid keys listed

    def test_non_list_stats_rejected(self):
        msgs = self._validate({"stats": "longest_hr"})
        assert len(msgs) == 1
        assert "stats" in msgs[0]

    def test_messages_returned_not_raised(self):
        assert isinstance(self._validate({"stats": 42}), list)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_statcast.py -v`
Expected: TestValidateConfig FAIL with `AttributeError: ... 'validate_config'`

- [ ] **Step 3: Implement**

Add to `MLBStatcastMonitor`, directly above `start()`:

```python
    @classmethod
    def validate_config(cls, cfg: dict[str, Any]) -> list[str]:
        """Pre-coercion config check, run by the engine via validate_widget_cfg.

        Returns message strings (does NOT raise); the engine turns any
        returned messages into a pre-flight ValueError. Same contract as the
        sibling widgets.
        """
        msgs: list[str] = []
        stats = cfg.get("stats")
        if stats is None:
            return msgs
        if not isinstance(stats, list) or not all(isinstance(s, str) for s in stats):
            msgs.append(
                f"statcast stats={stats!r} must be a list of strings, "
                f'e.g. stats = ["longest_hr"].'
            )
            return msgs
        bad = [s for s in stats if s not in _STAT_KEYS]
        if bad:
            names = ", ".join(repr(s) for s in bad)
            valid = ", ".join(repr(k) for k in _STAT_KEYS)
            msgs.append(
                f"statcast stats contains unknown key(s) {names}. "
                f"Valid keys: {valid}."
            )
        return msgs
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_statcast.py -v`
Expected: all PASS

- [ ] **Step 5: Run full gates and commit**

```bash
uv run pytest -q && uv run ruff check src tests && uv run ruff format --check src tests && uv run pyright src
git add src/led_ticker_baseball/statcast.py tests/test_statcast.py
git commit -m "feat: statcast validate_config guardrails"
```

---

### Task 8: Register the widget + smoke test

**Files:**
- Modify: `src/led_ticker_baseball/__init__.py`
- Modify: `tests/test_smoke.py`

- [ ] **Step 1: Write the failing test change**

In `tests/test_smoke.py`, extend the widget assertions:

```python
        assert get_widget_class("baseball.scores") is not None
        assert get_widget_class("baseball.standings") is not None
        assert get_widget_class("baseball.promotions") is not None
        assert get_widget_class("baseball.statcast") is not None
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_smoke.py -v`
Expected: FAIL (baseball.statcast not registered)

- [ ] **Step 3: Register**

In `src/led_ticker_baseball/__init__.py`:

(a) Add the import (isort order — `statcast` sorts after `standings`... no: alphabetically `scores` < `standings` < `statcast` < `transition`; ruff will enforce, follow it):

```python
from led_ticker_baseball.statcast import MLBStatcastMonitor
```

(b) In `register()`, after the promotions line:

```python
    api.widget("statcast")(MLBStatcastMonitor)
```

(c) Update the module docstring's widget list to read `"baseball.scores"` / `"baseball.standings"` / `"baseball.promotions"` / `"baseball.statcast"` (keep the transitions/emoji sentence intact).

- [ ] **Step 4: Run the full suite**

Run: `uv run pytest -q`
Expected: all PASS (smoke + import purity cover the new module end to end)

- [ ] **Step 5: Run full gates and commit**

```bash
uv run ruff check src tests && uv run ruff format --check src tests && uv run pyright src
git add src/led_ticker_baseball/__init__.py tests/test_smoke.py
git commit -m "feat: register baseball.statcast widget"
```

---

### Task 9: Docs + final verification

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: README widget section**

Add after the `baseball.promotions` section (mirror its heading level and table style; verify defaults against the code before writing):

````markdown
### `baseball.statcast`

League-wide daily Statcast superlatives — the longest home run, hardest-hit
ball, and fastest/slowest pitch across all of MLB, re-derived through the day
as games progress. One scrolling line per stat with the value in amber and the
record holder's team abbreviation in its brand color:
`Today · Longest HR 463 ft — Butler ATH`. Mornings fall back to yesterday's
finals (`Yest · …`). Data comes from Baseball Savant's day CSV (an
undocumented endpoint — the widget refreshes at a polite default cadence and
skips the pull entirely when no games are live or newly final).

```toml
[[playlist.section.widget]]
type = "baseball.statcast"
```

**No required fields** — everything below is optional tuning.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `stats` | list of strings | all four | Which lines to show, in display order: `"longest_hr"`, `"hardest_hit"`, `"fastest_pitch"`, `"slowest_pitch"`. |
| `update_interval` | int | `1800` | Seconds between refreshes (30 min). A ~10 KB schedule check skips the ~3 MB data pull when nothing changed. |
| `title` | string | `"Statcast"` | Section title override. |
| `timezone` | string | `"America/New_York"` | IANA timezone governing "Today" and the day rollover. |
| `padding` | int | `6` | Horizontal padding (logical px) after each message when scrolling. |
| `bg_color` | RGB list | none | Background fill behind all messages. |
| `font_color` | RGB list / string / table | unset | RGB list tints the stat label and name; the day label, amber value, and team abbr keep their callout colors. A string/table provider overrides all text, as in the other widgets. |
| `font` | string | `"6x12"` | Display font. Hires name needs `font_size`. |

The slowest-pitch line appends the pitch name when known (`69.6 mph (Slow
Curve)`) — that's where the eephus and position-player pitching comedy lives.
With no Statcast data for today or yesterday, the widget falls back to
`Next games: Mar 26` / `No games soon` (offseason) or `No Data` (fetch
failure).
````

Also update the post-install summary sentence to include `baseball.statcast`.

- [ ] **Step 2: CLAUDE.md updates**

- Overview bullet list, after the promotions bullet:

```markdown
- `baseball.statcast` — league-wide daily Statcast superlatives (longest HR,
  hardest hit, fastest/slowest pitch) from Baseball Savant's day CSV;
  schedule-gated stateless re-derive.
```

- Package layout block, after the `promotions.py` line (align columns):

```
  statcast.py     # baseball.statcast widget (MLBStatcastMonitor); Savant day-CSV superlatives; schedule-gated
```

- `register()` snippet: add `api.widget("statcast")(MLBStatcastMonitor)` after the promotions line (match the actual `__init__.py`).
- Tests/CI section: add `test_statcast.py` to the behavior+rendering coverage list.

- [ ] **Step 3: Final verification — all gates plus coverage**

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run pyright src
uv run pytest -q
uv run pytest --cov=src --cov-report=term-missing
```

Expected: clean; suite green; coverage ≥ 90% overall (statcast.py's `start()` will be the main uncovered block, matching the siblings).

- [ ] **Step 4: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: baseball.statcast README section + CLAUDE.md file map"
```

---

## Spec coverage self-check (for the reviewer)

- Data sources, URLs, User-Agent, BOM handling → Tasks 4, 6
- Stat definitions, tie/missing-value rules, topbot attribution → Task 1
- Line format, colors, stats order, pitch-name suffix, name degradation, plain font_color tint → Task 3
- Schedule gate rules (a)–(d) incl. fail-open and snapshot reset on error/fallback → Tasks 2, 6
- Today → Yest → no-games probe → No Data ladder; title-first contract → Tasks 5, 6
- validate_config (unknown keys named, list-of-strings) → Task 7
- Registration + smoke + import purity → Task 8
- README (source of truth) + CLAUDE.md → Task 9
