"""MLB standings widget using the free MLB Stats API."""

import contextlib
import difflib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
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
    run_monitor_loop,
    spawn_tracked,
)

from led_ticker_baseball._standings_card import MLBStandingsBoard
from led_ticker_baseball.teams import (
    API_TO_CANONICAL_ABBR,
    MLB_API,
    MLB_NAME_TO_ABBR,
    _team_color_by_name,
)

logger: logging.Logger = logging.getLogger(__name__)

_INTERVAL_DAILY: int = 86400

# Supported story shapes for MLBStandingsMonitor.layout. "ticker" builds the
# original per-team SegmentMessage rows (top_n + tracked teams not already in
# top_n). "auto"/"board" build one MLBStandingsBoard per tracked division
# instead — a held physical dashboard at scale>1, degrading to one legacy row
# per section visit at scale<=1 (see _standings_card.py). "auto" and "board"
# currently resolve identically here: the shape is decided by config, not by
# canvas (draw-time layout resolution — as MLBGameCard does per-story — has no
# aggregate-of-legacy-rows equivalent for a board that spans a whole
# division, so both names route through the same story-build path).
_STANDINGS_VALID_LAYOUTS: tuple[str, ...] = ("auto", "ticker", "board")

# Mirrors layouts/standings_board.py's own _MAX_ROWS/_MIN_ROWS — the
# `board_rows` config knob's valid range (validated in `validate_config`
# below). `MLBStandingsBoard.legacy_rows` (the scale<=1 fallback) is capped
# to the same `board_rows` count so it shows the same division slice the
# physical board renders, not the division's full roster.
_STANDINGS_BOARD_MAX_ROWS: int = 5
_STANDINGS_BOARD_MIN_ROWS: int = 3
_STANDINGS_BOARD_DEFAULT_ROWS: int = 5

# Static MLB division IDs -> display names. These are stable MLB Stats API
# constants (sportId=1, league 103/104) so a hydrate isn't needed to label
# division groupings.
DIVISION_NAMES: dict[int, str] = {
    200: "AL WEST",
    201: "AL EAST",
    202: "AL CENTRAL",
    203: "NL WEST",
    204: "NL EAST",
    205: "NL CENTRAL",
}


@dataclass
class TeamStanding:
    name: str  # API team name, e.g. "Mets", "Yankees"
    wins: int
    losses: int
    rank: int
    games_back: str  # "-" for leader, "3.0", "10.5", etc.
    abbr: str = ""  # canonical team abbreviation, e.g. "NYY"
    pct: str = ""  # API winning-percentage string, e.g. ".598"
    l10: str = ""  # last-10 record, e.g. "7-3"
    streak: str = ""  # streak code, e.g. "W3"
    division_rank: int = 99
    division_gb: str = "-"  # games back within division
    division_id: int = 0  # 0 == unknown/unset


def _group_by_division(
    standings: list[TeamStanding],
) -> dict[int, list[TeamStanding]]:
    """Group standings by division_id, each list sorted by division_rank.

    Excludes division_id 0 (unknown/unset).
    """
    groups: dict[int, list[TeamStanding]] = {}
    for standing in standings:
        if standing.division_id == 0:
            continue
        groups.setdefault(standing.division_id, []).append(standing)
    for teams in groups.values():
        teams.sort(key=lambda t: t.division_rank)
    return groups


def _select_division_rows(
    division_rows: list[TeamStanding],
    board_rows: int,
    tracked_abbrs: set[str],
) -> list[TeamStanding]:
    """Select up to `board_rows` rows from one division's team list
    (`division_rows`, already sorted by `division_rank` — see
    `_group_by_division`): the top `board_rows` by rank, then pin in any
    TRACKED team not already included by displacing rows from the BOTTOM
    of that top-N selection (division_rank order) — one displaced slot per
    missing tracked team. The rank digit the board shows is always the
    TRUE `division_rank` (a 1, 2, 5 board reads as self-explanatory), never
    a re-numbered 1..N.

    `board_rows=5` (the default) is a no-op versus the pre-#72 behavior
    whenever the division has <=5 teams (the common case: MLB divisions
    have 5 teams) — every team is already in the top-5 selection, so
    `missing` is always empty.

    Bounded to at most `len(selected)` (<= `board_rows`) missing tracked
    teams displacing existing rows, best-ranked first — a division with
    more tracked-but-unranked teams than board slots is not a case any
    real MLB division (5 teams per division) can hit, but this keeps the
    return value from ever exceeding `board_rows`.
    """
    selected = division_rows[:board_rows]
    selected_ids = {id(r) for r in selected}
    missing = [
        r
        for r in division_rows
        if r.abbr in tracked_abbrs and id(r) not in selected_ids
    ]
    if not missing:
        return selected

    missing.sort(key=lambda t: t.division_rank)
    budget = len(selected)
    missing = missing[:budget]
    keep = selected[: max(0, budget - len(missing))]
    final = keep + missing
    final.sort(key=lambda t: t.division_rank)
    return final


def _build_standing_message(
    standing: TeamStanding,
    bg_color: Color | None = None,
    font: Font | None = None,
    font_color: Color | ColorProvider | None = None,
) -> SegmentMessage:
    """Build a display message for a single team's standing."""
    team_c = _team_color_by_name(standing.name)

    gb_str = standing.games_back if standing.games_back != "-" else "-"

    segments: list[tuple[str, Any]] = [
        (f"{standing.rank}. ", colors.RGB_WHITE),
        (standing.name, team_c),
        (f" {standing.wins}-{standing.losses}", colors.RGB_WHITE),
        (f" {gb_str}", colors.RGB_WHITE),
    ]
    return SegmentMessage(
        segments, center=True, bg_color=bg_color, font=font, font_color=font_color
    )


@attrs.define
class MLBStandingsMonitor:
    """MLB overall standings showing top N teams and tracked teams."""

    session: aiohttp.ClientSession
    teams: list[str]
    title: str = "MLB Standings"
    top_n: int = 3
    timezone: str = "America/New_York"
    padding: int = 6
    hold_time: float = 0.0
    bg_color: Color | None = attrs.field(default=None, kw_only=True)
    font_color: Color | ColorProvider | None = attrs.field(default=None, kw_only=True)
    font: Font = attrs.field(default=FONT_DEFAULT, kw_only=True)
    layout: str = attrs.field(default="auto", kw_only=True)
    # Board layouts (`auto`/`board`) only — `layout = "ticker"` ignores this
    # and always shows the ticker's own top_n/tracked-team row shape.
    # Validated to 3-5 in `validate_config`; fewer rows scale text/chip up
    # (see layouts/standings_board.py's geometry table).
    board_rows: int = attrs.field(default=_STANDINGS_BOARD_DEFAULT_ROWS, kw_only=True)
    _tz: ZoneInfo | None = attrs.field(init=False, default=None)
    feed_title: TickerMessage | None = attrs.field(init=False, default=None)
    feed_stories: list[TickerMessage | SegmentMessage | MLBStandingsBoard] = (
        attrs.field(init=False, factory=list)
    )

    @classmethod
    def validate_config(cls, cfg: dict[str, Any]) -> list[str]:
        """Pre-coercion config check, run by the engine via validate_widget_cfg.

        Mirrors MLBScoreMonitor.validate_config's layout-value guardrail
        (see scores.py): a valid ``layout`` value, with a difflib
        suggestion for a near-miss. Returns message strings (does NOT
        raise); the engine turns any returned messages into a pre-flight
        ValueError.

        ``board_rows`` must be an int in 3..5 — bool is explicitly excluded
        even though it's an int subclass (mirrors core's `font_threshold`
        convention: `True`/`False` would silently coerce to 1/0, both
        outside range, but the exclusion is explicit rather than relying on
        the range check alone to document intent).
        """
        msgs: list[str] = []

        layout = cfg.get("layout", "auto")
        if layout not in _STANDINGS_VALID_LAYOUTS:
            close = difflib.get_close_matches(
                str(layout), _STANDINGS_VALID_LAYOUTS, n=1, cutoff=0.5
            )
            suggestion = f" Did you mean {close[0]!r}?" if close else ""
            valid = ", ".join(repr(v) for v in _STANDINGS_VALID_LAYOUTS)
            msgs.append(
                f"standings layout={layout!r} is not valid. "
                f"Choose one of: {valid}.{suggestion}"
            )

        if "board_rows" in cfg:
            board_rows = cfg["board_rows"]
            if (
                isinstance(board_rows, bool)
                or not isinstance(board_rows, int)
                or not (
                    _STANDINGS_BOARD_MIN_ROWS <= board_rows <= _STANDINGS_BOARD_MAX_ROWS
                )
            ):
                msgs.append(
                    f"standings board_rows={board_rows!r} is not valid. "
                    f"Must be an integer from {_STANDINGS_BOARD_MIN_ROWS} to "
                    f"{_STANDINGS_BOARD_MAX_ROWS}."
                )

        return msgs

    @classmethod
    async def start(
        cls,
        session: aiohttp.ClientSession,
        teams: list[str],
        update_interval: int = _INTERVAL_DAILY,
        **kwargs: Any,
    ) -> Self:
        logger.debug("MLBStandingsMonitor.start: teams=%s", teams)
        widget = cls(
            session=session,
            teams=[t.upper() for t in teams],
            **kwargs,
        )
        widget._tz = ZoneInfo(widget.timezone)
        await widget.update()
        logger.info(
            "MLB Standings: %d stories",
            len(widget.feed_stories),
        )
        spawn_tracked(run_monitor_loop(widget, update_interval))
        return widget

    async def update(self) -> None:
        """Fetch standings and build display messages."""
        tz = self._tz or ZoneInfo(self.timezone)
        now = datetime.now(tz)
        season = now.year

        url = (
            f"{MLB_API}/standings"
            f"?leagueId=103,104&season={season}"
            f"&standingsType=regularSeason"
        )

        try:
            async with self.session.get(url) as resp:
                data = await resp.json()
        except Exception:
            logger.exception("MLB Standings API error")
            self._set_error_state()
            return

        standings = self._parse_standings(data)
        if not standings:
            self._set_error_state()
            return

        # Season hasn't started yet — show opening day message
        if all(s.wins == 0 and s.losses == 0 for s in standings):
            await self._set_offseason_state()
            return

        title_color = (
            self.font_color if self.font_color is not None else colors.RGB_WHITE
        )
        self.feed_title = TickerMessage(
            self.title,
            font_color=title_color,
            center=True,
            bg_color=self.bg_color,
        )

        # Config uses abbreviations, so map API names back to abbrs for lookup.
        # Shared by both story shapes below.
        standings_by_abbr: dict[str, TeamStanding] = {}
        for s in standings:
            abbr = MLB_NAME_TO_ABBR.get(s.name, "")
            if abbr:
                standings_by_abbr[abbr] = s

        stories: list[TickerMessage | SegmentMessage | MLBStandingsBoard]
        if self.layout == "ticker":
            stories = self._build_ticker_stories(standings, standings_by_abbr)
        else:
            # "auto" / "board": one MLBStandingsBoard per tracked division.
            # Story SHAPE is decided by config only (see _STANDINGS_VALID_LAYOUTS
            # docstring) — both currently resolve identically here.
            stories = self._build_board_stories(standings, standings_by_abbr)
            if not stories:
                # Never blank the sign under the "auto" default: a
                # divisionless API response (division_id == 0 everywhere).
                # Tracked teams that fail to resolve fall back to the
                # overall leader's division board, not here.
                logger.info(
                    "standings: no divisions resolved; falling back to ticker rows"
                )
                stories = self._build_ticker_stories(standings, standings_by_abbr)

        self.feed_stories = stories
        logger.info(
            "MLB standings updated: %d stories",
            len(self.feed_stories),
        )

    def _build_ticker_stories(
        self,
        standings: list[TeamStanding],
        standings_by_abbr: dict[str, TeamStanding],
    ) -> list[TickerMessage | SegmentMessage | MLBStandingsBoard]:
        """layout="ticker": today's per-team SegmentMessage rows, unchanged —
        top N teams, then tracked teams not already in the top N."""
        stories: list[TickerMessage | SegmentMessage | MLBStandingsBoard] = []

        top_names: set[str] = set()
        for standing in standings[: self.top_n]:
            top_names.add(standing.name)
            stories.append(
                _build_standing_message(
                    standing,
                    bg_color=self.bg_color,
                    font=self.font,
                    font_color=self.font_color,
                )
            )

        for team in self.teams:
            abbr = API_TO_CANONICAL_ABBR.get(team, team)
            standing = standings_by_abbr.get(abbr)
            if standing and standing.name not in top_names:
                stories.append(
                    _build_standing_message(
                        standing,
                        bg_color=self.bg_color,
                        font=self.font,
                        font_color=self.font_color,
                    )
                )

        return stories

    def _build_board_stories(
        self,
        standings: list[TeamStanding],
        standings_by_abbr: dict[str, TeamStanding],
    ) -> list[TickerMessage | SegmentMessage | MLBStandingsBoard]:
        """layout="auto"/"board": one MLBStandingsBoard per tracked
        division, in config order (deduped), each carrying its division's
        top-`board_rows` rows (with tracked-team pinning, see
        `_select_division_rows`) plus the equivalent legacy SegmentMessage
        rows for the scale<=1 fallback (see _standings_card.MLBStandingsBoard).

        Fallback when `self.teams` is empty or none resolve to a division:
        the overall leader's division (`standings` is rank-sorted, so
        `standings[0]` is the leader).
        """
        divisions: list[int] = []
        seen: set[int] = set()
        for team in self.teams:
            abbr = API_TO_CANONICAL_ABBR.get(team, team)
            standing = standings_by_abbr.get(abbr)
            if standing and standing.division_id and standing.division_id not in seen:
                seen.add(standing.division_id)
                divisions.append(standing.division_id)

        if not divisions:
            leader = standings[0]
            if leader.division_id:
                divisions = [leader.division_id]

        tracked_abbrs = {API_TO_CANONICAL_ABBR.get(t, t) for t in self.teams}
        groups = _group_by_division(standings)
        stories: list[TickerMessage | SegmentMessage | MLBStandingsBoard] = []
        for division_id in divisions:
            division_rows = groups.get(division_id, [])
            rows = _select_division_rows(division_rows, self.board_rows, tracked_abbrs)
            if not rows:
                continue
            legacy_rows = [
                _build_standing_message(
                    row,
                    bg_color=self.bg_color,
                    font=self.font,
                    font_color=self.font_color,
                )
                for row in rows
            ]
            stories.append(
                MLBStandingsBoard(
                    division_name=DIVISION_NAMES.get(division_id, ""),
                    rows=rows,
                    legacy_rows=legacy_rows,
                    bg_color=self.bg_color,
                    font_color=self.font_color,
                    board_rows=self.board_rows,
                )
            )
        return stories

    def _parse_standings(
        self,
        data: dict[str, Any],
    ) -> list[TeamStanding]:
        """Parse MLB API standings response into sorted TeamStanding list."""
        all_teams: list[TeamStanding] = []
        for record in data.get("records", []):
            # `.get(key, {})`'s default only fires when the key is MISSING —
            # an explicit JSON `"division": null` still returns None here,
            # so `or {}` is required to survive a null-poisoned API payload
            # (see phase2-final-review.md F4).
            division_id = (record.get("division") or {}).get("id", 0)
            for tr in record.get("teamRecords", []):
                team = tr.get("team", {})
                name = team.get("name", "Unknown")
                wins = tr.get("wins", 0)
                losses = tr.get("losses", 0)
                rank = int(tr.get("sportRank", 99))
                gb = tr.get("sportGamesBack", "-")

                # The real /standings response does NOT include
                # team.abbreviation (only id/name/link -- it needs a
                # hydrate we don't request); fall back to the name lookup
                # so live data still resolves an abbr instead of rendering
                # a blank/grey chip. Whichever source wins still goes
                # through the API->canonical normalization below.
                raw_abbr = team.get("abbreviation", "") or MLB_NAME_TO_ABBR.get(
                    name, ""
                )
                abbr = API_TO_CANONICAL_ABBR.get(raw_abbr, raw_abbr)
                # `or ""` / `or "-"` below: a *present-but-null* field makes
                # `.get(key, default)` return None (not the default), which
                # `str(...)` would otherwise render as the literal text
                # "None" on the panel — null-check explicitly instead.
                pct = str(tr.get("winningPercentage") or "")
                split_records = (tr.get("records") or {}).get("splitRecords", [])
                l10 = next(
                    (
                        f"{sr.get('wins', 0)}-{sr.get('losses', 0)}"
                        for sr in split_records
                        if sr.get("type") == "lastTen"
                    ),
                    "",
                )
                streak = (tr.get("streak") or {}).get("streakCode", "")
                try:
                    division_rank = int(tr.get("divisionRank", 99))
                except TypeError, ValueError:
                    division_rank = 99
                division_gb = str(tr.get("divisionGamesBack") or "-")

                all_teams.append(
                    TeamStanding(
                        name=name,
                        wins=wins,
                        losses=losses,
                        rank=rank,
                        games_back=str(gb),
                        abbr=abbr,
                        pct=pct,
                        l10=l10,
                        streak=streak,
                        division_rank=division_rank,
                        division_gb=division_gb,
                        division_id=division_id,
                    )
                )
        all_teams.sort(key=lambda t: t.rank)
        return all_teams

    async def _fetch_opening_day(self) -> str | None:
        """Fetch the earliest regular season game date for tracked teams."""
        tz = self._tz or ZoneInfo(self.timezone)
        now = datetime.now(tz)
        start = now.strftime("%Y-%m-%d")
        end = (now + timedelta(days=30)).strftime("%Y-%m-%d")

        # Resolve abbreviation -> ID once instead of refetching the whole
        # /teams endpoint for every tracked team.
        try:
            async with self.session.get(f"{MLB_API}/teams?sportId=1") as resp:
                teams_data = await resp.json()
        except Exception:
            logger.debug("Failed to fetch MLB teams roster")
            return None

        abbr_to_id: dict[str, int] = {
            t["abbreviation"]: t["id"]
            for t in teams_data.get("teams", [])
            if t.get("abbreviation") and t.get("id") is not None
        }

        for team_abbr in self.teams:
            team_id = abbr_to_id.get(team_abbr)
            if not team_id:
                continue
            url = (
                f"{MLB_API}/schedule?teamId={team_id}"
                f"&startDate={start}&endDate={end}"
                f"&sportId=1&gameType=R"
            )
            try:
                async with self.session.get(url) as resp:
                    data = await resp.json()
            except Exception:
                logger.debug("Failed to fetch schedule for %s", team_abbr)
                continue

            for date_entry in data.get("dates", []):
                for g in date_entry.get("games", []):
                    game_date = g.get("gameDate")
                    if not game_date:
                        continue
                    with contextlib.suppress(ValueError, TypeError):
                        dt = datetime.fromisoformat(game_date.replace("Z", "+00:00"))
                        local = dt.astimezone(tz)
                        return local.strftime("%b %-d")
        return None

    async def _set_offseason_state(self) -> None:
        """Set display to offseason/pre-season message."""
        opening_day = await self._fetch_opening_day()
        msg = f"Opens {opening_day}" if opening_day else "Opens soon"

        body_color = (
            self.font_color if self.font_color is not None else colors.RGB_WHITE
        )
        self.feed_title = TickerMessage(
            self.title,
            font_color=body_color,
            center=True,
            bg_color=self.bg_color,
        )
        self.feed_stories = [
            TickerMessage(
                msg, font_color=body_color, center=True, bg_color=self.bg_color
            ),
        ]
        logger.info(
            "MLB standings updated: %d stories (offseason)",
            len(self.feed_stories),
        )

    def _set_error_state(self) -> None:
        """Set display to error state."""
        body_color = (
            self.font_color if self.font_color is not None else colors.RGB_WHITE
        )
        self.feed_title = TickerMessage(
            self.title,
            font_color=body_color,
            center=True,
            bg_color=self.bg_color,
        )
        self.feed_stories = [
            TickerMessage("No Data", font_color=body_color, bg_color=self.bg_color),
        ]
        logger.info(
            "MLB standings updated: %d stories (no data)",
            len(self.feed_stories),
        )
