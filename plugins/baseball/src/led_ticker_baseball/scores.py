"""MLB score monitor widget using the free MLB Stats API."""

import asyncio
import contextlib
import difflib
import logging
from datetime import datetime, timedelta
from typing import Any, Self
from zoneinfo import ZoneInfo

import aiohttp
import attrs
from led_ticker.plugin import (
    FONT_DEFAULT,
    FONT_SMALL,
    Color,
    ColorProvider,
    Font,
    SegmentMessage,
    TickerMessage,
    colors,
    run_monitor_loop,
    spawn_tracked,
)

from led_ticker_baseball._models import (
    GameInfo,
    SeriesInfo,
    _classify_postponement,
    _fit_team_name,
    _format_game_time,
    _format_inning,
    _ordinal,
    _parse_team_abbr,
)
from led_ticker_baseball._scoreboard import (
    MLBScoreboardMessage,
    _build_game_message,
    _build_scoreboard_message,
    _build_series_title,
)
from led_ticker_baseball._two_row import (
    MLBTwoRowMessage,
    _build_two_row_message,
    _build_two_row_series_title,
    _compute_final_two_row,
    _compute_live_two_row,
    _compute_postponed_two_row,
    _compute_preview_two_row,
    _expand_matchup_if_fits,
    _pip_segments,
)
from led_ticker_baseball.teams import (
    _MLB_LIVE_API,
    MLB_API,
    MLB_TEAM_NAMES,
    resolve_team_id,
)

__all__ = [
    # models
    "GameInfo",
    "SeriesInfo",
    "_ordinal",
    "_format_inning",
    "_format_game_time",
    "_classify_postponement",
    "_parse_team_abbr",
    "_fit_team_name",
    # scoreboard
    "MLBScoreboardMessage",
    "_build_series_title",
    "_build_game_message",
    "_build_scoreboard_message",
    # two_row
    "MLBTwoRowMessage",
    "_build_two_row_message",
    "_build_two_row_series_title",
    "_compute_preview_two_row",
    "_compute_final_two_row",
    "_compute_live_two_row",
    "_compute_postponed_two_row",
    "_pip_segments",
    "_expand_matchup_if_fits",
    # re-export from led_ticker.plugin (used by test_scoreboard.py)
    "SegmentMessage",
    # monitor
    "MLBScoreMonitor",
]

logger: logging.Logger = logging.getLogger(__name__)

# Supported layouts and the per-row knobs that only apply to "two_row".
# Mirrors core's _MLB_VALID_LAYOUTS / _TWO_ROW_ONLY (formerly checked in
# led_ticker.app.factories for type == "mlb"); restored here as a
# validate_config classmethod now that baseball.scores owns the widget.
_MLB_VALID_LAYOUTS: tuple[str, ...] = ("ticker", "scoreboard", "two_row")
_TWO_ROW_ONLY: tuple[str, ...] = (
    "top_font",
    "top_font_size",
    "top_font_threshold",
    "top_row_height",
)


_MLBStoryT = TickerMessage | SegmentMessage | MLBScoreboardMessage | MLBTwoRowMessage


@attrs.define
class MLBScoreMonitor:
    """MLB scores for a single team's current series."""

    session: aiohttp.ClientSession
    team: str
    timezone: str = "America/New_York"
    padding: int = 6
    final_hold_hours: int = 6
    hold_time: float = 0.0
    bg_color: Color | None = attrs.field(default=None, kw_only=True)
    font_color: Color | ColorProvider | None = attrs.field(default=None, kw_only=True)
    # None when the config omits `font`. Resolved per-layout at draw-build time:
    # two_row falls back to FONT_SMALL (fits an 8-row band), ticker / scoreboard
    # fall back to FONT_DEFAULT. See the `display_font` resolution in update().
    font: Font | None = attrs.field(default=None, kw_only=True)
    small_font: Font = attrs.field(default=FONT_SMALL, kw_only=True)
    layout: str = attrs.field(default="ticker", kw_only=True)
    top_font: Font | None = attrs.field(default=None, kw_only=True)
    top_row_height: int | None = attrs.field(default=None, kw_only=True)
    _team_id: int = attrs.field(init=False, default=0)
    _tz: ZoneInfo | None = attrs.field(init=False, default=None)
    feed_title: _MLBStoryT | None = attrs.field(init=False, default=None)
    feed_stories: list[_MLBStoryT] = attrs.field(init=False, factory=list)

    @classmethod
    def validate_config(cls, cfg: dict[str, Any]) -> list[str]:
        """Pre-coercion config check, run by the engine via validate_widget_cfg.

        Reproduces the two guardrails core formerly applied to ``type =
        "mlb"`` in ``led_ticker.app.factories`` (now dead under the
        ``baseball.scores`` plugin): a valid ``layout`` value, and the
        per-row ``top_*`` knobs only being meaningful with
        ``layout = "two_row"``. Returns message strings (does NOT raise);
        the engine turns any returned messages into a pre-flight ValueError.
        """
        msgs: list[str] = []

        layout = cfg.get("layout", "ticker")
        if layout not in _MLB_VALID_LAYOUTS:
            close = difflib.get_close_matches(
                str(layout), _MLB_VALID_LAYOUTS, n=1, cutoff=0.5
            )
            suggestion = f" Did you mean {close[0]!r}?" if close else ""
            valid = ", ".join(repr(v) for v in _MLB_VALID_LAYOUTS)
            msgs.append(
                f"mlb layout={layout!r} is not valid. "
                f"Choose one of: {valid}.{suggestion}"
            )

        # Per-row knobs only apply under two_row. Naming the offending
        # field(s) instead of silently ignoring them catches stale configs.
        if layout != "two_row":
            dead = [k for k in _TWO_ROW_ONLY if k in cfg]
            if dead:
                fields = ", ".join(repr(k) for k in dead)
                msgs.append(
                    f"{fields} only applies when layout='two_row'; "
                    f"remove the field(s) or set layout='two_row'."
                )

        return msgs

    @classmethod
    async def start(
        cls,
        session: aiohttp.ClientSession,
        team: str,
        update_interval: int = 300,
        **kwargs: Any,
    ) -> Self:
        logger.debug("MLBScoreMonitor.start: team=%s", team)
        widget = cls(session=session, team=team.upper(), **kwargs)
        widget._tz = ZoneInfo(widget.timezone)
        await widget._resolve_team_id()
        await widget.update()
        logger.info(
            "MLB %s: %d stories",
            team,
            len(widget.feed_stories),
        )
        spawn_tracked(run_monitor_loop(widget, update_interval))
        return widget

    async def _resolve_team_id(self) -> None:
        """Fetch team ID from MLB API."""
        logger.debug("MLB: resolving team ID for %s", self.team)
        team_id = await resolve_team_id(self.session, self.team)
        if team_id is not None:
            self._team_id = team_id
            logger.debug("MLB: %s → id %d", self.team, self._team_id)

    async def update(self) -> None:
        """Fetch schedule and build display messages."""
        team_name = MLB_TEAM_NAMES.get(self.team, self.team)
        tz = self._tz or ZoneInfo(self.timezone)

        # Resolve effective colors: honour explicit font_color override,
        # else fall back to the per-widget defaults.
        from led_ticker_baseball.teams import _team_color

        title_color = (
            self.font_color if self.font_color is not None else _team_color(self.team)
        )
        body_color = (
            self.font_color if self.font_color is not None else colors.RGB_WHITE
        )

        if not self._team_id:
            title = TickerMessage(
                f"{team_name}",
                font_color=title_color,
                bg_color=self.bg_color,
            )
            self.feed_title = title
            self.feed_stories = [
                title,
                TickerMessage("No Data", font_color=body_color, bg_color=self.bg_color),
            ]
            logger.info(
                "MLB %s updated: %d stories (no data)",
                self.team,
                len(self.feed_stories),
            )
            return

        now = datetime.now(tz)
        start = (now - timedelta(days=7)).strftime("%Y-%m-%d")
        end = (now + timedelta(days=7)).strftime("%Y-%m-%d")

        url = (
            f"{MLB_API}/schedule?teamId={self._team_id}"
            f"&startDate={start}&endDate={end}&sportId=1"
            f"&hydrate=team,linescore"
        )

        try:
            async with self.session.get(url) as resp:
                data = await resp.json()
        except Exception:
            logger.exception("MLB API error for %s", self.team)
            title = TickerMessage(
                f"{team_name}",
                font_color=title_color,
                bg_color=self.bg_color,
            )
            self.feed_title = title
            self.feed_stories = [
                title,
                TickerMessage("No Data", font_color=body_color, bg_color=self.bg_color),
            ]
            logger.info(
                "MLB %s updated: %d stories (no data)",
                self.team,
                len(self.feed_stories),
            )
            return

        try:
            games = self._parse_games(data, tz)
        except Exception:
            logger.exception("MLB parse error for %s", self.team)
            title = TickerMessage(
                f"{team_name}",
                font_color=title_color,
                bg_color=self.bg_color,
            )
            self.feed_title = title
            self.feed_stories = [
                title,
                TickerMessage("No Data", font_color=body_color, bg_color=self.bg_color),
            ]
            logger.info(
                "MLB %s updated: %d stories (no data)",
                self.team,
                len(self.feed_stories),
            )
            return

        # Concurrently hydrate ABS challenge counts for live games.
        live_games = [g for g in games if g.state == "live" and g.game_pk]
        if live_games:
            results = await asyncio.gather(
                *(self._fetch_abs_challenges(g.game_pk) for g in live_games)
            )
            for g, (home_ch, away_ch) in zip(live_games, results, strict=False):
                g.home_challenges = home_ch
                g.away_challenges = away_ch

        if not games:
            title = TickerMessage(
                f"{team_name}",
                font_color=title_color,
                bg_color=self.bg_color,
            )
            self.feed_title = title
            self.feed_stories = [
                title,
                TickerMessage(
                    "Season Over", font_color=body_color, bg_color=self.bg_color
                ),
            ]
            logger.info(
                "MLB %s updated: %d stories (season over)",
                self.team,
                len(self.feed_stories),
            )
            return

        series = self._group_into_series(games)
        current = self._find_current_series(series, now)

        if current is None:
            # No current series — find next
            next_game = self._find_next_game(games, now)
            title = TickerMessage(
                f"{team_name}",
                font_color=title_color,
                bg_color=self.bg_color,
            )
            self.feed_title = title
            next_label = "season over"
            if next_game:
                opp = (
                    next_game.away_abbr
                    if next_game.home_abbr == self.team
                    else next_game.home_abbr
                )
                opp_name = MLB_TEAM_NAMES.get(opp, opp)
                next_label = opp_name
                if next_game.start_time:
                    time_str = _format_game_time(next_game.start_time, tz)
                else:
                    time_str = "TBD"
                self.feed_stories = [
                    title,
                    TickerMessage(
                        f"Next: vs {opp_name}, {time_str}",
                        font_color=body_color,
                        bg_color=self.bg_color,
                    ),
                ]
            else:
                self.feed_stories = [
                    title,
                    TickerMessage(
                        "Season Over", font_color=body_color, bg_color=self.bg_color
                    ),
                ]
            logger.info(
                "MLB %s updated: %d stories (next: %s)",
                self.team,
                len(self.feed_stories),
                next_label,
            )
            return

        # Build display from current series.
        # Resolve the effective font: two_row falls back to FONT_SMALL (fits an
        # 8-row band under the band-overflow guard), ticker / scoreboard fall
        # back to FONT_DEFAULT. A configured font is used as-is for all layouts.
        if self.font is not None:
            display_font = self.font
        elif self.layout == "two_row":
            display_font = FONT_SMALL
        else:
            display_font = FONT_DEFAULT

        if self.layout == "two_row":
            series_title: _MLBStoryT = _build_two_row_series_title(
                self.team,
                current,
                tz,
                bg_color=self.bg_color,
                font=display_font,
                small_font=self.small_font,
                top_font=self.top_font,
                top_row_height=self.top_row_height,
                font_color=self.font_color,
            )
        else:
            series_title = _build_series_title(
                self.team,
                current,
                tz,
                bg_color=self.bg_color,
                font=display_font,
                font_color=self.font_color,
            )
        self.feed_title = series_title
        stories: list[_MLBStoryT] = [series_title]
        if self.layout == "scoreboard":
            stories.extend(
                _build_scoreboard_message(
                    g,
                    self.team,
                    tz,
                    bg_color=self.bg_color,
                    font=display_font,
                    small_font=self.small_font,
                    font_color=self.font_color,
                )
                for g in current.games
            )
        elif self.layout == "two_row":
            stories.extend(
                _build_two_row_message(
                    g,
                    self.team,
                    tz,
                    bg_color=self.bg_color,
                    font=display_font,
                    small_font=self.small_font,
                    top_font=self.top_font,
                    top_row_height=self.top_row_height,
                    font_color=self.font_color,
                    series_wins=current.team_wins,
                    series_losses=current.team_losses,
                    series_total_games=len(current.games),
                )
                for g in current.games
            )
        else:
            stories.extend(
                _build_game_message(
                    g,
                    self.team,
                    tz,
                    bg_color=self.bg_color,
                    font=display_font,
                    font_color=self.font_color,
                )
                for g in current.games
            )
        self.feed_stories = stories
        n_live = sum(1 for g in current.games if g.state == "live")
        logger.info(
            "MLB %s updated: %d stories (live: %d)",
            self.team,
            len(self.feed_stories),
            n_live,
        )

    def _parse_games(
        self, schedule_data: dict[str, Any], tz: ZoneInfo
    ) -> list[GameInfo]:
        """Parse MLB API schedule response into GameInfo list."""
        games: list[GameInfo] = []
        for date_entry in schedule_data.get("dates", []):
            for g in date_entry.get("games", []):
                status = g.get("status", {})
                abstract = status.get("abstractGameState", "Preview")
                detailed = status.get("detailedState", "")
                reason = status.get("reason", "") or ""

                # Postponed / cancelled / suspended games come through with
                # abstractGameState="Final" but detailedState like
                # "Postponed", "Cancelled", "Suspended: Rain", etc. Detect
                # those before treating the game as completed (which would
                # render None scores as if the game ended 0-0).
                postponed_state, postpone_tag = _classify_postponement(detailed)

                home_team = g.get("teams", {}).get("home", {})
                away_team = g.get("teams", {}).get("away", {})
                home_abbr = _parse_team_abbr(home_team.get("team", {}))
                away_abbr = _parse_team_abbr(away_team.get("team", {}))

                home_score = home_team.get("score")
                away_score = away_team.get("score")

                inning: str | None = None
                balls = strikes = outs = 0
                on_first = on_second = on_third = False
                if abstract == "Live" and not postponed_state:
                    linescore = g.get("linescore", {})
                    inning_num = linescore.get("currentInning", 0)
                    half = linescore.get("inningHalf", "top").lower()
                    if inning_num:
                        inning = _format_inning(inning_num, half)

                    # At-bat data
                    offense = linescore.get("offense", {})
                    balls = linescore.get("balls", 0) or 0
                    strikes = linescore.get("strikes", 0) or 0
                    outs = linescore.get("outs", 0) or 0
                    on_first = "first" in offense
                    on_second = "second" in offense
                    on_third = "third" in offense

                # ABS challenges — hydrated separately for live games
                # via _fetch_abs_challenges.
                home_challenges: int | None = None
                away_challenges: int | None = None

                start_time: datetime | None = None
                game_date = g.get("gameDate")
                if game_date:
                    with contextlib.suppress(ValueError, TypeError):
                        start_time = datetime.fromisoformat(
                            game_date.replace("Z", "+00:00")
                        )

                state_map: dict[str, str] = {
                    "Final": "final",
                    "Live": "live",
                    "Preview": "preview",
                }

                resolved_state = (
                    postponed_state
                    if postponed_state is not None
                    else state_map.get(abstract, "preview")
                )

                games.append(
                    GameInfo(
                        home_abbr=home_abbr,
                        away_abbr=away_abbr,
                        home_score=home_score,
                        away_score=away_score,
                        state=resolved_state,
                        inning=inning,
                        start_time=start_time,
                        game_type=g.get("gameType", "R"),
                        game_pk=g.get("gamePk", 0),
                        balls=balls,
                        strikes=strikes,
                        outs=outs,
                        on_first=on_first,
                        on_second=on_second,
                        on_third=on_third,
                        postpone_reason=reason if postponed_state else "",
                        postpone_tag=postpone_tag if postponed_state else "PPD",
                        home_challenges=home_challenges,
                        away_challenges=away_challenges,
                    )
                )

        games.sort(
            key=lambda g: (
                g.start_time
                or datetime.min.replace(
                    tzinfo=tz,
                )
            )
        )
        return games

    def _group_into_series(self, games: list[GameInfo]) -> list[SeriesInfo]:
        """Group games into series by consecutive opponent."""
        if not games:
            return []

        series_list: list[SeriesInfo] = []
        current_opp: str | None = None
        current_games: list[GameInfo] = []

        for g in games:
            opp = g.away_abbr if g.home_abbr == self.team else g.home_abbr
            if opp != current_opp:
                if current_games:
                    assert current_opp is not None
                    series_list.append(self._make_series(current_opp, current_games))
                current_opp = opp
                current_games = [g]
            else:
                current_games.append(g)

        if current_games:
            assert current_opp is not None
            series_list.append(self._make_series(current_opp, current_games))

        return series_list

    def _make_series(self, opponent_abbr: str, games: list[GameInfo]) -> SeriesInfo:
        """Create a SeriesInfo with win/loss record."""
        wins = 0
        losses = 0
        for g in games:
            if g.state != "final":
                continue
            is_home = g.home_abbr == self.team
            team_score = g.home_score if is_home else g.away_score
            opp_score = g.away_score if is_home else g.home_score
            if team_score is not None and opp_score is not None:
                if team_score > opp_score:
                    wins += 1
                else:
                    losses += 1
        return SeriesInfo(
            opponent_abbr=opponent_abbr,
            games=games,
            team_wins=wins,
            team_losses=losses,
        )

    def _find_current_series(
        self, series_list: list[SeriesInfo], now: datetime
    ) -> SeriesInfo | None:
        """Find series that is live or most recently played."""
        for s in reversed(series_list):
            # "Final" + "postponed" both count as "this game is done for now"
            # for the purpose of locating the current series.
            has_final = any(g.state in ("final", "postponed") for g in s.games)
            has_live = any(g.state == "live" for g in s.games)
            has_upcoming = any(g.state == "preview" for g in s.games)
            if has_live:
                return s
            if has_final and has_upcoming:
                return s  # series in progress
            if has_final:
                # Check if this series ended recently (within 24h)
                last_game_time = max(
                    (g.start_time for g in s.games if g.start_time),
                    default=None,
                )
                if last_game_time:
                    hours_ago = (
                        now - last_game_time.astimezone(self._tz)
                    ).total_seconds() / 3600
                    if hours_ago < self.final_hold_hours:
                        return s
        # No current series — check for upcoming
        for s in series_list:
            if any(g.state == "preview" for g in s.games):
                return s
        return None

    def _find_next_game(self, games: list[GameInfo], now: datetime) -> GameInfo | None:
        """Find the next upcoming game."""
        for g in games:
            if (
                g.state == "preview"
                and g.start_time
                and g.start_time.astimezone(self._tz) > now
            ):
                return g
        return None

    async def _fetch_abs_challenges(
        self, game_pk: int
    ) -> tuple[int | None, int | None]:
        """Fetch ABS challenge remaining counts from the live game feed.

        Returns (home_remaining, away_remaining), or (None, None) when ABS is
        not active for this game or the request fails.
        """
        url = f"{_MLB_LIVE_API}/game/{game_pk}/feed/live"
        try:
            async with self.session.get(url) as resp:
                data = await resp.json()
        except Exception:
            logger.exception("ABS challenge fetch failed for gamePk=%s", game_pk)
            return None, None

        abs_ch = data.get("gameData", {}).get("absChallenges", {})
        # Empty dict means ABS is not active at this park. Non-empty means ABS
        # is equipped; hasChallenges is false until the first challenge is made,
        # so we gate on the dict being non-empty rather than on hasChallenges.
        if not abs_ch or "home" not in abs_ch:
            return None, None

        home = abs_ch.get("home") or {}
        away = abs_ch.get("away") or {}
        with contextlib.suppress(TypeError, ValueError):
            return int(home.get("remaining", 0)), int(away.get("remaining", 0))
        return None, None
