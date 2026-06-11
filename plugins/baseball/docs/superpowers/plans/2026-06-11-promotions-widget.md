# baseball.promotions Widget Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `baseball.promotions` widget that shows a team's upcoming home-game promotions (giveaways/theme nights, e.g. the Blue Jays' "Loonie Dogs Night") from the MLB StatsAPI schedule `promotions` hydration.

**Architecture:** New `MLBPromotionsMonitor` in `src/led_ticker_baseball/promotions.py`, mirroring `standings.py`'s monitor shape (attrs class, `start()` classmethod, `run_monitor_loop`, `feed_title`/`feed_stories`). A shared `resolve_team_id()` helper is lifted into `teams.py` and `scores.py` is refactored onto it. Spec: `docs/superpowers/specs/2026-06-10-promotions-widget-design.md`.

**Tech Stack:** Python 3.14, attrs, aiohttp, pytest (`asyncio_mode = "auto"`), uv, ruff. Core imports ONLY from `led_ticker.plugin` (enforced by `tests/test_import_purity.py`). NO `from __future__ import annotations` anywhere.

**Commands** (run from the repo root; `../led-ticker` must be checked out as a sibling):

```bash
uv run pytest -q                      # full suite
uv run pytest tests/test_promotions.py -v   # this feature's tests
uv run ruff check src tests          # lint — run before every commit
```

**File map:**

- Create: `src/led_ticker_baseball/promotions.py`
- Create: `tests/test_promotions.py`
- Modify: `src/led_ticker_baseball/teams.py` (add `resolve_team_id`)
- Modify: `src/led_ticker_baseball/scores.py` (use the helper)
- Modify: `src/led_ticker_baseball/__init__.py` (register widget)
- Modify: `tests/test_smoke.py` (assert registration)
- Modify: `README.md`, `CLAUDE.md` (docs)

---

### Task 1: `resolve_team_id` helper in teams.py

The third abbr→id resolver would otherwise be born in promotions.py; lift a shared one instead.

**Files:**
- Modify: `src/led_ticker_baseball/teams.py`
- Create: `tests/test_promotions.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_promotions.py`:

```python
"""Tests for the MLB promotions widget and the shared resolve_team_id helper."""

import unittest.mock as mock


def _ctx(json_value):
    """Async context manager mock whose response .json() returns json_value."""
    resp = mock.AsyncMock()
    resp.json.return_value = json_value
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


TEAMS_PAYLOAD = {
    "teams": [
        {"id": 141, "abbreviation": "TOR"},
        {"id": 147, "abbreviation": "NYY"},
    ]
}


class TestResolveTeamId:
    async def test_resolves_known_abbreviation(self):
        from led_ticker_baseball.teams import resolve_team_id

        session = make_session({"/teams": TEAMS_PAYLOAD})
        assert await resolve_team_id(session, "TOR") == 141

    async def test_unknown_abbreviation_returns_none(self):
        from led_ticker_baseball.teams import resolve_team_id

        session = make_session({"/teams": TEAMS_PAYLOAD})
        assert await resolve_team_id(session, "ZZZ") is None

    async def test_request_failure_returns_none(self):
        from led_ticker_baseball.teams import resolve_team_id

        session = mock.MagicMock()
        session.get.side_effect = RuntimeError("network down")
        assert await resolve_team_id(session, "TOR") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_promotions.py -v`
Expected: 3 FAILED with `ImportError: cannot import name 'resolve_team_id'`

- [ ] **Step 3: Implement the helper**

In `src/led_ticker_baseball/teams.py`, replace the import block at the top:

```python
import logging

import aiohttp

from led_ticker.plugin import (
    Color,
    colors,
    make_color,
)
```

After the `from led_ticker.plugin import (...)` block, add:

```python
logger: logging.Logger = logging.getLogger(__name__)
```

At the end of the file, add:

```python
async def resolve_team_id(
    session: aiohttp.ClientSession, abbr: str
) -> int | None:
    """Resolve a team abbreviation (e.g. "TOR") to its MLB StatsAPI team ID.

    Returns None when the abbreviation is unknown or the request fails.
    """
    url = f"{MLB_API}/teams?sportId=1"
    try:
        async with session.get(url) as resp:
            data = await resp.json()
    except Exception:
        logger.exception("Failed to resolve team ID for %s", abbr)
        return None
    for t in data.get("teams", []):
        if t.get("abbreviation") == abbr:
            return t.get("id")
    logger.warning("Team %s not found in MLB API", abbr)
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_promotions.py -v`
Expected: 3 PASSED

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check src tests
git add src/led_ticker_baseball/teams.py tests/test_promotions.py
git commit -m "feat: add shared resolve_team_id helper to teams.py"
```

---

### Task 2: Refactor scores.py onto the shared helper

Behavior-preserving: same URL, same parsing, same logging intent. Existing tests are the safety net — no new tests.

**Files:**
- Modify: `src/led_ticker_baseball/scores.py:1128-1142` (`_resolve_team_id`)

- [ ] **Step 1: Add the import**

In `src/led_ticker_baseball/scores.py`, extend the teams import block:

```python
from led_ticker_baseball.teams import (
    MLB_API,
    MLB_TEAM_NAMES,
    _MLB_LIVE_API,
    _team_color,
    _team_palette,
    resolve_team_id,
)
```

- [ ] **Step 2: Replace the method body**

Replace the whole `_resolve_team_id` method of `MLBScoreMonitor`:

```python
    async def _resolve_team_id(self) -> None:
        """Fetch team ID from MLB API."""
        logger.debug("MLB: resolving team ID for %s", self.team)
        team_id = await resolve_team_id(self.session, self.team)
        if team_id is not None:
            self._team_id = team_id
            logger.debug("MLB: %s → id %d", self.team, self._team_id)
```

- [ ] **Step 3: Run the full suite**

Run: `uv run pytest -q`
Expected: all PASS (scores tests exercise the same behavior through the wrapper)

- [ ] **Step 4: Lint and commit**

```bash
uv run ruff check src tests
git add src/led_ticker_baseball/scores.py
git commit -m "refactor: scores._resolve_team_id delegates to teams.resolve_team_id"
```

---

### Task 3: promotions.py pure helpers (clean / dedupe / match / date)

**Files:**
- Create: `src/led_ticker_baseball/promotions.py`
- Modify: `tests/test_promotions.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_promotions.py`:

```python
class TestCleanPromoName:
    def test_strips_presented_by(self):
        from led_ticker_baseball.promotions import _clean_promo_name

        assert (
            _clean_promo_name("Loonie Dogs Night presented by Schneiders")
            == "Loonie Dogs Night"
        )

    def test_strips_pres_by(self):
        from led_ticker_baseball.promotions import _clean_promo_name

        assert _clean_promo_name("Loonie Dogs Night pres. by Schneiders") == (
            "Loonie Dogs Night"
        )

    def test_case_insensitive(self):
        from led_ticker_baseball.promotions import _clean_promo_name

        assert _clean_promo_name("Pride Night Presented By TD") == "Pride Night"

    def test_no_sponsor_unchanged(self):
        from led_ticker_baseball.promotions import _clean_promo_name

        assert _clean_promo_name("Canada Day") == "Canada Day"


class TestDedupePromos:
    def test_exact_duplicates_collapse(self):
        from led_ticker_baseball.promotions import _dedupe_promos

        assert _dedupe_promos(["Pride Night", "pride night"]) == ["Pride Night"]

    def test_prefix_duplicate_keeps_shorter_seen_first(self):
        from led_ticker_baseball.promotions import _dedupe_promos

        names = ["Dylan Cease Bobblehead Giveaway", "Dylan Cease Bobblehead Giveaway Night"]
        assert _dedupe_promos(names) == ["Dylan Cease Bobblehead Giveaway"]

    def test_prefix_duplicate_keeps_shorter_seen_second(self):
        from led_ticker_baseball.promotions import _dedupe_promos

        names = ["Dylan Cease Bobblehead Giveaway Night", "Dylan Cease Bobblehead Giveaway"]
        assert _dedupe_promos(names) == ["Dylan Cease Bobblehead Giveaway"]

    def test_distinct_names_kept_in_order(self):
        from led_ticker_baseball.promotions import _dedupe_promos

        names = ["Loonie Dogs Night", "Pride Night"]
        assert _dedupe_promos(names) == names


class TestMatchAny:
    def test_case_insensitive_substring(self):
        from led_ticker_baseball.promotions import _match_any

        assert _match_any("Loonie Dogs Night", ["loonie dogs"])

    def test_no_match(self):
        from led_ticker_baseball.promotions import _match_any

        assert not _match_any("Pride Night", ["bobblehead"])

    def test_empty_keywords_never_match(self):
        from led_ticker_baseball.promotions import _match_any

        assert not _match_any("Pride Night", [])


class TestGameLocalDate:
    def test_official_date_preferred(self):
        import datetime as dt
        from zoneinfo import ZoneInfo

        from led_ticker_baseball.promotions import _game_local_date

        g = {"officialDate": "2026-06-23", "gameDate": "2026-06-24T02:15:00Z"}
        tz = ZoneInfo("America/New_York")
        assert _game_local_date(g, tz) == dt.date(2026, 6, 23)

    def test_game_date_fallback_converts_timezone(self):
        import datetime as dt
        from zoneinfo import ZoneInfo

        from led_ticker_baseball.promotions import _game_local_date

        # 02:15 UTC = 22:15 the previous day in New York
        g = {"gameDate": "2026-06-24T02:15:00Z"}
        tz = ZoneInfo("America/New_York")
        assert _game_local_date(g, tz) == dt.date(2026, 6, 23)

    def test_missing_dates_return_none(self):
        from zoneinfo import ZoneInfo

        from led_ticker_baseball.promotions import _game_local_date

        assert _game_local_date({}, ZoneInfo("America/New_York")) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_promotions.py -v`
Expected: new tests FAIL with `ModuleNotFoundError: No module named 'led_ticker_baseball.promotions'`; Task 1 tests still PASS.

- [ ] **Step 3: Create the module with the helpers**

Create `src/led_ticker_baseball/promotions.py`:

```python
"""MLB home-game promotions widget using the free MLB Stats API.

Data comes from the schedule endpoint's ``promotions`` hydration — giveaways
and theme nights attached to each home game (e.g. the Blue Jays' "Loonie Dogs
Night"). The API has no live counter data; this widget shows what's on, not
how many hot dogs were eaten.
"""

import contextlib
import logging
import re
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

logger: logging.Logger = logging.getLogger(__name__)

# "Loonie Dogs Night presented by Schneiders" → "Loonie Dogs Night"
_SPONSOR_RE: re.Pattern[str] = re.compile(
    r"\s+(?:presented by|pres\. by)\s+.*$", re.IGNORECASE
)


def _clean_promo_name(name: str) -> str:
    """Strip sponsor tails: 'X presented by Y' / 'X pres. by Y' → 'X'."""
    return _SPONSOR_RE.sub("", name).strip()


def _dedupe_promos(names: list[str]) -> list[str]:
    """Collapse duplicate promo names, keeping feed order.

    Exact duplicates (casefolded) are dropped; when one name is a prefix of
    another (the feed lists both "Dylan Cease Bobblehead Giveaway Night" and
    "Dylan Cease Bobblehead Giveaway"), the shorter name wins.
    """
    kept: list[str] = []
    for name in names:
        cf = name.casefold()
        dominated = False
        for i, other in enumerate(kept):
            ocf = other.casefold()
            if cf.startswith(ocf):
                dominated = True  # a shorter-or-equal name is already kept
                break
            if ocf.startswith(cf):
                kept[i] = name  # new name is shorter; it wins
                dominated = True
                break
        if not dominated:
            kept.append(name)
    return kept


def _match_any(name: str, keywords: list[str]) -> bool:
    """Case-insensitive substring match against any keyword."""
    n = name.casefold()
    return any(k.casefold() in n for k in keywords)


def _game_local_date(g: dict[str, Any], tz: ZoneInfo) -> date | None:
    """Local calendar date of a schedule game: officialDate, else gameDate."""
    official = g.get("officialDate")
    if official:
        with contextlib.suppress(ValueError, TypeError):
            return date.fromisoformat(official)
    game_date = g.get("gameDate")
    if game_date:
        with contextlib.suppress(ValueError, TypeError):
            dt = datetime.fromisoformat(game_date.replace("Z", "+00:00"))
            return dt.astimezone(tz).date()
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_promotions.py -v`
Expected: all PASS

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check src tests
git add src/led_ticker_baseball/promotions.py tests/test_promotions.py
git commit -m "feat: promotions name cleaning, dedupe, matching, date helpers"
```

---

### Task 4: GamePromos + widget skeleton + `_parse_home_games`

**Files:**
- Modify: `src/led_ticker_baseball/promotions.py`
- Modify: `tests/test_promotions.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_promotions.py`:

```python
def make_game(home_id, official_date, promos=()):
    """Minimal schedule-game payload. home_id 141 = TOR (the tested team)."""
    return {
        "officialDate": official_date,
        "teams": {
            "home": {"team": {"id": home_id}},
            "away": {"team": {"id": 999}},
        },
        "promotions": [{"name": n} for n in promos],
    }


def make_schedule(*games):
    return {"dates": [{"games": list(games)}]}


def make_widget(**kwargs):
    from led_ticker_baseball.promotions import MLBPromotionsMonitor

    widget = MLBPromotionsMonitor(
        session=kwargs.pop("session", mock.Mock()),
        team="TOR",
        **kwargs,
    )
    widget._team_id = 141
    return widget


class TestParseHomeGames:
    def _parse(self, data):
        from zoneinfo import ZoneInfo

        widget = make_widget()
        return widget._parse_home_games(data, ZoneInfo("America/New_York"))

    def test_home_games_only(self):
        data = make_schedule(
            make_game(141, "2026-06-23", promos=["Loonie Dogs Night"]),
            make_game(144, "2026-06-24", promos=["Bobblehead Giveaway"]),  # away
        )
        games, had_games = self._parse(data)
        assert had_games is True
        assert len(games) == 1
        assert games[0].promos == ["Loonie Dogs Night"]

    def test_promos_cleaned_and_deduped(self):
        data = make_schedule(
            make_game(
                141,
                "2026-06-10",
                promos=[
                    "Dylan Cease Bobblehead Giveaway Night",
                    "Dylan Cease Bobblehead Giveaway presented by Rogers",
                ],
            ),
        )
        games, _ = self._parse(data)
        assert games[0].promos == ["Dylan Cease Bobblehead Giveaway"]

    def test_doubleheader_promos_merged_by_date(self):
        data = make_schedule(
            make_game(141, "2026-06-23", promos=["Loonie Dogs Night"]),
            make_game(141, "2026-06-23", promos=["Pride Night"]),
        )
        games, _ = self._parse(data)
        assert len(games) == 1
        assert games[0].promos == ["Loonie Dogs Night", "Pride Night"]

    def test_sorted_by_date(self):
        data = make_schedule(
            make_game(141, "2026-06-30", promos=["Loonie Dogs Night"]),
            make_game(141, "2026-06-23", promos=["Pride Night"]),
        )
        games, _ = self._parse(data)
        assert [g.game_date.day for g in games] == [23, 30]

    def test_empty_schedule(self):
        games, had_games = self._parse({"dates": []})
        assert games == []
        assert had_games is False

    def test_away_only_sets_had_games(self):
        data = make_schedule(make_game(144, "2026-06-24"))
        games, had_games = self._parse(data)
        assert games == []
        assert had_games is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_promotions.py -v`
Expected: TestParseHomeGames FAIL with `ImportError: cannot import name 'MLBPromotionsMonitor'`

- [ ] **Step 3: Implement**

In `src/led_ticker_baseball/promotions.py`, replace the import section at the top of the file (keeping the module docstring) with:

```python
import contextlib
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import aiohttp
import attrs

from led_ticker.plugin import (
    Color,
    ColorProvider,
    FONT_DEFAULT,
    Font,
    SegmentMessage,
    TickerMessage,
)

logger: logging.Logger = logging.getLogger(__name__)
```

(Imports grow per task to keep `ruff`'s unused-import check green at every
commit; Tasks 5–7 each list their additions. The `_SPONSOR_RE` constant and
the four helpers from Task 3 stay as they are, below this block.)

Then append at the end of the file:

```python
@dataclass
class GamePromos:
    game_date: date  # local calendar date of the home game
    promos: list[str] = field(default_factory=list)


@attrs.define
class MLBPromotionsMonitor:
    """Upcoming home-game promotions (giveaways / theme nights) for one team."""

    session: aiohttp.ClientSession
    team: str
    title: str = ""
    timezone: str = "America/New_York"
    lookahead_days: int = 14
    highlight: list[str] = attrs.field(factory=list)
    filter: list[str] = attrs.field(factory=list)
    limit: int = 0
    padding: int = 6
    hold_time: float = 0.0
    bg_color: Color | None = attrs.field(default=None, kw_only=True)
    font_color: Color | ColorProvider | None = attrs.field(default=None, kw_only=True)
    font: Font = attrs.field(default=FONT_DEFAULT, kw_only=True)
    _team_id: int = attrs.field(init=False, default=0)
    _tz: ZoneInfo | None = attrs.field(init=False, default=None)
    feed_title: TickerMessage | SegmentMessage | None = attrs.field(
        init=False, default=None
    )
    feed_stories: list[TickerMessage | SegmentMessage] = attrs.field(
        init=False, factory=list
    )

    def _parse_home_games(
        self, data: dict[str, Any], tz: ZoneInfo
    ) -> tuple[list[GamePromos], bool]:
        """Per-date home-game promo lists from a schedule response.

        Returns (games sorted by date, whether the response had ANY games) —
        the flag distinguishes a road trip from the offseason in the
        fallback path. Doubleheader promos merge into one date entry.
        """
        by_date: dict[date, list[str]] = {}
        had_games = False
        for date_entry in data.get("dates", []):
            for g in date_entry.get("games", []):
                had_games = True
                home = g.get("teams", {}).get("home", {}).get("team", {})
                if home.get("id") != self._team_id:
                    continue
                d = _game_local_date(g, tz)
                if d is None:
                    continue
                names = [
                    _clean_promo_name(p["name"])
                    for p in g.get("promotions", [])
                    if p.get("name")
                ]
                by_date.setdefault(d, []).extend(names)
        games = [
            GamePromos(game_date=d, promos=_dedupe_promos(names))
            for d, names in sorted(by_date.items())
        ]
        return games, had_games
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_promotions.py -v`
Expected: all PASS

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check src tests
git add src/led_ticker_baseball/promotions.py tests/test_promotions.py
git commit -m "feat: MLBPromotionsMonitor skeleton + home-game promo parsing"
```

---

### Task 5: Selection + story building

**Files:**
- Modify: `src/led_ticker_baseball/promotions.py`
- Modify: `tests/test_promotions.py`

- [ ] **Step 1: Write the failing tests**

Add `import datetime as dt` to the imports at the top of
`tests/test_promotions.py`, then append:

```python
def gp(day, promos):
    """GamePromos in June 2026 shorthand."""
    from led_ticker_baseball.promotions import GamePromos

    return GamePromos(game_date=dt.date(2026, 6, day), promos=list(promos))


TODAY = dt.date(2026, 6, 10)


class TestPickTarget:
    def test_today_preferred_over_future(self):
        widget = make_widget()
        target = widget._pick_target(
            [gp(10, ["Loonie Dogs Night"]), gp(23, ["Pride Night"])], TODAY
        )
        assert target.game_date == TODAY

    def test_earliest_future_when_today_empty(self):
        widget = make_widget()
        target = widget._pick_target(
            [gp(10, []), gp(23, ["Pride Night"])], TODAY
        )
        assert target.game_date == dt.date(2026, 6, 23)

    def test_filter_skips_non_matching_games(self):
        widget = make_widget(filter=["loonie"])
        target = widget._pick_target(
            [gp(10, ["Pride Night"]), gp(23, ["Loonie Dogs Night"])], TODAY
        )
        assert target.game_date == dt.date(2026, 6, 23)
        assert target.promos == ["Loonie Dogs Night"]

    def test_none_when_no_matches(self):
        widget = make_widget(filter=["bobblehead"])
        assert widget._pick_target([gp(10, ["Pride Night"])], TODAY) is None


class TestBuildPromoStories:
    def test_today_label(self):
        widget = make_widget()
        stories = widget._build_promo_stories(gp(10, ["Loonie Dogs Night"]), TODAY)
        assert len(stories) == 1
        texts = [t for t, _ in stories[0].segments]
        assert texts[0] == "Today · "
        assert texts[1] == "Loonie Dogs Night"

    def test_future_date_label(self):
        widget = make_widget()
        stories = widget._build_promo_stories(gp(23, ["Pride Night"]), TODAY)
        texts = [t for t, _ in stories[0].segments]
        assert texts[0] == "Jun 23 · "

    def test_highlight_sorts_first_and_renders_amber(self):
        widget = make_widget(highlight=["loonie"])
        stories = widget._build_promo_stories(
            gp(10, ["Pride Night", "Loonie Dogs Night"]), TODAY
        )
        first_texts = [t for t, _ in stories[0].segments]
        assert first_texts[1] == "Loonie Dogs Night"
        name_color = stories[0].segments[1][1]
        assert (name_color.red, name_color.green, name_color.blue) == (255, 200, 60)
        # Non-highlighted promo stays white
        from led_ticker.colors import RGB_WHITE

        assert stories[1].segments[1][1] is RGB_WHITE

    def test_limit_applied_after_highlight_sort(self):
        widget = make_widget(highlight=["pride"], limit=1)
        stories = widget._build_promo_stories(
            gp(10, ["Loonie Dogs Night", "Pride Night"]), TODAY
        )
        assert len(stories) == 1
        assert stories[0].segments[1][0] == "Pride Night"

    def test_zero_limit_means_all(self):
        widget = make_widget(limit=0)
        stories = widget._build_promo_stories(
            gp(10, ["Loonie Dogs Night", "Pride Night"]), TODAY
        )
        assert len(stories) == 2

    def test_stories_centered(self):
        widget = make_widget()
        stories = widget._build_promo_stories(gp(10, ["Pride Night"]), TODAY)
        assert stories[0].center is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_promotions.py -v`
Expected: new tests FAIL with `AttributeError: ... has no attribute '_pick_target'` (and `_build_promo_stories`)

- [ ] **Step 3: Implement**

Add `colors` and `make_color` to the `from led_ticker.plugin import (...)`
block in `promotions.py`, then add these methods to `MLBPromotionsMonitor`
(after `_parse_home_games`):

```python
    def _apply_filter(self, promos: list[str]) -> list[str]:
        """Keep only promos matching the filter keywords (all when unset)."""
        if not self.filter:
            return list(promos)
        return [p for p in promos if _match_any(p, self.filter)]

    def _pick_target(
        self, games: list[GamePromos], today: date
    ) -> GamePromos | None:
        """First game on/after today with post-filter promos (today wins)."""
        for game in games:
            if game.game_date < today:
                continue
            matches = self._apply_filter(game.promos)
            if matches:
                return GamePromos(game_date=game.game_date, promos=matches)
        return None

    def _build_promo_stories(
        self, target: GamePromos, today: date
    ) -> list[SegmentMessage]:
        """One centered story per promo: '<Today|Jun 22> · <name>'.

        Highlighted promos render amber and sort first; `limit` truncates
        AFTER that sort so highlights are never the lines dropped.
        """
        label = (
            "Today"
            if target.game_date == today
            else target.game_date.strftime("%b %-d")
        )
        date_c = make_color(150, 150, 150)  # grey — date label
        highlight_c = make_color(255, 200, 60)  # amber — highlighted promo

        highlighted = [p for p in target.promos if _match_any(p, self.highlight)]
        rest = [p for p in target.promos if p not in highlighted]
        ordered = highlighted + rest
        if self.limit > 0:
            ordered = ordered[: self.limit]

        return [
            SegmentMessage(
                [
                    (f"{label} · ", date_c),
                    (
                        name,
                        highlight_c if name in highlighted else colors.RGB_WHITE,
                    ),
                ],
                center=True,
                bg_color=self.bg_color,
                font=self.font,
                font_color=self.font_color,
            )
            for name in ordered
        ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_promotions.py -v`
Expected: all PASS

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check src tests
git add src/led_ticker_baseball/promotions.py tests/test_promotions.py
git commit -m "feat: promotions target selection + highlight/limit story building"
```

---

### Task 6: State setters (title, error, next-home, fallback probe)

**Files:**
- Modify: `src/led_ticker_baseball/promotions.py`
- Modify: `tests/test_promotions.py`

- [ ] **Step 1: Write the failing tests**

Add `from zoneinfo import ZoneInfo` to the imports at the top of
`tests/test_promotions.py`, then append:

```python
NY = ZoneInfo("America/New_York")


def probe_schedule(*games):
    """Payload served to the 30-day fallback probe (gameType=R URL)."""
    return {"dates": [{"games": list(games)}]}


class TestStateSetters:
    def test_default_title_is_team_name_plus_promos(self):
        widget = make_widget()
        widget._set_title()
        texts = [t for t, _ in widget.feed_title.segments]
        assert texts == ["Blue Jays", " Promos"]

    def test_title_override(self):
        widget = make_widget(title="Dog Watch")
        widget._set_title()
        assert widget.feed_title.text == "Dog Watch"

    def test_error_state(self):
        widget = make_widget()
        widget._set_error_state()
        assert len(widget.feed_stories) == 1
        assert widget.feed_stories[0].text == "No Data"

    def test_next_home_future(self):
        widget = make_widget()
        widget._set_next_home_state(dt.date(2026, 6, 22), TODAY)
        assert widget.feed_stories[0].text == "Next home game: Jun 22"

    def test_next_home_today(self):
        widget = make_widget()
        widget._set_next_home_state(TODAY, TODAY)
        assert widget.feed_stories[0].text == "Home game today"

    async def test_fallback_road_trip_finds_next_home(self):
        session = make_session(
            {"gameType=R": probe_schedule(make_game(141, "2026-06-26"))}
        )
        widget = make_widget(session=session)
        await widget._set_fallback_state(NY, had_games=True)
        assert widget.feed_stories[0].text == "Next home game: Jun 26"

    async def test_fallback_road_trip_no_home_in_probe(self):
        session = make_session(
            {"gameType=R": probe_schedule(make_game(144, "2026-06-26"))}
        )
        widget = make_widget(session=session)
        await widget._set_fallback_state(NY, had_games=True)
        assert widget.feed_stories[0].text == "No home games soon"

    async def test_fallback_offseason_opener_on_road(self):
        session = make_session(
            {"gameType=R": probe_schedule(make_game(144, "2027-03-28"))}
        )
        widget = make_widget(session=session)
        await widget._set_fallback_state(NY, had_games=False)
        assert widget.feed_stories[0].text == "Opens Mar 28"

    async def test_fallback_offseason_no_games(self):
        session = make_session({"gameType=R": {"dates": []}})
        widget = make_widget(session=session)
        await widget._set_fallback_state(NY, had_games=False)
        assert widget.feed_stories[0].text == "Opens soon"

    async def test_fallback_probe_failure_degrades(self):
        session = mock.MagicMock()
        session.get.side_effect = RuntimeError("network down")
        widget = make_widget(session=session)
        await widget._set_fallback_state(NY, had_games=False)
        assert widget.feed_stories[0].text == "Opens soon"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_promotions.py -v`
Expected: TestStateSetters FAIL with `AttributeError: ... '_set_title'` etc.

- [ ] **Step 3: Implement**

In `promotions.py`, add `timedelta` to the `from datetime import (...)` line
and add the teams import below the plugin block:

```python
from led_ticker_baseball.teams import (
    MLB_API,
    MLB_TEAM_NAMES,
    _team_color,
)
```

Then add these methods to `MLBPromotionsMonitor`:

```python
    def _set_title(self) -> None:
        """Team-colored '<Team> Promos' title, or the configured override."""
        if self.title:
            t_c = (
                self.font_color if self.font_color is not None else colors.RGB_WHITE
            )
            self.feed_title = TickerMessage(
                self.title, font_color=t_c, center=True, bg_color=self.bg_color
            )
            return
        team_name = MLB_TEAM_NAMES.get(self.team, self.team)
        self.feed_title = SegmentMessage(
            [(team_name, _team_color(self.team)), (" Promos", colors.RGB_WHITE)],
            center=True,
            bg_color=self.bg_color,
            font=self.font,
            font_color=self.font_color,
        )

    def _body_color(self) -> Color | ColorProvider:
        return self.font_color if self.font_color is not None else colors.RGB_WHITE

    def _set_error_state(self) -> None:
        """Set display to error state."""
        self.feed_stories = [
            TickerMessage(
                "No Data", font_color=self._body_color(), bg_color=self.bg_color
            ),
        ]
        logger.info(
            "MLB Promotions %s updated: %d stories (no data)",
            self.team,
            len(self.feed_stories),
        )

    def _set_next_home_state(self, game_date: date, today: date) -> None:
        """Home games exist in the window but none had matching promos."""
        if game_date == today:
            text = "Home game today"
        else:
            text = f"Next home game: {game_date.strftime('%b %-d')}"
        self.feed_stories = [
            TickerMessage(
                text,
                font_color=self._body_color(),
                center=True,
                bg_color=self.bg_color,
            ),
        ]
        logger.info("MLB Promotions %s updated: %s", self.team, text)

    async def _set_fallback_state(self, tz: ZoneInfo, had_games: bool) -> None:
        """No home games in the window: probe 30 days of regular season.

        First home game → "Next home game: <date>". Otherwise `had_games`
        (the main window had away games → mid-season road trip) decides
        between "No home games soon" and the offseason "Opens …" texts.
        A failed probe degrades to the no-result text silently.
        """
        now = datetime.now(tz)
        start = now.strftime("%Y-%m-%d")
        end = (now + timedelta(days=30)).strftime("%Y-%m-%d")
        url = (
            f"{MLB_API}/schedule?teamId={self._team_id}"
            f"&startDate={start}&endDate={end}&sportId=1&gameType=R"
        )
        data: dict[str, Any] = {}
        try:
            async with self.session.get(url) as resp:
                data = await resp.json()
        except Exception:
            logger.debug("MLB Promotions probe failed for %s", self.team)

        first_any: date | None = None
        first_home: date | None = None
        for date_entry in data.get("dates", []):
            for g in date_entry.get("games", []):
                d = _game_local_date(g, tz)
                if d is None:
                    continue
                if first_any is None or d < first_any:
                    first_any = d
                home = g.get("teams", {}).get("home", {}).get("team", {})
                if home.get("id") == self._team_id and (
                    first_home is None or d < first_home
                ):
                    first_home = d

        if first_home is not None:
            text = f"Next home game: {first_home.strftime('%b %-d')}"
        elif had_games:
            text = "No home games soon"
        elif first_any is not None:
            text = f"Opens {first_any.strftime('%b %-d')}"
        else:
            text = "Opens soon"

        self.feed_stories = [
            TickerMessage(
                text,
                font_color=self._body_color(),
                center=True,
                bg_color=self.bg_color,
            ),
        ]
        logger.info("MLB Promotions %s updated: fallback (%s)", self.team, text)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_promotions.py -v`
Expected: all PASS

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check src tests
git add src/led_ticker_baseball/promotions.py tests/test_promotions.py
git commit -m "feat: promotions title/error/next-home/fallback states"
```

---

### Task 7: `update()` + `start()`

**Files:**
- Modify: `src/led_ticker_baseball/promotions.py`
- Modify: `tests/test_promotions.py`

- [ ] **Step 1: Write the failing tests**

Add `import logging` to the imports at the top of `tests/test_promotions.py`.
`update()` uses real wall-clock "today", so these tests date games relative to
the running clock (the suite's convention — standings does the same). Append:

```python
def _today_ny():
    import datetime as dtm

    return dtm.datetime.now(NY).date()


class TestUpdate:
    def _widget(self, schedule_payload, probe_payload=None, **kwargs):
        routes = {"hydrate=game(promotions)": schedule_payload}
        if probe_payload is not None:
            routes["gameType=R"] = probe_payload
        widget = make_widget(session=make_session(routes), **kwargs)
        widget._tz = NY
        return widget

    async def test_today_home_game_with_promos(self):
        today = _today_ny()
        widget = self._widget(
            make_schedule(
                make_game(141, today.isoformat(), promos=["Loonie Dogs Night"])
            )
        )
        await widget.update()
        texts = [t for t, _ in widget.feed_stories[0].segments]
        assert texts == ["Today · ", "Loonie Dogs Night"]
        assert widget.feed_title is not None

    async def test_future_home_game_when_today_empty(self):
        today = _today_ny()
        future = today + dt.timedelta(days=5)
        widget = self._widget(
            make_schedule(make_game(141, future.isoformat(), promos=["Pride Night"]))
        )
        await widget.update()
        texts = [t for t, _ in widget.feed_stories[0].segments]
        assert texts[0] == f"{future.strftime('%b %-d')} · "

    async def test_no_matching_promos_shows_next_home_game(self):
        today = _today_ny()
        future = today + dt.timedelta(days=5)
        widget = self._widget(
            make_schedule(make_game(141, future.isoformat(), promos=["Pride Night"])),
            filter=["bobblehead"],
        )
        await widget.update()
        assert widget.feed_stories[0].text == (
            f"Next home game: {future.strftime('%b %-d')}"
        )

    async def test_road_trip_routes_to_fallback(self):
        today = _today_ny()
        home_date = today + dt.timedelta(days=20)
        widget = self._widget(
            make_schedule(make_game(144, today.isoformat())),  # away game only
            probe_payload=probe_schedule(make_game(141, home_date.isoformat())),
        )
        await widget.update()
        assert widget.feed_stories[0].text == (
            f"Next home game: {home_date.strftime('%b %-d')}"
        )

    async def test_empty_schedule_routes_to_offseason_fallback(self):
        widget = self._widget({"dates": []}, probe_payload={"dates": []})
        await widget.update()
        assert widget.feed_stories[0].text == "Opens soon"

    async def test_api_error_sets_no_data(self):
        session = mock.MagicMock()
        session.get.side_effect = RuntimeError("network down")
        widget = make_widget(session=session)
        widget._tz = NY
        await widget.update()
        assert widget.feed_stories[0].text == "No Data"

    async def test_unresolved_team_id_sets_no_data(self):
        widget = self._widget(make_schedule())
        widget._team_id = 0
        await widget.update()
        assert widget.feed_stories[0].text == "No Data"

    async def test_update_logs_info(self, caplog):
        today = _today_ny()
        widget = self._widget(
            make_schedule(
                make_game(141, today.isoformat(), promos=["Loonie Dogs Night"])
            )
        )
        with caplog.at_level(logging.INFO, logger="led_ticker_baseball.promotions"):
            await widget.update()
        matching = [
            r
            for r in caplog.records
            if r.levelno == logging.INFO and "promotions" in r.message.lower()
        ]
        assert matching, f"expected INFO log; got {[r.message for r in caplog.records]}"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_promotions.py -v`
Expected: TestUpdate FAIL with `AttributeError: ... 'update'`

- [ ] **Step 3: Implement**

In `promotions.py`: change the typing import to `from typing import Any, Self`;
add `run_monitor_loop` and `spawn_tracked` to the plugin import block; add
`resolve_team_id` to the teams import block; and add below the `logger` line:

```python
_INTERVAL_SIX_HOURS: int = 21600
```

Then add to `MLBPromotionsMonitor`, directly below the attrs fields (above `_parse_home_games`):

```python
    @classmethod
    async def start(
        cls,
        session: aiohttp.ClientSession,
        team: str,
        update_interval: int = _INTERVAL_SIX_HOURS,
        **kwargs: Any,
    ) -> Self:
        logger.debug("MLBPromotionsMonitor.start: team=%s", team)
        widget = cls(session=session, team=team.upper(), **kwargs)
        widget._tz = ZoneInfo(widget.timezone)
        widget._team_id = await resolve_team_id(session, widget.team) or 0
        await widget.update()
        logger.info(
            "MLB Promotions %s: %d stories",
            widget.team,
            len(widget.feed_stories),
        )
        spawn_tracked(run_monitor_loop(widget, update_interval))
        return widget

    async def update(self) -> None:
        """Fetch the promotions-hydrated schedule and build display messages."""
        tz = self._tz or ZoneInfo(self.timezone)
        today = datetime.now(tz).date()
        self._set_title()

        if not self._team_id:
            self._set_error_state()
            return

        start = today.strftime("%Y-%m-%d")
        end = (today + timedelta(days=self.lookahead_days)).strftime("%Y-%m-%d")
        url = (
            f"{MLB_API}/schedule?teamId={self._team_id}"
            f"&startDate={start}&endDate={end}&sportId=1"
            f"&hydrate=game(promotions)"
        )
        try:
            async with self.session.get(url) as resp:
                data = await resp.json()
            games, had_games = self._parse_home_games(data, tz)
        except Exception:
            logger.exception("MLB Promotions API error for %s", self.team)
            self._set_error_state()
            return

        if not games:
            await self._set_fallback_state(tz, had_games)
            return

        target = self._pick_target(games, today)
        if target is None:
            # games is sorted and the query starts at today, so [0] is the
            # earliest upcoming home game.
            self._set_next_home_state(games[0].game_date, today)
            return

        self.feed_stories = self._build_promo_stories(target, today)
        logger.info(
            "MLB Promotions %s updated: %d stories",
            self.team,
            len(self.feed_stories),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_promotions.py -v`
Expected: all PASS. (`start()` mirrors the untested-by-convention sibling `start()`s; it's exercised manually and via the engine.)

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check src tests
git add src/led_ticker_baseball/promotions.py tests/test_promotions.py
git commit -m "feat: promotions update() flow + start() monitor loop"
```

---

### Task 8: `validate_config`

**Files:**
- Modify: `src/led_ticker_baseball/promotions.py`
- Modify: `tests/test_promotions.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_promotions.py`:

```python
class TestValidateConfig:
    def _validate(self, cfg):
        from led_ticker_baseball.promotions import MLBPromotionsMonitor

        return MLBPromotionsMonitor.validate_config(cfg)

    def test_clean_config_passes(self):
        assert self._validate(
            {"team": "TOR", "highlight": ["Loonie Dogs"], "limit": 3}
        ) == []

    def test_negative_limit_rejected(self):
        msgs = self._validate({"team": "TOR", "limit": -1})
        assert len(msgs) == 1
        assert "limit" in msgs[0]

    def test_non_int_limit_rejected(self):
        msgs = self._validate({"team": "TOR", "limit": "3"})
        assert len(msgs) == 1

    def test_string_filter_rejected(self):
        msgs = self._validate({"team": "TOR", "filter": "Loonie Dogs"})
        assert len(msgs) == 1
        assert "filter" in msgs[0]

    def test_string_highlight_rejected(self):
        msgs = self._validate({"team": "TOR", "highlight": "Loonie Dogs"})
        assert len(msgs) == 1
        assert "highlight" in msgs[0]

    def test_messages_returned_not_raised(self):
        msgs = self._validate({"team": "TOR", "limit": -1, "filter": "x"})
        assert len(msgs) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_promotions.py -v`
Expected: TestValidateConfig FAIL with `AttributeError: ... 'validate_config'`

- [ ] **Step 3: Implement**

Add to `MLBPromotionsMonitor`, above `start()`:

```python
    @classmethod
    def validate_config(cls, cfg: dict[str, Any]) -> list[str]:
        """Pre-coercion config check, run by the engine via validate_widget_cfg.

        Returns message strings (does NOT raise); the engine turns any
        returned messages into a pre-flight ValueError. Same contract as
        ``MLBScoreMonitor.validate_config``.
        """
        msgs: list[str] = []

        limit = cfg.get("limit", 0)
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
            msgs.append(
                f"promotions limit={limit!r} must be a non-negative integer."
            )

        for key in ("filter", "highlight"):
            if key not in cfg:
                continue
            val = cfg[key]
            if not isinstance(val, list) or not all(
                isinstance(v, str) for v in val
            ):
                msgs.append(
                    f"promotions {key}={val!r} must be a list of strings, "
                    f'e.g. {key} = ["Loonie Dogs"].'
                )

        return msgs
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_promotions.py -v`
Expected: all PASS

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check src tests
git add src/led_ticker_baseball/promotions.py tests/test_promotions.py
git commit -m "feat: promotions validate_config guardrails"
```

---

### Task 9: Register the widget + smoke test

**Files:**
- Modify: `src/led_ticker_baseball/__init__.py`
- Modify: `tests/test_smoke.py`

- [ ] **Step 1: Write the failing test change**

In `tests/test_smoke.py`, extend the widget assertions:

```python
        assert get_widget_class("baseball.scores") is not None
        assert get_widget_class("baseball.standings") is not None
        assert get_widget_class("baseball.promotions") is not None
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_smoke.py -v`
Expected: FAIL (promotions not registered)

- [ ] **Step 3: Register**

In `src/led_ticker_baseball/__init__.py`, add the import (alphabetical with the others):

```python
from led_ticker_baseball.promotions import MLBPromotionsMonitor
```

Add the registration line in `register()` after standings:

```python
    api.widget("promotions")(MLBPromotionsMonitor)
```

Update the module docstring's widget list sentence to read:

```
The entry-point name ``baseball`` is the plugin namespace, so widgets are
``type = "baseball.scores"`` / ``"baseball.standings"`` /
``"baseball.promotions"``, transitions are ``baseball.roll`` /
``baseball.roll_reverse`` / ``baseball.roll_alternating``, and the emoji is
``:baseball.ball:``.
```

- [ ] **Step 4: Run the full suite**

Run: `uv run pytest -q`
Expected: all PASS (smoke + import purity now cover the new module end-to-end)

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check src tests
git add src/led_ticker_baseball/__init__.py tests/test_smoke.py
git commit -m "feat: register baseball.promotions widget"
```

---

### Task 10: Docs (README + CLAUDE.md) + final verification

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: README widget section**

Add after the `baseball.standings` widget section (mirroring its heading level and table style):

````markdown
### `baseball.promotions`

Upcoming home-game promotions — giveaways and theme nights, e.g. the Blue Jays'
Loonie Dogs Night — for a tracked team, from the schedule API's promotions feed.
Shows today's promos when there's a home game today, otherwise the next home
game's, one scrolling line per promo with a grey date prefix:
`Jun 22 · Retro Domer Hat Giveaway`. Sponsor tails ("presented by …") are
stripped, and near-duplicate feed entries are collapsed. Promos matching
`highlight` render in amber and sort first.

```toml
[[playlist.section.widget]]
type = "baseball.promotions"
team = "TOR"
highlight = ["Loonie Dogs"]
```

**`team` is the only required field** — everything below is optional tuning.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `team` | string | required | MLB team abbreviation — see [Team codes](#team-codes). Case-insensitive. |
| `highlight` | list of strings | `[]` | Case-insensitive substrings; matching promos render amber and sort first. |
| `filter` | list of strings | `[]` | If non-empty, only promos matching one of these substrings are shown. |
| `limit` | int | `0` | Max promo lines (`0` = all). Applied after highlight sorting, so highlighted promos are never the ones dropped. |
| `lookahead_days` | int | `14` | How far ahead to look for the next home game with promotions. |
| `update_interval` | int | `21600` | Seconds between refreshes (6 h — keeps the "Today" label honest after midnight). |
| `title` | string | `"<Team> Promos"` | Section title override. |
| `timezone` | string | `"America/New_York"` | IANA timezone governing "Today" and date labels. |
| `padding` | int | `6` | Horizontal padding (logical px) after each message when scrolling. |
| `bg_color` | RGB list | none | Background fill behind all messages. |
| `font_color` | RGB list / string / table | unset | Override body text color; date labels and highlights keep their callout colors. |
| `font` | string | `"6x12"` | Display font. Hires name needs `font_size`. |

With nothing to show, the widget falls back to `Next home game: Jun 22`
(promo-free homestand), `No home games soon` (road trip), or
`Opens <date>` / `Opens soon` (offseason).
````

Also update the post-install summary sentence (currently "Once installed, the `baseball.scores` / `baseball.standings` widgets, …") to include `baseball.promotions`.

- [ ] **Step 2: CLAUDE.md updates**

In the **Overview** bullet list, after the standings bullet, add:

```markdown
- `baseball.promotions` — upcoming home-game promotions (giveaways/theme nights);
  today-first with highlight/filter/limit knobs and offseason-aware fallbacks.
```

In the **Package layout** block, after the `standings.py` line, add:

```
  promotions.py   # baseball.promotions widget (MLBPromotionsMonitor); home-game promos; today-first + fallback states
```

In the `register()` snippet, after the standings line, add:

```python
    api.widget("promotions")(MLBPromotionsMonitor)
```

In the **Tests / CI** behavior-coverage list, add `test_promotions.py` to the
behavior + rendering coverage line.

- [ ] **Step 3: Final verification**

```bash
uv run ruff check src tests
uv run pytest -q
```

Expected: lint clean, full suite PASS.

- [ ] **Step 4: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: baseball.promotions README section + CLAUDE.md file map"
```

---

## Spec coverage self-check (for the reviewer)

- Config surface (`team`/`highlight`/`filter`/`limit`/`lookahead_days`/`update_interval` + standard knobs) → Tasks 4, 7, 10
- Name cleaning, dedup (prefix rule), case-insensitive matching → Task 3
- Home-games-only, doubleheader merge, officialDate handling → Task 4
- Today-first selection, filter, highlight order/color, limit-after-sort → Task 5
- Title, error, next-home (incl. "Home game today"), road-trip vs offseason fallback → Task 6
- update() routing + INFO logging + start()/monitor loop → Task 7
- validate_config contract → Task 8
- Registration + smoke + import purity → Task 9
- README (user-facing source of truth) + CLAUDE.md invariants → Task 10
- Shared `resolve_team_id` + scores refactor → Tasks 1–2
