"""MLB ballpark attendance widget — league superlatives + team mode.

Two modes (chosen by whether ``team`` is configured): league-wide daily
attendance superlatives (biggest/smallest crowd, fullest/emptiest park by
capacity %), or one tracked team's game (attendance + fill % + venue + weather).
All data is from the StatsAPI the plugin already uses; attendance exists only
once a game is Final (schedule has venue/capacity/state, the live feed has
weather, the boxscore carries the attendance string). Stateless: every refresh
re-derives, schedule-gated so off-hours ticks are cheap.
"""

import asyncio
import logging
import re
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
    _MLB_LIVE_API,
    API_TO_CANONICAL_ABBR,
    MLB_API,
    _team_color,
    next_game_date,
    resolve_team_id,
)

logger: logging.Logger = logging.getLogger(__name__)

_INTERVAL_THIRTY_MIN: int = 1800

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
    # MLB encodes wind as "<speed>, <direction>"; a closed roof or dead calm
    # sends the literal "None" as the direction ("0 mph, None"). Strip it so
    # the line doesn't trail off with ", None".
    wind = (weather.get("wind") or "").removesuffix(", None").strip()
    # Build from whatever is present: "72° Clear", "72°", or "Clear".
    head = " ".join(p for p in (f"{temp}°" if temp else "", condition or "") if p)
    if not head:
        return None
    return f"{head}, wind {wind}" if wind else head


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
            home_raw = home.get("abbreviation", "")
            away_raw = away.get("abbreviation", "")
            games.append(
                GameVenue(
                    game_pk=g.get("gamePk", 0),
                    state=g.get("status", {}).get("abstractGameState", "Preview"),
                    game_number=g.get("gameNumber", 1),
                    home_abbr=(API_TO_CANONICAL_ABBR.get(home_raw) or home_raw),
                    away_abbr=(API_TO_CANONICAL_ABBR.get(away_raw) or away_raw),
                    venue=venue.get("name", ""),
                    capacity=venue.get("fieldInfo", {}).get("capacity", 0) or 0,
                )
            )
    return games


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


@attrs.define
class MLBAttendanceMonitor:
    """Ballpark attendance — league superlatives, or one team's game."""

    session: aiohttp.ClientSession
    # "" → league mode; else team mode. Upper-cased at construction so the
    # abbreviation matches the API regardless of how the widget is built
    # (config coercion, start(), or a direct constructor in tests).
    team: str = attrs.field(default="", converter=lambda v: v.upper() if v else "")
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

    def _fmt_value(self, rec: CrowdRecord) -> str:
        return f"{rec.value}%" if rec.is_pct else f"{rec.value:,}"

    def _build_league_stories(
        self, records: dict[str, CrowdRecord], day_label: str
    ) -> list[TickerMessage | SegmentMessage]:
        """One centered line per superlative.

        Format: 'Today · Biggest crowd 45,123 — Dodger Stadium'. Day label
        grey, value amber, venue in the home team's brand color. ``self.stats``
        order is display order; missing stats are omitted.
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

    # Contract: the _set_*_state setters manage feed_stories only. update()
    # calls _set_title() first, so feed_title is always set, including on error.

    def _set_error_state(self) -> None:
        self.feed_stories = [
            TickerMessage(
                "No Data", font_color=self._body_color(), bg_color=self.bg_color
            ),
        ]
        logger.info(
            "MLB Attendance updated: %d stories (no data)", len(self.feed_stories)
        )

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
                text, font_color=self._body_color(), center=True, bg_color=self.bg_color
            ),
        ]
        logger.info("MLB Attendance updated: fallback (%s)", text)

    def _pick_team_game(self, games: list[GameVenue]) -> GameVenue | None:
        """The tracked team's game for the day. Doubleheader rule: a Live game
        wins; else the latest *Final* game (so a completed game 1 is not
        masked by an unplayed game 2); else the latest scheduled game."""
        mine = [g for g in games if self.team in (g.home_abbr, g.away_abbr)]
        if not mine:
            return None
        live = [g for g in mine if g.state == "Live"]
        if live:
            return live[0]
        finals = [g for g in mine if g.state == "Final"]
        pool = finals or mine
        return max(pool, key=lambda g: g.game_number)

    async def _league_pairs(
        self, games: list[GameVenue]
    ) -> list[tuple[GameVenue, int]]:
        """Concurrent boxscore fetches for Final games; (game, attendance)
        pairs, skipping games with no announced attendance."""
        finals = [g for g in games if g.state == "Final"]
        atts = await asyncio.gather(
            *(self._fetch_attendance(g.game_pk) for g in finals)
        )
        return [(g, a) for g, a in zip(finals, atts, strict=True) if a is not None]

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
            stats_valid = isinstance(stats, list) and all(
                isinstance(s, str) for s in stats
            )
            if not stats_valid:
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
        # NOTE: `stats` alongside `team` is NOT flagged. The engine turns any
        # returned message into a fatal pre-flight ValueError, so a "warning"
        # here would reject an otherwise-valid config; team mode simply ignores
        # `stats` at runtime (documented in the README).
        return msgs

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
        if widget.team:  # already upper-cased by the field converter
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
                stable = await self._update_team(today, games)
            else:
                stable = await self._update_league(today, games)
        except Exception:
            logger.exception("MLB Attendance fetch/derive error")
            self._last_derive = None
            self._set_error_state()
            return

        # Snapshot the gate key only when the rendered result is STABLE for the
        # rest of the polling window. The sub-updates return False when today
        # still has data pending (a Final whose attendance hasn't been
        # announced yet, or games not yet final) so the gate keeps re-deriving
        # — attendance lands AFTER a game goes Final, so the Final-count gate
        # alone would otherwise mask today's attendance behind the yesterday
        # fallback all day once the count stops changing.
        self._last_derive = (today, counts[1]) if (stable and counts) else None

    async def _update_league(self, today: date, games: list[GameVenue] | None) -> bool:
        """Render league superlatives. Returns whether the result is stable
        (safe to gate-skip) vs. transient (today still owes attendance)."""
        today_games = games or []
        finals_today = [g for g in today_games if g.state == "Final"]
        pairs = await self._league_pairs(today_games)
        if pairs:
            records = _derive_superlatives(pairs, self.stats)
            self.feed_stories = self._build_league_stories(records, "Today")
            logger.info(
                "MLB Attendance updated: %d stories (Today)", len(self.feed_stories)
            )
            # Keep polling if some of today's Finals haven't reported a crowd yet.
            return len(pairs) >= len(finals_today)

        # No attendance for today yet — fall back to yesterday's slate.
        yest = today - timedelta(days=1)
        ygames, _ = await self._fetch_schedule(yest)
        ypairs = await self._league_pairs(ygames or [])
        if ypairs:
            records = _derive_superlatives(ypairs, self.stats)
            label = yest.strftime("%-m/%-d")
            self.feed_stories = self._build_league_stories(records, label)
            logger.info(
                "MLB Attendance updated: %d stories (%s)", len(self.feed_stories), label
            )
            # If today has games, their attendance is still pending → keep polling.
            return not today_games
        await self._set_no_games_state(today)
        return not today_games

    async def _update_team(self, today: date, games: list[GameVenue] | None) -> bool:
        """Render the tracked team's game line. Returns whether the result is
        stable (safe to gate-skip)."""
        game = self._pick_team_game(games or [])
        if game is not None:
            att, weather, venue, cap = await self._fetch_game_data(game.game_pk)
            self.feed_stories = [
                self._build_team_line(
                    venue=venue or game.venue,
                    attendance=att,
                    capacity=cap or game.capacity,
                    weather=weather,
                    day_label="",
                )
            ]
            logger.info("MLB Attendance updated: team %s (today)", self.team)
            # A Final game with no announced crowd yet → keep polling for it.
            return not (game.state == "Final" and att is None)

        # No game today → yesterday's game is the stable answer for the day.
        yest = today - timedelta(days=1)
        ygames, _ = await self._fetch_schedule(yest)
        ygame = self._pick_team_game(ygames or [])
        if ygame is not None:
            att, weather, venue, cap = await self._fetch_game_data(ygame.game_pk)
            self.feed_stories = [
                self._build_team_line(
                    venue=venue or ygame.venue,
                    attendance=att,
                    capacity=cap or ygame.capacity,
                    weather=weather,
                    day_label=yest.strftime("%-m/%-d"),
                )
            ]
            logger.info("MLB Attendance updated: team %s (%s)", self.team, yest)
            return True
        await self._set_no_games_state(today)
        return True
