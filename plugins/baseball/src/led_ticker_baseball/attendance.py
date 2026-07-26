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
from dataclasses import dataclass, replace
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

from led_ticker_baseball._attendance_card import MLBAttendanceCard
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
    fill_frac: float = 0.0  # attendance/capacity, 0.0 when capacity is 0/missing
    attendance: int = 0  # raw attendance for this record, regardless of is_pct
    capacity: int = 0  # venue capacity for this record, 0 when unlisted


@dataclass(frozen=True)
class AttendanceGame:
    paid: int | None
    capacity: int
    avg: int | None  # attendanceAverageHome; None when missing (early season)
    venue: str
    home_abbr: str
    # Game-day weather for the long-card's dead-zone readout (task-5); both
    # default "" so existing construction (and league mode, which never sets
    # these) is unaffected. Pre-formatted degree string ("72°"), not a raw
    # number — the layout draws it verbatim, no further formatting.
    temp: str = ""
    condition: str = ""


# `demo = true` fixture data — a curated docs-showcase / on-demand
# hardware-validation slate (see the sibling fixture blocks in scores.py /
# standings.py / promotions.py / statcast.py). Frozen dataclasses — safe to
# share as module-level constants (nothing mutates these in place).
#
# The team fixture (`DEMO_GAME_VENUE` + `DEMO_ATTENDANCE_*`) shows every
# element the long-card layout can draw: paid attendance, capacity, a season
# average (for the VS AVG tick), venue + home team, and temp/condition (the
# weather line). The league fixture (`DEMO_CROWD_RECORDS`) covers exactly
# `biggest_crowd` + `fullest` — see `_load_demo`'s docstring for why the
# demo shows a fixed pair rather than every configured `stats` entry.
DEMO_GAME_VENUE: GameVenue = GameVenue(
    game_pk=0,
    state="Final",
    game_number=1,
    home_abbr="NYY",
    away_abbr="BOS",
    venue="Yankee Stadium",
    capacity=46_537,
)
DEMO_ATTENDANCE_PAID: int = 42_313
DEMO_ATTENDANCE_AVG: int = 39_850
DEMO_ATTENDANCE_WEATHER: dict[str, Any] = {
    "temp": "72",
    "condition": "Clear",
    "wind": "5 mph, Out To CF",
}
DEMO_CROWD_RECORDS: dict[str, CrowdRecord] = {
    "biggest_crowd": CrowdRecord(
        value=54_120,
        venue="Dodger Stadium",
        home_abbr="LAD",
        is_pct=False,
        fill_frac=54_120 / 56_000,
        attendance=54_120,
        capacity=56_000,
    ),
    "fullest": CrowdRecord(
        value=99,
        venue="Fenway Park",
        home_abbr="BOS",
        is_pct=True,
        fill_frac=0.99,
        attendance=37_354,
        capacity=37_731,
    ),
}


def _derive_superlatives(
    pairs: list[tuple[GameVenue, int]], stats: list[str]
) -> dict[str, CrowdRecord]:
    """Best record per requested superlative over (game, attendance) pairs.

    Crowd stats use raw attendance over all pairs; fullest/emptiest use
    attendance/capacity over pairs with capacity > 0. Strict comparisons keep
    the first pair on ties (schedule order).
    """
    records: dict[str, CrowdRecord] = {}

    def consider(key: str, value: int, gv: GameVenue, att: int, *, lower: bool) -> None:
        cur = records.get(key)
        if cur is not None and (value >= cur.value if lower else value <= cur.value):
            return
        is_pct = key in ("fullest", "emptiest")
        fill = (
            (value / 100.0) if is_pct else (att / gv.capacity if gv.capacity else 0.0)
        )
        records[key] = CrowdRecord(
            value=value,
            venue=gv.venue,
            home_abbr=gv.home_abbr,
            is_pct=is_pct,
            fill_frac=fill,
            attendance=att,
            capacity=gv.capacity,
        )

    for gv, att in pairs:
        if "biggest_crowd" in stats:
            consider("biggest_crowd", att, gv, att, lower=False)
        if "smallest_crowd" in stats:
            consider("smallest_crowd", att, gv, att, lower=True)
        pct = _fill_pct(att, gv.capacity)
        if pct is not None:
            if "fullest" in stats:
                consider("fullest", pct, gv, att, lower=False)
            if "emptiest" in stats:
                consider("emptiest", pct, gv, att, lower=True)
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
    demo: bool = False
    # Card layout at scale > 1 ("auto" picks big/long by physical width); at
    # scale <= 1 every layout forwards verbatim to the legacy line, so this
    # field is a no-op on smallsign. Validated in validate_config below.
    layout: str = "auto"
    # "show" (default) renders the no-attendance state (a team game not yet
    # Final, or an off day) as a hires fallback line at scale>1 / legacy BDF
    # at scale<=1; "hide" drops the widget from the rotation instead
    # (`feed_stories = []`) until real attendance data (or a game) arrives.
    # Validated in validate_config below.
    no_data: str = "show"
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
    feed_stories: list[TickerMessage | SegmentMessage | MLBAttendanceCard] = (
        attrs.field(init=False, factory=list)
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

    def _build_league_cards(
        self, records: dict[str, CrowdRecord], day_label: str
    ) -> list[TickerMessage | SegmentMessage | MLBAttendanceCard]:
        """One MLBAttendanceCard per superlative, wrapping its legacy line.

        `_build_league_stories` builds the legacy `SegmentMessage` lines in
        `self.stats` display order (record-present filtering already applied
        there); this pairs each line back up with its record so scale>1 can
        render the hero card while scale<=1 forwards verbatim to the legacy
        line (see `MLBAttendanceCard.draw`).
        """
        lines = self._build_league_stories(records, day_label)
        ordered = [k for k in self.stats if k in records]
        total = len(ordered)
        cards: list[TickerMessage | SegmentMessage | MLBAttendanceCard] = []
        for idx, (key, legacy) in enumerate(zip(ordered, lines, strict=True)):
            cards.append(
                MLBAttendanceCard(
                    record=records[key],
                    legacy=legacy,
                    label=_STAT_LABELS[key].upper(),
                    story_index=idx,
                    story_total=total,
                    cfg_layout=self.layout,
                    bg_color=self.bg_color,
                    font_color=self.font_color,
                )
            )
        return cards

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

    def _build_team_fallback_text(self, *, venue: str, day_label: str) -> str:
        """Plain-text no-attendance fallback line: reuses `_build_team_line`
        (attendance and weather both explicitly omitted — attendance is None
        in this state anyway, and dropping weather keeps the hires fallback
        line short) so the day_label/team/venue formatting can't drift from
        the legacy line's own."""
        line = self._build_team_line(
            venue=venue, attendance=None, capacity=0, weather=None, day_label=day_label
        )
        return "".join(seg for seg, _color in line.segments)

    def _build_team_card_from_avg(
        self,
        *,
        game_venue: GameVenue,
        att: int | None,
        cap: int,
        weather: dict[str, Any] | None,
        day_label: str,
        avg: int | None,
    ) -> MLBAttendanceCard:
        """Sync half of `_build_team_card`: build the card given an
        ALREADY-RESOLVED season average.

        Split out so `_load_demo()` can supply a fixture average without
        awaiting `_fetch_season_avg()` (a network call) — that's the ONLY
        difference between the demo and live paths; every other kwarg and
        the card construction itself is shared here, so there's no
        duplicated rendering logic to drift between the two.
        """
        legacy = self._build_team_line(
            venue=game_venue.venue,
            attendance=att,
            capacity=cap,
            weather=weather,
            day_label=day_label,
        )
        w = weather or {}
        temp_raw = w.get("temp")
        record = AttendanceGame(
            paid=att,
            capacity=cap,
            avg=avg,
            venue=game_venue.venue,
            home_abbr=game_venue.home_abbr,
            temp=f"{temp_raw}°" if temp_raw else "",
            condition=w.get("condition") or "",
        )
        return MLBAttendanceCard(
            record=record,
            legacy=legacy,
            cfg_layout=self.layout,
            bg_color=self.bg_color,
            font_color=self.font_color,
            fallback_text=self._build_team_fallback_text(
                venue=game_venue.venue, day_label=day_label
            ),
            fallback_color=self._plain_body_color(),
        )

    async def _build_team_card(
        self,
        *,
        game_venue: GameVenue,
        att: int | None,
        cap: int,
        weather: dict[str, Any] | None,
        day_label: str,
    ) -> MLBAttendanceCard:
        """The tracked team's single game, wrapped for scale-dispatch.

        Fetches the season average, then delegates the actual card
        construction to `_build_team_card_from_avg` (shared with
        `_load_demo()`). The caller resolves `game_venue.venue` to the live
        feed's venue name when present (mirroring the existing
        `venue or game.venue` fallback) — this method just reads it off
        `game_venue`.
        """
        avg = await self._fetch_season_avg()
        return self._build_team_card_from_avg(
            game_venue=game_venue,
            att=att,
            cap=cap,
            weather=weather,
            day_label=day_label,
            avg=avg,
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

    async def _fetch_season_avg(self) -> int | None:
        """Team's home-crowd season average (records[0].attendanceAverageHome).

        None on failure/missing. NOTE: the prototype's `attendanceAverage`
        field does not exist (verified 2026-07-20) — this is the correct one.
        """
        if not self._team_id:
            return None
        season = datetime.now(self._tz or ZoneInfo(self.timezone)).year
        url = f"{MLB_API}/attendance?teamId={self._team_id}&season={season}"
        try:
            async with self.session.get(url) as resp:
                data = await resp.json()
        except Exception:
            return None
        recs = data.get("records") or []
        if not recs:
            return None
        avg = recs[0].get("attendanceAverageHome")
        return avg if isinstance(avg, int) else None

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
        The 30-day probe lives in ``teams.next_game_date``. ``no_data="hide"``
        drops the widget entirely (``feed_stories = []``) instead of showing
        this line.
        """
        next_date = await next_game_date(self.session, today, team_id=self._team_id)
        if next_date is None:
            text = "No games soon"
        elif self._team_id:
            text = f"Next game: {next_date.strftime('%b %-d')}"
        else:
            text = f"Next games: {next_date.strftime('%b %-d')}"
        if self.no_data == "hide":
            self.feed_stories = []
            logger.info("MLB Attendance updated: hidden (no_data=hide, %s)", text)
            return
        # Wrapped in MLBAttendanceCard so the line renders hires at scale>1
        # (the card's no-attendance fallback path) rather than the block-
        # scaled BDF a bare TickerMessage would draw; a minimal `paid=None`
        # AttendanceGame is enough to make `_has_attendance` false.
        self.feed_stories = [
            MLBAttendanceCard(
                record=AttendanceGame(
                    paid=None, capacity=0, avg=None, venue="", home_abbr=""
                ),
                legacy=TickerMessage(
                    text,
                    font_color=self._body_color(),
                    center=True,
                    bg_color=self.bg_color,
                ),
                cfg_layout=self.layout,
                bg_color=self.bg_color,
                font_color=self.font_color,
                fallback_text=text,
                fallback_color=self._body_color(),
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

        # `team` is optional (league mode is a fully supported mode already),
        # so unlike scores/standings/promotions there is no "required unless
        # demo" rule here — `demo` just needs to be a bool.
        demo = cfg.get("demo")
        if demo is not None and not isinstance(demo, bool):
            msgs.append(
                f"baseball.attendance demo must be a bool (true/false), got {demo!r}"
            )

        layout = cfg.get("layout", "auto")
        if layout not in ("auto", "big", "long"):
            msgs.append(
                f"attendance layout={layout!r} is not valid. "
                "Use 'auto', 'big', or 'long'."
            )

        no_data = cfg.get("no_data", "show")
        if no_data not in ("show", "hide"):
            msgs.append(
                f"attendance no_data={no_data!r} is not valid. Use 'show' or 'hide'."
            )

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
        if widget.demo:
            widget._load_demo()
            return widget
        if widget.team:  # already upper-cased by the field converter
            widget._team_id = await resolve_team_id(session, widget.team) or 0
        await widget.update()
        logger.info("MLB Attendance: %d stories", len(widget.feed_stories))
        spawn_tracked(run_monitor_loop(widget, update_interval))
        return widget

    def _load_demo(self) -> None:
        """Populate feed_stories with BOTH a team fixture card and league
        superlative cards — no network fetch (no schedule/boxscore/season-avg
        fetch of any kind).

        Regardless of whether `team` is configured (team mode) or left blank
        (league mode), demo always shows BOTH shapes in one rotation so a
        single `demo = true` widget showcases the full card surface —
        `[title, team_card, biggest_crowd_card, fullest_card]`.

        Reuses the SAME builders `update()` uses: `_build_team_card_from_avg`
        (the sync half of `_build_team_card`, split out specifically so demo
        can supply a fixture season average instead of awaiting
        `_fetch_season_avg()`) for the team card, and `_build_league_cards`
        for the league cards — so demo cards render through the SAME
        renderers real attendance data does. `_build_league_cards` filters by
        `self.stats`, so `DEMO_CROWD_RECORDS` (fixed to `biggest_crowd` +
        `fullest`) only surfaces the subset also present in `self.stats` —
        same "missing stat omitted" behavior as live data.
        """
        self._set_title()
        team_card = self._build_team_card_from_avg(
            game_venue=DEMO_GAME_VENUE,
            att=DEMO_ATTENDANCE_PAID,
            cap=DEMO_GAME_VENUE.capacity,
            weather=dict(DEMO_ATTENDANCE_WEATHER),
            day_label="",
            avg=DEMO_ATTENDANCE_AVG,
        )
        league_cards = self._build_league_cards(dict(DEMO_CROWD_RECORDS), "Today")
        self.feed_stories = [team_card, *league_cards]
        logger.info("MLB Attendance demo: %d stories", len(self.feed_stories))

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
            self.feed_stories = self._build_league_cards(records, "Today")
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
            self.feed_stories = self._build_league_cards(records, label)
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
            card = await self._build_team_card(
                game_venue=replace(game, venue=venue or game.venue),
                att=att,
                cap=cap or game.capacity,
                weather=weather,
                day_label="",
            )
            # "hide" drops the widget from the rotation while attendance is
            # still unknown (att is None) instead of showing the fallback
            # line; once att is known the hero card always shows.
            self.feed_stories = (
                [] if (self.no_data == "hide" and att is None) else [card]
            )
            logger.info("MLB Attendance updated: team %s (today)", self.team)
            # A Final game with no announced crowd yet → keep polling for it.
            return not (game.state == "Final" and att is None)

        # No game today → yesterday's game is the stable answer for the day.
        yest = today - timedelta(days=1)
        ygames, _ = await self._fetch_schedule(yest)
        ygame = self._pick_team_game(ygames or [])
        if ygame is not None:
            att, weather, venue, cap = await self._fetch_game_data(ygame.game_pk)
            card = await self._build_team_card(
                game_venue=replace(ygame, venue=venue or ygame.venue),
                att=att,
                cap=cap or ygame.capacity,
                weather=weather,
                day_label=yest.strftime("%-m/%-d"),
            )
            self.feed_stories = (
                [] if (self.no_data == "hide" and att is None) else [card]
            )
            logger.info("MLB Attendance updated: team %s (%s)", self.team, yest)
            return True
        await self._set_no_games_state(today)
        return True
