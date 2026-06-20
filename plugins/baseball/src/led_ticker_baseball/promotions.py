"""MLB home-game promotions widget using the free MLB Stats API.

Data comes from the schedule endpoint's ``promotions`` hydration — giveaways
and theme nights attached to each home game (e.g. the Blue Jays' "Loonie Dogs
Night"). The API has no live counter data; this widget shows what's on, not
how many hot dogs were eaten.
"""

import contextlib
import logging
import re
from dataclasses import dataclass, field
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
    MLB_API,
    MLB_TEAM_NAMES,
    _team_color,
    resolve_team_id,
)

logger: logging.Logger = logging.getLogger(__name__)

_INTERVAL_SIX_HOURS: int = 21600

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
    "Dylan Cease Bobblehead Giveaway"), the shorter name wins. Pairwise only:
    three-way prefix chains within one game's promo list aren't fully
    collapsed — the feed has never produced one.
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
            return datetime.fromisoformat(game_date).astimezone(tz).date()
    return None


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
            msgs.append(f"promotions limit={limit!r} must be a non-negative integer.")

        for key in ("filter", "highlight"):
            if key not in cfg:
                continue
            val = cfg[key]
            if not isinstance(val, list) or not all(isinstance(v, str) for v in val):
                msgs.append(
                    f"promotions {key}={val!r} must be a list of strings, "
                    f'e.g. {key} = ["Loonie Dogs"].'
                )

        return msgs

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
                    if p and p.get("name")
                ]
                by_date.setdefault(d, []).extend(names)
        games = [
            GamePromos(game_date=d, promos=_dedupe_promos(names))
            for d, names in sorted(by_date.items())
        ]
        return games, had_games

    def _apply_filter(self, promos: list[str]) -> list[str]:
        """Keep only promos matching the filter keywords (all when unset)."""
        if not self.filter:
            return list(promos)
        return [p for p in promos if _match_any(p, self.filter)]

    def _pick_target(self, games: list[GamePromos], today: date) -> GamePromos | None:
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
    ) -> list[TickerMessage | SegmentMessage]:
        """One centered story per promo: 'TOR <Today|Jun 22> · <name>'.

        Every line leads with the team abbreviation in its brand color —
        stories scroll independently, so each must identify its team without
        relying on the section title. Highlighted promos render amber and
        sort first; ``limit`` truncates AFTER that sort so highlights are
        never the lines dropped.
        """
        label = (
            "Today"
            if target.game_date == today
            else target.game_date.strftime("%b %-d")
        )
        team_c = _team_color(self.team)
        date_c = make_color(150, 150, 150)  # grey — date label
        highlight_c = make_color(255, 200, 60)  # amber — highlighted promo
        body_c = self._plain_body_color()

        highlighted = [p for p in target.promos if _match_any(p, self.highlight)]
        rest = [p for p in target.promos if p not in highlighted]
        ordered = highlighted + rest
        if self.limit > 0:
            ordered = ordered[: self.limit]

        return [
            SegmentMessage(
                [
                    (f"{self.team} ", team_c),
                    (f"{label} · ", date_c),
                    (
                        name,
                        highlight_c if name in highlighted else body_c,
                    ),
                ],
                center=True,
                bg_color=self.bg_color,
                font=self.font,
                font_color=self.font_color,
            )
            for name in ordered
        ]

    def _set_title(self) -> None:
        """Team-colored '<Team> Promos' title, or the configured override."""
        if self.title:
            t_c = self.font_color if self.font_color is not None else colors.RGB_WHITE
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

    def _plain_body_color(self) -> Color | ColorProvider:
        """Body-text color for per-segment use.

        A plain-Color ``font_color`` tints body text while callout segments
        (team prefix, date label, amber highlight) keep their colors.
        Providers (``color_for``) can't color a single segment; they pass
        through ``font_color=`` on the message instead, which overrides every
        segment in core — same as the sibling widgets.
        """
        if self.font_color is not None and not hasattr(self.font_color, "color_for"):
            return self.font_color
        return colors.RGB_WHITE

    def _story_line(self, text: str) -> SegmentMessage:
        """Single status line led by the team abbreviation in its brand color."""
        return SegmentMessage(
            [
                (f"{self.team} ", _team_color(self.team)),
                (text, self._plain_body_color()),
            ],
            center=True,
            bg_color=self.bg_color,
            font=self.font,
            font_color=self.font_color,
        )

    # Contract for the _set_*_state setters below: they manage feed_stories
    # only. update() calls _set_title() unconditionally before dispatching to
    # any of them, so feed_title is always set — including on error paths.

    def _set_error_state(self) -> None:
        """Set display to error state."""
        self.feed_stories = [self._story_line("No Data")]
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
        self.feed_stories = [self._story_line(text)]
        logger.info("MLB Promotions %s updated: %s", self.team, text)

    async def _set_fallback_state(self, tz: ZoneInfo, had_games: bool) -> None:
        """No home games in the window: probe 30 days of regular season.

        First home game → "Next home game: <date>". Otherwise ``had_games``
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

        self.feed_stories = [self._story_line(text)]
        logger.info("MLB Promotions %s updated: fallback (%s)", self.team, text)
