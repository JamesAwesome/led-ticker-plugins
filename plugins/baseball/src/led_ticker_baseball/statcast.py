"""MLB Statcast superlatives widget — league-wide or scoped to one team.

Derives the day's longest home run, hardest-hit ball, and fastest/slowest
pitch from Baseball Savant's day CSV — an undocumented website endpoint, so
requests carry a User-Agent and the default refresh is a polite 30 minutes,
gated on the (tiny) StatsAPI day schedule so off-hours refreshes skip the
pull. With ``team`` set, the CSV is scoped server-side to that team's games
and the superlatives to its own players. Stateless: every refresh re-derives
from the full day so far.
"""

import csv
import io
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Self
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
    make_color,
    run_monitor_loop,
    spawn_tracked,
)

from led_ticker_baseball.teams import (
    API_TO_CANONICAL_ABBR,
    MLB_API,
    _team_color,
    resolve_team_id,
)

logger: logging.Logger = logging.getLogger(__name__)

SAVANT_CSV_URL: str = (
    "https://baseballsavant.mlb.com/statcast_search/csv"
    "?all=true&type=details&game_date_gt={day}&game_date_lt={day}"
)
_USER_AGENT: str = (
    "led-ticker-baseball (+https://github.com/JamesAwesome/led-ticker-baseball)"
)
# Cap the ~3 MB Savant pull well under aiohttp's 300 s default; a timeout
# degrades cleanly to the "No Data" state via update()'s except block.
_SAVANT_TIMEOUT_S: int = 30

_INTERVAL_THIRTY_MIN: int = 1800

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
    """Float column value; None when missing, blank, or malformed.

    A ``"0"`` string is a valid reading and returns ``0.0``. (Savant CSV
    values are always strings via DictReader, so the falsy-zero edge of the
    ``or ""`` guard only applies to a literal int/float 0, which CSV rows
    never carry.)
    """
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
    team = team or ""
    # Savant emits ATH/AZ; normalize to the plugin's canonical OAK/ARI so the
    # filter, team color, and config code all agree (single map in teams.py).
    return API_TO_CANONICAL_ABBR.get(team, team)


def _format_value(key: str, value: float) -> str:
    """'463 ft' for the HR distance, '101.8 mph' for speeds."""
    if key == "longest_hr":
        return f"{round(value)} ft"
    return f"{value:.1f} mph"


@dataclass(frozen=True)
class StatRecord:
    value: float
    person_id: int
    team_abbr: str
    pitch_name: str = ""


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


@attrs.define
class MLBStatcastMonitor:
    """Daily Statcast superlatives — league-wide, or scoped to one team's
    players via an optional ``team``."""

    session: aiohttp.ClientSession
    # "" → league-wide; else scope superlatives to that team's own players.
    # Upper-cased at construction so the abbr matches the API on any build path.
    team: str = attrs.field(default="", converter=lambda v: v.upper() if v else "")
    stats: list[str] = attrs.field(factory=lambda: list(_STAT_KEYS))
    title: str = "Statcast"
    timezone: str = "America/New_York"
    padding: int = 6
    hold_time: float = 0.0
    bg_color: Color | None = attrs.field(default=None, kw_only=True)
    font_color: Color | ColorProvider | None = attrs.field(default=None, kw_only=True)
    font: Font = attrs.field(default=FONT_DEFAULT, kw_only=True)
    _tz: ZoneInfo | None = attrs.field(init=False, default=None)
    _team_id: int = attrs.field(init=False, default=0)
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

    @classmethod
    def validate_config(cls, cfg: dict[str, Any]) -> list[str]:
        """Pre-coercion config check, run by the engine via validate_widget_cfg.

        Returns message strings (does NOT raise); the engine turns any
        returned messages into a pre-flight ValueError. Same contract as the
        sibling widgets.
        """
        msgs: list[str] = []
        team = cfg.get("team")
        if team is not None and not isinstance(team, str):
            msgs.append(f"statcast team={team!r} must be a string abbreviation.")
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
                f"statcast stats contains unknown key(s) {names}. Valid keys: {valid}."
            )
        return msgs

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
        if widget.team:  # upper-cased by the field converter
            widget._team_id = await resolve_team_id(session, widget.team) or 0
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
                yesterday = today - timedelta(days=1)
                records = await self._derive_day(yesterday)
                label = yesterday.strftime("%-m/%-d")  # e.g. "6/12"
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
        if self.team:
            # Scope the pull to the team's games server-side (~24x smaller).
            # The CSV still includes the opponent's rows, so the client-side
            # _row_team filter in _derive_records stays necessary and correct.
            url += f"&hfTeam={self.team}%7C"
        async with self.session.get(
            url,
            headers={"User-Agent": _USER_AGENT},
            timeout=aiohttp.ClientTimeout(total=_SAVANT_TIMEOUT_S),
        ) as resp:
            # Savant is undocumented and rate-limits; aiohttp does not raise on
            # 4xx/5xx, so an HTML error page or "Too Many Requests" body would
            # otherwise parse to zero rows and masquerade as an off-day. Raise
            # instead so update() routes it to the "No Data" error state, per
            # this method's contract.
            resp.raise_for_status()
            text = await resp.text()
        rows = list(csv.DictReader(io.StringIO(text.lstrip("﻿"))))
        return _derive_records(rows, self.stats, self.team)

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
        # Gate the label on the SAME condition as the teamId query (_team_id),
        # not on self.team — so a team whose id failed to resolve degrades
        # honestly to the league "Next games" instead of mislabeling a
        # league-wide date as the team's "Next game".
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
