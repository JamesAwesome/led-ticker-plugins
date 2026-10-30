"""basketball.scores — live NBA scores from ESPN's public scoreboard API (no key).

One story (a `BasketballGameCard`) per game, in the widget's `feed_stories`.
Modes:

- `teams` (default): per tracked team, in config order, its live game, else
  a final inside `final_hold_hours`, else its game later today, else its next
  scheduled game. A head-to-head is one card. Nothing scheduled (the
  offseason) means no story at all.
- `league`: tracked-team games first, then other live games, then finals
  inside the hold, then the rest of today's games by tip-off. Capped.
- `live`: only games in progress, tracked teams first. Capped; empty when
  nothing is live, so the rotation skips the widget.

Data comes from the shared, self-gating `_source.ESPNSource`; a failed poll
keeps the last good games and marks every card `stale`.
"""

import difflib
import logging
import math
import time
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import aiohttp
import attrs
from led_ticker.plugin import (
    FONT_DEFAULT,
    Color,
    ColorProvider,
    Font,
    run_monitor_loop,
    spawn_tracked,
)

from led_ticker_basketball._card import BasketballGameCard
from led_ticker_basketball._models import (
    GameInfo,
    build_demo_games,
    final_in_hold,
)
from led_ticker_basketball._source import (
    LIVE_INTERVAL,
    MIN_INTERVAL,
    ESPNSource,
    Snapshot,
    shared_source,
)
from led_ticker_basketball.layouts import VALID_LAYOUTS
from led_ticker_basketball.teams import NBA_TEAMS, normalize_team

__all__ = ["BasketballScoreMonitor", "BasketballGameCard", "select_stories"]

logger: logging.Logger = logging.getLogger(__name__)

MODES: tuple[str, ...] = ("teams", "league", "live")
_FAR_FUTURE = datetime.max.replace(tzinfo=UTC)
DEFAULT_FINAL_HOLD_HOURS = 6


# ------------------------------------------------------------ selection


def _start_key(g: GameInfo) -> tuple[int, datetime, str]:
    # TBD tip-offs sort after every timed game.
    return (1 if g.time_tbd else 0, g.start_utc or _FAR_FUTURE, g.game_id)


def _upcoming(g: GameInfo) -> bool:
    return g.state == "future"


def _team_pick(
    team: str, games: list[GameInfo], now_dt: datetime, hold_hours: int
) -> GameInfo | None:
    mine = [g for g in games if team in (g.away, g.home)]
    live = [g for g in mine if g.state == "live"]
    if live:
        return live[0]
    finals = [
        g for g in mine if g.state == "final" and final_in_hold(g, now_dt, hold_hours)
    ]
    if finals:
        return finals[-1]  # the most recent
    upcoming = [g for g in mine if _upcoming(g)]
    return upcoming[0] if upcoming else None


def _dedupe(games: Iterable[GameInfo | None]) -> list[GameInfo]:
    seen: set[str] = set()
    out: list[GameInfo] = []
    for g in games:
        if g is not None and g.game_id not in seen:
            seen.add(g.game_id)
            out.append(g)
    return out


def select_stories(
    games: dict[str, GameInfo],
    next_games: dict[str, GameInfo],
    *,
    mode: str,
    teams: list[str],
    max_games: int,
    now_wall: float,
    final_hold_hours: int,
    tz: ZoneInfo | None = None,
) -> list[GameInfo]:
    """The games to show, in rotation order. Pure."""
    now_dt = datetime.fromtimestamp(now_wall, UTC)
    tracked = [t.upper() for t in teams]
    ordered = sorted(games.values(), key=_start_key)
    cap = max(1, max_games)

    if mode == "teams":
        return _dedupe(
            _team_pick(t, ordered, now_dt, final_hold_hours) or next_games.get(t)
            for t in tracked
        )

    if mode == "live":
        live = [g for g in ordered if g.state == "live"]
        firsts = [g for t in tracked for g in live if t in (g.away, g.home)]
        return _dedupe([*firsts, *live])[:cap]

    # league
    picks = [_team_pick(t, ordered, now_dt, final_hold_hours) for t in tracked]
    finals = [
        g
        for g in ordered
        if g.state == "final" and final_in_hold(g, now_dt, final_hold_hours)
    ]
    return _dedupe(
        [
            *picks,
            *(g for g in ordered if g.state == "live"),
            *finals,
            *(g for g in ordered if _upcoming(g)),
        ]
    )[:cap]


# --------------------------------------------------------------- widget


def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _is_number(v: Any) -> bool:
    return isinstance(v, int | float) and not isinstance(v, bool) and math.isfinite(v)


_CardKey = str


@attrs.define
class BasketballScoreMonitor:
    """Live NBA scores, one card per game."""

    session: aiohttp.ClientSession | None
    mode: str = "teams"
    teams: list[str] = attrs.field(factory=list)
    max_games: int = 8
    final_hold_hours: int = DEFAULT_FINAL_HOLD_HOURS
    timezone: str = "America/New_York"
    padding: int = 6
    hold_time: float = 0.0
    demo: bool = False
    bg_color: Color | None = attrs.field(default=None, kw_only=True)
    font_color: Color | ColorProvider | None = attrs.field(default=None, kw_only=True)
    font: Font | None = attrs.field(default=None, kw_only=True)
    layout: str = attrs.field(default="auto", kw_only=True)
    logos: bool = attrs.field(default=True, kw_only=True)
    ball_at: bool = attrs.field(default=True, kw_only=True)
    _tz: ZoneInfo | None = attrs.field(init=False, default=None)
    _source: ESPNSource | None = attrs.field(init=False, default=None)
    _cards: dict[_CardKey, BasketballGameCard] = attrs.field(init=False, factory=dict)
    _celebrated: dict[str, set[str]] = attrs.field(init=False, factory=dict)
    feed_stories: list[BasketballGameCard] = attrs.field(init=False, factory=list)

    _LIST_FIELD_HINTS = {
        "mode": ('"teams" | "league" | "live"', "which games to show", '"teams"'),
        "teams": (
            'list of NBA codes, e.g. ["PHI", "NY"]',
            "tracked teams (required in teams mode)",
            "[]",
        ),
        "layout": ('"auto" | "scoreboard" | "ticker"', "game render shape", '"auto"'),
        "logos": (
            "bool",
            "paint bundled team logos on bigsign/longboi",
            "true",
        ),
        "ball_at": (
            "bool",
            "the ball is the @ on smallsign next-game cards",
            "true",
        ),
        "timezone": ("IANA zone", "tip-off times and day labels", '"America/New_York"'),
        "padding": ("int px", "gap after the hi-res ticker line (scale > 1 only)", "6"),
        "update_interval": (
            "int seconds",
            f"live poll cadence; floored at {MIN_INTERVAL}s",
            str(LIVE_INTERVAL),
        ),
    }

    @classmethod
    def validate_config(cls, cfg: dict[str, Any]) -> list[str]:
        """Pre-coercion config check (returns messages, never raises)."""
        msgs: list[str] = []
        mode = cfg.get("mode", "teams")
        if mode not in MODES:
            close = difflib.get_close_matches(str(mode), MODES, n=1, cutoff=0.5)
            hint = f" Did you mean {close[0]!r}?" if close else ""
            valid = ", ".join(repr(m) for m in MODES)
            msgs.append(
                f"basketball.scores mode={mode!r} is not valid. "
                f"Choose one of: {valid}.{hint}"
            )
        teams = cfg.get("teams", [])
        if not isinstance(teams, list) or any(not isinstance(t, str) for t in teams):
            msgs.append(
                'basketball.scores teams must be a list of strings, e.g. ["PHI", "NY"]'
            )
        else:
            for code in teams:
                if normalize_team(code) is None:
                    close = difflib.get_close_matches(
                        code.strip().upper(), list(NBA_TEAMS), n=1, cutoff=0.5
                    )
                    hint = f" Did you mean {close[0]!r}?" if close else ""
                    msgs.append(
                        f"basketball.scores teams has unknown code {code!r}.{hint}"
                    )
            if mode == "teams" and not teams and cfg.get("demo") is not True:
                msgs.append(
                    'basketball.scores mode="teams" needs a non-empty teams list, '
                    'e.g. teams = ["PHI", "NY"] (or use mode="league")'
                )
        layout = cfg.get("layout", "auto")
        if layout not in VALID_LAYOUTS:
            close = difflib.get_close_matches(
                str(layout), VALID_LAYOUTS, n=1, cutoff=0.5
            )
            hint = f" Did you mean {close[0]!r}?" if close else ""
            valid = ", ".join(repr(v) for v in VALID_LAYOUTS)
            msgs.append(
                f"basketball.scores layout={layout!r} is not valid. "
                f"Choose one of: {valid}.{hint}"
            )
        if "small_font" in cfg:
            msgs.append(
                "basketball.scores does not accept small_font: "
                "the smallsign board uses font"
            )
        for name in ("logos", "ball_at"):
            v = cfg.get(name)
            if v is not None and not isinstance(v, bool):
                msgs.append(
                    f"basketball.scores {name} must be a bool (true/false), got {v!r}"
                )
        try:
            ZoneInfo(cfg.get("timezone", "America/New_York"))
        except ZoneInfoNotFoundError, ValueError, TypeError:
            msgs.append("basketball.scores timezone must name an IANA timezone")
        n = cfg.get("max_games", 8)
        if not _is_int(n) or n < 1:
            msgs.append(
                f"basketball.scores max_games must be a positive int, got {n!r}"
            )
        hold = cfg.get("final_hold_hours", DEFAULT_FINAL_HOLD_HOURS)
        if not _is_int(hold) or hold < 0:
            msgs.append(
                f"basketball.scores final_hold_hours must be an int >= 0, got {hold!r}"
            )
        for name in ("hold_time", "padding"):
            if name in cfg:
                v = cfg[name]
                if not _is_number(v) or v < 0:
                    msgs.append(
                        f"basketball.scores {name} must be a number >= 0, got {v!r}"
                    )
        demo = cfg.get("demo")
        if demo is not None and not isinstance(demo, bool):
            msgs.append(
                f"basketball.scores demo must be a bool (true/false), got {demo!r}"
            )
        if "update_interval" in cfg:
            iv = cfg["update_interval"]
            if not _is_int(iv) or iv < 1:
                msgs.append(
                    f"basketball.scores update_interval must be a positive int "
                    f"(seconds), got {iv!r}"
                )
        return msgs

    @classmethod
    async def start(
        cls,
        session: aiohttp.ClientSession | None,
        update_interval: int = LIVE_INTERVAL,
        **kwargs: Any,
    ) -> Self:
        widget = cls(session=session, **kwargs)
        widget.teams = [normalize_team(t) or t.strip().upper() for t in widget.teams]
        widget._tz = ZoneInfo(widget.timezone)
        widget.padding = int(widget.padding)  # validated: a number >= 0
        if widget.demo:
            widget._load_demo()
            return widget
        source = shared_source(session)
        source.want(
            teams=set(widget.teams),
            all_games=widget.mode != "teams",
            tz=widget._tz,
            final_hold_hours=widget.final_hold_hours,
            live_interval=update_interval,
        )
        widget._source = source
        await widget.update()
        interval = max(MIN_INTERVAL, update_interval)
        logger.info(
            "basketball.scores: %d stories, mode=%s, polling every %ds",
            len(widget.feed_stories),
            widget.mode,
            interval,
        )
        # splay=False: core's default adds a fixed random 0-60 s to the
        # interval at startup, which stretches a 15 s live poll. The shared
        # source already rate-limits itself.
        spawn_tracked(run_monitor_loop(widget, interval, splay=False))
        return widget

    # --- stories -----------------------------------------------------

    def _new_card(self, game: GameInfo) -> BasketballGameCard:
        return BasketballGameCard(
            game=game,
            tz=self._tz or ZoneInfo(self.timezone),
            cfg_layout=self.layout,
            padding=self.padding,
            now_fn=time.time,
            tracked=frozenset(self.teams),
            base_hold=self.hold_time,
            bg_color=self.bg_color,
            font=self.font if self.font is not None else FONT_DEFAULT,
            font_color=self.font_color,
            logos=self.logos,
            ball_at=self.ball_at,
        )

    def _load_demo(self) -> None:
        games, ev = build_demo_games(time.time())
        self._cards = {g.game_id: self._new_card(g) for g in games}
        live = self._cards["demo-live"]
        live.demo_final = ev
        live.queue_final(ev)
        self.feed_stories = list(self._cards.values())
        logger.info("basketball.scores demo: %d stories", len(self.feed_stories))

    async def update(self) -> None:
        """Poll (the source gates itself) and rebuild `feed_stories`.

        Never raises: a failure keeps the previous stories.
        """
        if self._source is None:
            return
        try:
            snap = await self._source.poll()
            self._rebuild(self._source, snap)
        except Exception:  # noqa: BLE001 — never into the poll loop
            logger.exception("basketball.scores update failed; keeping last stories")

    def _rebuild(self, source: ESPNSource, snap: Snapshot) -> None:
        chosen = select_stories(
            snap.games,
            snap.next_games,
            mode=self.mode,
            teams=self.teams,
            max_games=self.max_games,
            now_wall=time.time(),
            final_hold_hours=self.final_hold_hours,
            tz=self._tz or ZoneInfo(self.timezone),
        )
        next_keys = {g.game_id: f"next:{t}" for t, g in snap.next_games.items()}
        cards: dict[_CardKey, BasketballGameCard] = {}
        for game in chosen:
            key = (
                game.game_id
                if game.game_id in snap.games
                else next_keys.get(game.game_id, game.game_id)
            )
            card = self._cards.get(key)
            if card is None:
                card = self._new_card(game)
            else:
                if game.away_score != card.game.away_score:
                    card.pulse(game.away)
                if game.home_score != card.game.home_score:
                    card.pulse(game.home)
            card.game = game
            card.stale = snap.stale
            cards[key] = card
        self._queue_finals(source, snap, cards)
        # A game that left the selection (live mode: it just went final) on
        # the very poll that ended it keeps its card until the final has
        # actually flashed; `pending` empties once it was shown.
        for key, card in self._cards.items():
            gid = str(key)
            if key not in cards and gid in snap.games and card.pending:
                card.game = snap.games[gid]
                card.stale = snap.stale
                cards[key] = card
        self._cards = cards
        source.note_displayed(self, {k for k in cards if not k.startswith("next:")})
        self.feed_stories = list(cards.values())
        logger.info(
            "basketball.scores updated: %d stories%s",
            len(self.feed_stories),
            " (stale)" if snap.stale else "",
        )

    def _queue_finals(
        self,
        source: ESPNSource,
        snap: Snapshot,
        cards: dict[_CardKey, BasketballGameCard],
    ) -> None:
        """Queue finals this widget hasn't celebrated onto their cards.

        A game's first sight by THIS widget is a silent baseline, so a hot
        reload with a surviving shared source never replays old finals.
        """
        for gid in snap.games:
            ev = source.final_after_baseline(gid)
            seen = self._celebrated.get(gid)
            if seen is None:
                self._celebrated[gid] = {ev.key} if ev else set()
                continue
            if ev is not None and ev.key not in seen:
                seen.add(ev.key)
                card = cards.get(gid) or self._cards.get(gid)
                if card is not None:
                    card.queue_final(ev)
        self._celebrated = {
            gid: keys for gid, keys in self._celebrated.items() if gid in snap.games
        }
