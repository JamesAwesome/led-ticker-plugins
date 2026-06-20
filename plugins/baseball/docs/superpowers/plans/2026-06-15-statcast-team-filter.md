# baseball.statcast Team Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional `team` field to `baseball.statcast` that scopes the daily superlatives to one team's own players (e.g. Phillies batters/pitchers), mirroring `baseball.attendance`'s team/league duality; league mode (no `team`) is unchanged.

**Architecture:** Pure client-side row filter on the Savant CSV the widget already pulls — `_derive_records` gains a `team` param and skips a row for a stat unless the relevant player (`_row_team(r, who)`) is on that team. A `team` attrs field (upper-cased via converter), team-aware line format and no-games probe, and team-id resolution in `start()` round it out — all patterned on `attendance.py`. Spec: `docs/superpowers/specs/2026-06-14-statcast-team-filter-design.md`.

**Tech Stack:** Python 3.14, attrs, aiohttp, pytest (`asyncio_mode = "auto"`), uv, ruff (E/F/I/UP/B/SIM + format), pyright, coverage ≥90. Core imports ONLY from `led_ticker.plugin`; `resolve_team_id` etc. from `led_ticker_baseball.teams`. NO `from __future__ import annotations`.

**Branch:** work on `statcast-team-filter` only; never checkout/switch branches; never commit to main.

**Gates — run all four before EVERY commit** (run `uv run ruff format src tests` first if the check fails):

```bash
uv run pytest -q
uv run ruff check src tests
uv run ruff format --check src tests
uv run pyright src
```

**Files:** all changes in `src/led_ticker_baseball/statcast.py`, `tests/test_statcast.py`, plus `README.md` + `CLAUDE.md` in Task 5. No new files; no registration change.

**Test-helper context (already in `tests/test_statcast.py`):** `row(**kwargs)` builds a Savant row defaulting `home_team="PHI"`, `away_team="TOR"`, `inning_topbot="Top"`; `hr(dist, batter=10, **kwargs)` builds a home-run row (passes kwargs through to `row`). `_row_team(r, "batter")` returns the away team when `inning_topbot=="Top"` (away bats on Top), else home; `"pitcher"` is the other side. So a **Phillies batter** event = `away_team="PHI", inning_topbot="Top"` (or `home_team="PHI", inning_topbot="Bot"`); a **Phillies pitcher** event with `inning_topbot="Top"` has the pitcher on `home_team` → set `home_team="PHI"`.

---

### Task 1: `team` filter in `_derive_records` + the `team` field

**Files:**
- Modify: `src/led_ticker_baseball/statcast.py`
- Modify: `tests/test_statcast.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_statcast.py`:

```python
class TestDeriveRecordsTeamFilter:
    def _derive(self, rows, stats, team=""):
        from led_ticker_baseball.statcast import _derive_records

        return _derive_records(rows, list(stats), team)

    def test_longest_hr_only_counts_team_batter(self):
        rows = [
            # Opponent (TOR) hits the longer HR but must be excluded.
            hr(470, batter=99, away_team="TOR", home_team="PHI", inning_topbot="Top"),
            # Phillies batter (away on Top) HR.
            hr(450, batter=11, away_team="PHI", home_team="NYM", inning_topbot="Top"),
        ]
        rec = self._derive(rows, ["longest_hr"], team="PHI")["longest_hr"]
        assert rec.value == 450.0
        assert rec.person_id == 11
        assert rec.team_abbr == "PHI"

    def test_fastest_pitch_only_counts_team_pitcher(self):
        rows = [
            # Phillies pitcher (home team on Top) throws 99.
            row(release_speed=99.0, pitcher=21, home_team="PHI", inning_topbot="Top"),
            # Opponent pitcher throws harder but excluded.
            row(release_speed=103.0, pitcher=88, home_team="NYM", inning_topbot="Top"),
        ]
        rec = self._derive(rows, ["fastest_pitch"], team="PHI")["fastest_pitch"]
        assert rec.value == 99.0
        assert rec.person_id == 21

    def test_no_team_event_omits_stat(self):
        rows = [hr(470, batter=99, away_team="TOR", home_team="NYM", inning_topbot="Top")]
        assert "longest_hr" not in self._derive(rows, ["longest_hr"], team="PHI")

    def test_savant_abbr_normalized_in_filter(self):
        # Savant 'AZ' batter matches team='ARI'.
        rows = [hr(440, batter=7, away_team="AZ", home_team="LAD", inning_topbot="Top")]
        rec = self._derive(rows, ["longest_hr"], team="ARI")["longest_hr"]
        assert rec.person_id == 7

    def test_empty_team_is_league_wide(self):
        # team="" → unchanged: the longest HR wins regardless of team.
        rows = [
            hr(470, batter=99, away_team="TOR", home_team="PHI", inning_topbot="Top"),
            hr(450, batter=11, away_team="PHI", home_team="NYM", inning_topbot="Top"),
        ]
        rec = self._derive(rows, ["longest_hr"], team="")["longest_hr"]
        assert rec.value == 470.0


class TestTeamField:
    def test_team_upper_cased_at_construction(self):
        assert make_widget(team="phi").team == "PHI"

    def test_default_is_league_mode(self):
        assert make_widget().team == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_statcast.py -k "TeamFilter or TeamField" -v`
Expected: FAIL — `_derive_records()` takes 2 args (no `team`), and `MLBStatcastMonitor` has no `team` field.

- [ ] **Step 3: Implement**

In `src/led_ticker_baseball/statcast.py`:

(a) Extend `_derive_records` — add the `team` param and one guard line in `consider`:

```python
def _derive_records(
    rows: list[dict[str, Any]], stats: list[str], team: str = ""
) -> dict[str, StatRecord]:
    """One pass over Savant rows → best record per requested stat key.

    When ``team`` is set, only that team's own players qualify: the batter must
    be on ``team`` for batting stats, the pitcher for pitch stats. Strict
    comparisons keep the first row on ties (CSV order). Rows missing the
    relevant value are skipped.
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
        if team and _row_team(r, who) != team:
            return
        cur = records.get(key)
        if cur is not None and (value >= cur.value if lower else value <= cur.value):
            return
        records[key] = StatRecord(
            value=value,
            person_id=_to_id(r, who),
            team_abbr=_row_team(r, who),
            pitch_name=(r.get("pitch_name") or "").strip(),
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

(b) Add the `team` field to `MLBStatcastMonitor`, immediately after `session`:

```python
    session: aiohttp.ClientSession
    # "" → league-wide; else scope superlatives to that team's own players.
    # Upper-cased at construction so the abbr matches the API on any build path.
    team: str = attrs.field(default="", converter=lambda v: v.upper() if v else "")
    stats: list[str] = attrs.field(factory=lambda: list(_STAT_KEYS))
```

(c) Add the `_team_id` state field, immediately after the `_tz` field:

```python
    _tz: ZoneInfo | None = attrs.field(init=False, default=None)
    _team_id: int = attrs.field(init=False, default=0)
```

(d) In `_derive_day`, pass the team through:

```python
        rows = list(csv.DictReader(io.StringIO(text.lstrip("﻿"))))
        return _derive_records(rows, self.stats, self.team)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_statcast.py -q`
Expected: all PASS (new team tests + existing league tests unchanged).

- [ ] **Step 5: Run full gates and commit**

```bash
uv run pytest -q && uv run ruff check src tests && uv run ruff format --check src tests && uv run pyright src
git add src/led_ticker_baseball/statcast.py tests/test_statcast.py
git commit -m "feat: statcast team filter in derivation + team field"
```

---

### Task 2: Team-mode line format in `_build_stat_stories`

**Files:**
- Modify: `src/led_ticker_baseball/statcast.py`
- Modify: `tests/test_statcast.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_statcast.py`:

```python
class TestBuildStatStoriesTeamMode:
    def test_team_line_leads_with_abbr_no_trailing(self):
        widget = make_widget(team="PHI", stats=["longest_hr"])
        records = {"longest_hr": rec(472, person_id=10, team="PHI")}
        stories = widget._build_stat_stories(records, "Today", {10: "Schwarber"})
        assert line_text(stories[0]) == "PHI Today · Longest HR 472 ft — Schwarber"

    def test_team_prefix_in_brand_color(self):
        from led_ticker_baseball.teams import _team_color

        widget = make_widget(team="PHI", stats=["longest_hr"])
        stories = widget._build_stat_stories(
            {"longest_hr": rec(472, person_id=10, team="PHI")}, "Today", {10: "Schwarber"}
        )
        prefix_c = stories[0].segments[0][1]
        phi = _team_color("PHI")
        assert (prefix_c.red, prefix_c.green, prefix_c.blue) == (phi.red, phi.green, phi.blue)

    def test_team_line_unresolved_name_degrades(self):
        widget = make_widget(team="PHI", stats=["longest_hr"])
        stories = widget._build_stat_stories(
            {"longest_hr": rec(472, person_id=10, team="PHI")}, "6/14", {}
        )
        assert line_text(stories[0]) == "PHI 6/14 · Longest HR 472 ft —"

    def test_team_slowest_pitch_keeps_pitch_name(self):
        widget = make_widget(team="PHI", stats=["slowest_pitch"])
        records = {
            "slowest_pitch": rec(68.0, person_id=31, team="PHI", pitch_name="Slow Curve")
        }
        stories = widget._build_stat_stories(records, "Today", {31: "Strahm"})
        assert line_text(stories[0]) == (
            "PHI Today · Slowest pitch 68.0 mph (Slow Curve) — Strahm"
        )

    def test_league_line_unchanged(self):
        widget = make_widget(stats=["longest_hr"])  # no team
        stories = widget._build_stat_stories(
            {"longest_hr": rec(463, person_id=5, team="OAK")}, "Today", {5: "Butler"}
        )
        assert line_text(stories[0]) == "Today · Longest HR 463 ft — Butler OAK"
```

(The `rec` and `line_text` helpers already exist in this file.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_statcast.py -k TeamMode -v`
Expected: FAIL — team lines currently render the league format (leading day label, trailing abbr).

- [ ] **Step 3: Implement**

Replace `_build_stat_stories` in `statcast.py` with:

```python
    def _build_stat_stories(
        self,
        records: dict[str, StatRecord],
        day_label: str,
        names: dict[int, str],
    ) -> list[TickerMessage | SegmentMessage]:
        """One centered line per stat.

        League mode: 'Today · Longest HR 463 ft — Butler OAK' (trailing team
        abbr in brand color). Team mode (``self.team`` set): the line leads with
        the team abbr in brand color and drops the trailing abbr — the holder is
        always the tracked team — e.g. 'PHI Today · Longest HR 472 ft — Schwarber'.
        ``self.stats`` order is display order; stats with no record are omitted;
        an unresolved name degrades to value only.
        """
        grey = make_color(150, 150, 150)  # grey — day label
        amber = make_color(255, 200, 60)  # amber — the record value
        body_c = self._plain_body_color()

        stories: list[TickerMessage | SegmentMessage] = []
        for key in self.stats:
            record = records.get(key)
            if record is None:
                continue
            segments: list[tuple[str, Color | ColorProvider]] = []
            if self.team:
                segments.append((f"{self.team} ", _team_color(self.team)))
            segments.append((f"{day_label} · ", grey))
            segments.append((f"{_STAT_LABELS[key]} ", body_c))
            segments.append((_format_value(key, record.value), amber))
            if key == "slowest_pitch" and record.pitch_name:
                segments.append((f" ({record.pitch_name})", body_c))
            name = names.get(record.person_id, "")
            if self.team:
                # Holder shown as bare name; team is implied by the prefix.
                segments.append((f" — {name}" if name else " —", body_c))
            else:
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

Run: `uv run pytest tests/test_statcast.py -q`
Expected: all PASS (team-mode + league-mode line tests).

- [ ] **Step 5: Run full gates and commit**

```bash
uv run pytest -q && uv run ruff check src tests && uv run ruff format --check src tests && uv run pyright src
git add src/led_ticker_baseball/statcast.py tests/test_statcast.py
git commit -m "feat: statcast team-mode line format"
```

---

### Task 3: team-id resolution in `start()` + team-aware no-games probe

**Files:**
- Modify: `src/led_ticker_baseball/statcast.py`
- Modify: `tests/test_statcast.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_statcast.py`:

```python
class TestNoGamesStateTeamAware:
    async def test_team_mode_says_next_game_with_teamid(self):
        captured = {}

        def side_effect(url, *args, **kwargs):
            captured["url"] = url
            return _ctx({"dates": [{"date": "2027-03-26"}]})

        session = mock.MagicMock()
        session.get.side_effect = side_effect
        widget = make_widget(session=session, team="PHI")
        widget._team_id = 143
        await widget._set_no_games_state(TODAY)
        assert widget.feed_stories[0].text == "Next game: Mar 26"
        assert "teamId=143" in captured["url"]

    async def test_league_mode_says_next_games_no_teamid(self):
        captured = {}

        def side_effect(url, *args, **kwargs):
            captured["url"] = url
            return _ctx({"dates": [{"date": "2027-03-26"}]})

        session = mock.MagicMock()
        session.get.side_effect = side_effect
        widget = make_widget(session=session)  # league
        await widget._set_no_games_state(TODAY)
        assert widget.feed_stories[0].text == "Next games: Mar 26"
        assert "teamId" not in captured["url"]


class TestStartTeamMode:
    async def test_team_mode_resolves_team_id(self):
        import led_ticker_baseball.statcast as mod
        from led_ticker_baseball.statcast import MLBStatcastMonitor

        routes = {
            "/teams": {"teams": [{"id": 143, "abbreviation": "PHI"}]},
            "sportId=1&date=": {"dates": []},
            "statcast_search": make_csv(),
            "startDate": {"dates": []},
        }
        session = make_session(routes)
        spawn = mock.Mock()
        loop = mock.Mock(return_value="LOOP")
        with (
            mock.patch.object(mod, "spawn_tracked", spawn),
            mock.patch.object(mod, "run_monitor_loop", loop),
        ):
            w = await MLBStatcastMonitor.start(session, team="phi", update_interval=55)
        assert w.team == "PHI"
        assert w._team_id == 143
        spawn.assert_called_once_with("LOOP")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_statcast.py -k "TeamAware or StartTeamMode" -v`
Expected: FAIL — probe has no `teamId`/`Next game` branch; `start()` never resolves `_team_id`.

- [ ] **Step 3: Implement**

In `statcast.py`:

(a) Add `resolve_team_id` to the teams import:

```python
from led_ticker_baseball.teams import MLB_API, _team_color, resolve_team_id
```

(b) In `start()`, resolve the team id when `team` is set (insert after `widget._tz = …`):

```python
        widget = cls(session=session, **kwargs)
        widget._tz = ZoneInfo(widget.timezone)
        if widget.team:  # upper-cased by the field converter
            widget._team_id = await resolve_team_id(session, widget.team) or 0
        await widget.update()
```

(c) Make `_set_no_games_state` team-aware — replace its URL line and text branch:

```python
    async def _set_no_games_state(self, today: date) -> None:
        """Off-day / offseason: probe 30 days for the next game date.

        Team mode names the next game (``teamId``-scoped); league mode names the
        next slate. A failed probe degrades to 'No games soon' silently.
        """
        start = today.isoformat()
        end = (today + timedelta(days=30)).isoformat()
        team_q = f"&teamId={self._team_id}" if self._team_id else ""
        url = (
            f"{MLB_API}/schedule?sportId=1&startDate={start}&endDate={end}"
            f"&gameType=R{team_q}"
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
        if next_date is None:
            text = "No games soon"
        elif self.team:
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

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_statcast.py -q`
Expected: all PASS.

- [ ] **Step 5: Run full gates and commit**

```bash
uv run pytest -q && uv run ruff check src tests && uv run ruff format --check src tests && uv run pyright src
git add src/led_ticker_baseball/statcast.py tests/test_statcast.py
git commit -m "feat: statcast team-id resolution + team-aware no-games probe"
```

---

### Task 4: `validate_config` team check

**Files:**
- Modify: `src/led_ticker_baseball/statcast.py`
- Modify: `tests/test_statcast.py`

- [ ] **Step 1: Write the failing tests**

Append to the existing `TestValidateConfig` class in `tests/test_statcast.py` (or as new methods alongside it):

```python
class TestValidateConfigTeam:
    def _validate(self, cfg):
        from led_ticker_baseball.statcast import MLBStatcastMonitor

        return MLBStatcastMonitor.validate_config(cfg)

    def test_string_team_passes(self):
        assert self._validate({"team": "PHI"}) == []

    def test_non_string_team_rejected(self):
        msgs = self._validate({"team": 42})
        assert len(msgs) == 1
        assert "team" in msgs[0]

    def test_team_plus_stats_passes(self):
        assert self._validate({"team": "PHI", "stats": ["longest_hr"]}) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_statcast.py -k ValidateConfigTeam -v`
Expected: FAIL — `validate_config` does not check `team`.

- [ ] **Step 3: Implement**

In `validate_config`, add the team check at the top (before the `stats` handling):

```python
        msgs: list[str] = []
        team = cfg.get("team")
        if team is not None and not isinstance(team, str):
            msgs.append(f"statcast team={team!r} must be a string abbreviation.")
        stats = cfg.get("stats")
        if stats is None:
            return msgs
```

(The rest of `validate_config` — the `stats` list/key checks — is unchanged; `team` messages accumulate into the same `msgs` list and are returned alongside any `stats` messages.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_statcast.py -q`
Expected: all PASS.

- [ ] **Step 5: Run full gates and commit**

```bash
uv run pytest -q && uv run ruff check src tests && uv run ruff format --check src tests && uv run pyright src
git add src/led_ticker_baseball/statcast.py tests/test_statcast.py
git commit -m "feat: statcast validate_config rejects non-string team"
```

---

### Task 5: Docs + final verification

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: README — intro + statcast section**

In `README.md`, in the `### baseball.statcast` section: update the opening
sentence to note the optional team scope, add a `team` row to the options
table, and add a team-mode line-format example.

Update the section's first sentence to:

```markdown
League-wide daily Statcast superlatives — the longest home run, hardest-hit
ball, and fastest/slowest pitch across all of MLB — or, with a `team` set, the
same superlatives scoped to that team's own players.
```

Add this row to the options table, immediately above the `stats` row:

```markdown
| `team` | string | unset | Scope superlatives to this team's own players (e.g. a Phillies batter for `longest_hr`, a Phillies pitcher for `fastest_pitch`). Omit for league-wide. Case-insensitive — see [Team codes](#team-codes). |
```

After the existing league-mode line-format example, add:

```markdown
With a team set, lines lead with the team abbreviation in its brand color and
drop the (now-redundant) trailing one:
`PHI Today · Longest HR 472 ft — Schwarber`. The off-day fallback then names
the team's next game (`Next game: Jun 20`) rather than the league slate.
```

- [ ] **Step 2: CLAUDE.md — statcast overview bullet**

In `CLAUDE.md`, update the `baseball.statcast` overview bullet to mention the
optional team scope. Change it to:

```markdown
- `baseball.statcast` — daily Statcast superlatives (longest HR, hardest hit,
  fastest/slowest pitch), league-wide or scoped to one team's players via an
  optional `team`; from Baseball Savant's day CSV, schedule-gated.
```

- [ ] **Step 3: Final verification — all gates + coverage**

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run pyright src
uv run pytest -q
uv run pytest --cov=src --cov-report=term-missing
```

Expected: lint/format/pyright clean; suite green; coverage ≥ 90% overall;
`statcast.py` high (the new team branches are covered by Tasks 1–4).

- [ ] **Step 4: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: baseball.statcast team filter (README + CLAUDE.md)"
```

---

## Spec coverage self-check (for the reviewer)

- Client-side row filter, own-players semantics (batter/pitcher side) → Task 1
- `team` field + upper-case converter; `_derive_day` passes it → Task 1
- Team-mode line format (lead abbr in brand color, drop trailing, keep pitch suffix, name-degrade); league unchanged → Task 2
- `_team_id` resolution in `start()`; team-aware probe (`Next game` + `teamId` vs `Next games`) → Task 3
- `validate_config` rejects non-string `team`; `team`+`stats` valid → Task 4
- README + CLAUDE.md → Task 5
- League-mode regression guarded throughout (Task 1 `test_empty_team_is_league_wide`, Task 2 `test_league_line_unchanged`, Task 3 league probe test, existing suite)
- Savant ATH/AZ normalization in the filter (reuses `_row_team`) → Task 1 `test_savant_abbr_normalized_in_filter`
