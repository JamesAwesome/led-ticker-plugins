"""tennis.scores — live tennis scores from the Live Tennis API.

Cycles one story per live match (main tours first); when nothing is live,
one story per upcoming match; a single status line when there is nothing
at all, no key, or the key was rejected. Layouts: `auto` (default; ticker
on scale 1, held scoreboard on scale>1), `ticker`, `scoreboard`.

Data comes from the vendor's FREE tier (100 requests/day), so the poll
cadence is enforced in `_source.LiveTennisSource` (15-minute floor) — not
merely defaulted — and a fetch failure keeps the last good payload.
"""

import difflib
import logging
from datetime import UTC, datetime
from typing import Any, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import aiohttp
import attrs
from led_ticker.plugin import (
    FONT_DEFAULT,
    FONT_SMALL,
    Color,
    ColorProvider,
    Font,
    TickerMessage,
    run_monitor_loop,
    spawn_tracked,
)

from led_ticker_tennis import _palette as pal
from led_ticker_tennis._card import TennisMatchCard
from led_ticker_tennis._hires_line import HiresLine
from led_ticker_tennis._models import (
    TOURS,
    MatchInfo,
    build_demo_matches,
    parse_match,
    sort_key,
    tour_matches,
)
from led_ticker_tennis._source import (
    FREE_KEY_URL,
    MIN_UPDATE_INTERVAL,
    LiveTennisSource,
    clamp_interval,
    resolve_api_key,
    shared_source,
)
from led_ticker_tennis.layouts import VALID_LAYOUTS

__all__ = ["TennisScoreMonitor", "MatchInfo", "TennisMatchCard", "HiresLine"]

logger: logging.Logger = logging.getLogger(__name__)

_DRAWS: tuple[str, ...] = ("all", "singles", "doubles")
NO_KEY_TEXT = f"Tennis: set LIVETENNIS_API_KEY (free key: {FREE_KEY_URL})"
BAD_KEY_TEXT = "Tennis: API key rejected — check LIVETENNIS_API_KEY"
NO_MATCHES_TEXT = "No tennis matches right now"

_StoryT = TickerMessage | HiresLine | TennisMatchCard


@attrs.define
class TennisScoreMonitor:
    """Live tennis scores, cycling across live matches (fixtures when quiet)."""

    session: aiohttp.ClientSession | None
    api_key: str = ""
    tours: list[str] = attrs.field(factory=list)  # empty = every tour
    draw: str = "all"  # "all" | "singles" | "doubles"
    max_matches: int = 8
    timezone: str = "America/New_York"
    padding: int = 6
    hold_time: float = 0.0
    show_ranking: bool = False
    demo: bool = False
    bg_color: Color | None = attrs.field(default=None, kw_only=True)
    font_color: Color | ColorProvider | None = attrs.field(default=None, kw_only=True)
    font: Font | None = attrs.field(default=None, kw_only=True)
    small_font: Font = attrs.field(default=FONT_SMALL, kw_only=True)
    layout: str = attrs.field(default="auto", kw_only=True)
    _tz: ZoneInfo | None = attrs.field(init=False, default=None)
    _source: LiveTennisSource | None = attrs.field(init=False, default=None)
    feed_stories: list[_StoryT] = attrs.field(init=False, factory=list)

    _LIST_FIELD_HINTS = {
        "layout": ('"auto" | "ticker" | "scoreboard"', "match render shape", '"auto"'),
        "tours": (
            'list of "atp"/"wta"/"challenger"/"itf"/"juniors"',
            "tour filter (empty = all)",
            "[]",
        ),
        "draw": ('"all" | "singles" | "doubles"', "draw filter", '"all"'),
        "api_key": ("string", "Live Tennis API key (or env LIVETENNIS_API_KEY)", '""'),
        "update_interval": (
            "int seconds",
            f"poll cadence; floored at {MIN_UPDATE_INTERVAL}s (free tier)",
            "900",
        ),
    }

    @classmethod
    def validate_config(cls, cfg: dict[str, Any]) -> list[str]:
        """Pre-coercion config check (returns messages, never raises)."""
        msgs: list[str] = []
        try:
            ZoneInfo(cfg.get("timezone", "America/New_York"))
        except ZoneInfoNotFoundError, ValueError, TypeError:
            msgs.append("tennis.scores timezone must name an IANA timezone")
        layout = cfg.get("layout", "auto")
        if layout not in VALID_LAYOUTS:
            close = difflib.get_close_matches(
                str(layout), VALID_LAYOUTS, n=1, cutoff=0.5
            )
            hint = f" Did you mean {close[0]!r}?" if close else ""
            valid = ", ".join(repr(v) for v in VALID_LAYOUTS)
            msgs.append(
                f"tennis.scores layout={layout!r} is not valid. "
                f"Choose one of: {valid}.{hint}"
            )
        tours = cfg.get("tours", [])
        if not isinstance(tours, list) or any(not isinstance(t, str) for t in tours):
            msgs.append(
                'tennis.scores tours must be a list of strings, e.g. ["atp", "wta"]'
            )
        else:
            bad = [t for t in tours if t.lower() not in TOURS]
            if bad:
                msgs.append(
                    f"tennis.scores tours has unknown value(s) {bad!r}; "
                    f"choose from {list(TOURS)!r}"
                )
        draw = cfg.get("draw", "all")
        if draw not in _DRAWS:
            msgs.append(
                f"tennis.scores draw={draw!r} is not valid. "
                "Choose one of: 'all', 'singles', 'doubles'."
            )
        demo = cfg.get("demo")
        if demo is not None and not isinstance(demo, bool):
            msgs.append(f"tennis.scores demo must be a bool (true/false), got {demo!r}")
        n = cfg.get("max_matches", 8)
        if isinstance(n, bool) or not isinstance(n, int) or n < 1:
            msgs.append(f"tennis.scores max_matches must be a positive int, got {n!r}")
        return msgs

    @classmethod
    async def start(
        cls,
        session: aiohttp.ClientSession | None,
        update_interval: int = MIN_UPDATE_INTERVAL,
        **kwargs: Any,
    ) -> Self:
        widget = cls(session=session, **kwargs)
        widget.tours = [t.lower() for t in widget.tours]
        widget._tz = ZoneInfo(widget.timezone)
        if widget.demo:
            widget._load_demo()
            return widget
        key = resolve_api_key(widget.api_key)
        widget.api_key = key
        if not key:
            logger.warning(
                "tennis.scores: no API key (api_key / LIVETENNIS_API_KEY); "
                "nothing will be fetched"
            )
            widget.feed_stories = [widget._line(NO_KEY_TEXT, pal.AMBER)]
            return widget
        interval = clamp_interval(update_interval)
        widget._source = shared_source(session, key, interval=interval)
        await widget.update()
        logger.info(
            "tennis.scores: %d stories, polling every %ds",
            len(widget.feed_stories),
            interval,
        )
        spawn_tracked(run_monitor_loop(widget, interval))
        return widget

    # --- stories -----------------------------------------------------

    def _line(self, text: str, color: Color) -> HiresLine:
        legacy = TickerMessage(text, font_color=color, bg_color=self.bg_color)
        return HiresLine([(text, color)], legacy=legacy)

    def _card(self, m: MatchInfo, i: int, n: int) -> TennisMatchCard:
        return TennisMatchCard(
            match=m,
            tz=self._tz or ZoneInfo(self.timezone),
            cfg_layout=self.layout,
            story_index=i,
            story_total=n,
            padding=self.padding,
            show_ranking=self.show_ranking,
            bg_color=self.bg_color,
            font=self.font if self.font is not None else FONT_DEFAULT,
            small_font=self.small_font,
            font_color=self.font_color,
        )

    def _wanted(self, m: MatchInfo) -> bool:
        if not tour_matches(m.tour, self.tours):
            return False
        if self.draw == "singles" and m.is_doubles:
            return False
        return not (self.draw == "doubles" and not m.is_doubles)

    def _select(
        self, rows: list[dict[str, Any]], *, upcoming: bool = False
    ) -> list[MatchInfo]:
        matches = [parse_match(r) for r in rows]
        matches = [m for m in matches if self._wanted(m)]
        if upcoming:
            now = datetime.now(UTC)
            matches = [
                m
                for m in matches
                if m.state == "upcoming"
                and (m.start_time is None or m.start_time > now)
            ]
        # Matches in progress first; finished results fill the remaining slots.
        matches.sort(key=lambda m: (m.state == "final", sort_key(m)))
        return matches[: max(1, self.max_matches)]

    def _load_demo(self) -> None:
        tz = self._tz or ZoneInfo(self.timezone)
        matches = [m for m in build_demo_matches(tz) if self._wanted(m)]
        self.feed_stories = [
            self._card(m, i, len(matches)) for i, m in enumerate(matches)
        ]
        logger.info("tennis.scores demo: %d stories", len(self.feed_stories))

    async def update(self) -> None:
        """Poll (cadence permitting) and rebuild `feed_stories`. Never raises."""
        if self._source is None:
            return
        snap = await self._source.poll()
        if (
            snap.key_rejected
            and not snap.live
            and not snap.upcoming
            and not snap.recent
        ):
            self.feed_stories = [self._line(BAD_KEY_TEXT, pal.LOSS)]
            return
        live = self._select(snap.recent + snap.live)
        if live:
            self._source.remember_displayed([m.match_id for m in live])
            for m in live:
                m.stale = m.stale or (snap.stale and m.state != "final")
            self.feed_stories = [
                self._card(m, i, len(live)) for i, m in enumerate(live)
            ]
            logger.info(
                "tennis.scores: %d live match(es)%s",
                len(live),
                " (stale)" if snap.stale else "",
            )
            return
        upcoming = self._select(snap.upcoming, upcoming=True)
        if upcoming:
            for m in upcoming:
                m.stale = snap.stale
            self.feed_stories = [
                self._card(m, i, len(upcoming)) for i, m in enumerate(upcoming)
            ]
            logger.info("tennis.scores: no live play; %d upcoming", len(upcoming))
            return
        text = "Tennis: update failed" if snap.stale else NO_MATCHES_TEXT
        self.feed_stories = [self._line(text, pal.LABEL_HI)]
        logger.info(
            "tennis.scores: nothing to show (%s)", snap.last_error or "empty listings"
        )
