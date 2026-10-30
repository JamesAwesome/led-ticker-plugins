"""hockey.scores — live NHL scores from the NHL public web API (no key).

One story (a `HockeyGameCard`) per game, in the widget's `feed_stories`.
Modes:

- `teams` (default): per tracked team, in config order, its live game,
  else a final inside `final_hold_hours`, else a game later today, else
  its next scheduled game. A head-to-head is one card. Nothing scheduled
  (the offseason) means no story at all.
- `league`: tracked-team games first, then other live games, then finals
  inside the hold, then games later today by start time. Capped.
- `live`: only games in progress, tracked teams first. Capped; empty when
  nothing is live, so the rotation skips the widget.

Data comes from the shared, self-gating `_source.NHLSource`; a failed poll
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
    FONT_SMALL,
    Color,
    ColorProvider,
    Font,
    run_monitor_loop,
    spawn_tracked,
)

from led_ticker_hockey._card import HockeyGameCard
from led_ticker_hockey._models import (
    GameInfo,
    Goal,
    build_demo_games,
    final_in_hold,
)
from led_ticker_hockey._source import (
    LIVE_INTERVAL,
    MIN_INTERVAL,
    NHLSource,
    Snapshot,
    shared_source,
)
from led_ticker_hockey.layouts import VALID_LAYOUTS
from led_ticker_hockey.teams import NHL_TEAMS, normalize_team

__all__ = ["HockeyScoreMonitor", "HockeyGameCard", "select_stories"]

logger: logging.Logger = logging.getLogger(__name__)

MODES: tuple[str, ...] = ("teams", "league", "live")
_FAR_FUTURE = datetime.max.replace(tzinfo=UTC)

_CardKey = int | str


# ------------------------------------------------------------ selection


def _start_key(g: GameInfo) -> tuple[datetime, int]:
    return (g.start_utc or _FAR_FUTURE, g.game_id)


def _later_today(g: GameInfo, now_dt: datetime, tz: ZoneInfo) -> bool:
    return (
        g.state == "future"
        and g.start_utc is not None
        and g.start_utc.astimezone(tz).date() == now_dt.astimezone(tz).date()
    )


def _team_pick(
    team: str,
    games: list[GameInfo],
    now_dt: datetime,
    tz: ZoneInfo,
    hold_hours: int,
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
    today = [g for g in mine if _later_today(g, now_dt, tz)]
    return today[0] if today else None


def _dedupe(games: Iterable[GameInfo | None]) -> list[GameInfo]:
    seen: set[int] = set()
    out: list[GameInfo] = []
    for g in games:
        if g is not None and g.game_id not in seen:
            seen.add(g.game_id)
            out.append(g)
    return out


def select_stories(
    games: dict[int, GameInfo],
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
    zone = tz or ZoneInfo("UTC")
    now_dt = datetime.fromtimestamp(now_wall, UTC)
    tracked = [t.upper() for t in teams]
    ordered = sorted(games.values(), key=_start_key)
    cap = max(1, max_games)

    if mode == "teams":
        return _dedupe(
            _team_pick(t, ordered, now_dt, zone, final_hold_hours) or next_games.get(t)
            for t in tracked
        )

    if mode == "live":
        live = [g for g in ordered if g.state == "live"]
        firsts = [g for t in tracked for g in live if t in (g.away, g.home)]
        return _dedupe([*firsts, *live])[:cap]

    # league
    picks = [_team_pick(t, ordered, now_dt, zone, final_hold_hours) for t in tracked]
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
            *(g for g in ordered if _later_today(g, now_dt, zone)),
        ]
    )[:cap]


# --------------------------------------------------------------- widget


def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _is_number(v: Any) -> bool:
    return isinstance(v, int | float) and not isinstance(v, bool) and math.isfinite(v)


@attrs.define
class HockeyScoreMonitor:
    """Live NHL scores, one card per game."""

    session: aiohttp.ClientSession | None
    mode: str = "teams"
    teams: list[str] = attrs.field(factory=list)
    max_games: int = 8
    final_hold_hours: int = 6
    timezone: str = "America/New_York"
    padding: int = 6
    hold_time: float = 0.0
    demo: bool = False
    bg_color: Color | None = attrs.field(default=None, kw_only=True)
    font_color: Color | ColorProvider | None = attrs.field(default=None, kw_only=True)
    font: Font | None = attrs.field(default=None, kw_only=True)
    small_font: Font = attrs.field(default=FONT_SMALL, kw_only=True)
    layout: str = attrs.field(default="auto", kw_only=True)
    logos: bool = attrs.field(default=True, kw_only=True)
    celebration_flash: bool = attrs.field(default=False, kw_only=True)
    _tz: ZoneInfo | None = attrs.field(init=False, default=None)
    _source: NHLSource | None = attrs.field(init=False, default=None)
    _cards: dict[_CardKey, HockeyGameCard] = attrs.field(init=False, factory=dict)
    _celebrated: dict[int, set[str]] = attrs.field(init=False, factory=dict)
    # Per game: (away, home) score snapshots already celebrated or queued.
    _celebrated_scores: dict[int, set[tuple[int, int]]] = attrs.field(
        init=False, factory=dict
    )
    feed_stories: list[HockeyGameCard] = attrs.field(init=False, factory=list)

    _LIST_FIELD_HINTS = {
        "mode": ('"teams" | "league" | "live"', "which games to show", '"teams"'),
        "teams": (
            'list of NHL codes, e.g. ["PHI", "NYI"]',
            "tracked teams (required in teams mode)",
            "[]",
        ),
        "layout": ('"auto" | "scoreboard" | "ticker"', "game render shape", '"auto"'),
        "logos": (
            "bool",
            "paint bundled team logos on bigsign/longboi",
            "true",
        ),
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
                f"hockey.scores mode={mode!r} is not valid. "
                f"Choose one of: {valid}.{hint}"
            )
        teams = cfg.get("teams", [])
        if not isinstance(teams, list) or any(not isinstance(t, str) for t in teams):
            msgs.append(
                'hockey.scores teams must be a list of strings, e.g. ["PHI", "NYI"]'
            )
        else:
            for code in teams:
                if normalize_team(code) is None:
                    close = difflib.get_close_matches(
                        code.strip().upper(), list(NHL_TEAMS), n=1, cutoff=0.5
                    )
                    hint = f" Did you mean {close[0]!r}?" if close else ""
                    msgs.append(f"hockey.scores teams has unknown code {code!r}.{hint}")
            if mode == "teams" and not teams and cfg.get("demo") is not True:
                msgs.append(
                    'hockey.scores mode="teams" needs a non-empty teams list, '
                    'e.g. teams = ["PHI", "NYI"] (or use mode="league")'
                )
        layout = cfg.get("layout", "auto")
        if layout not in VALID_LAYOUTS:
            close = difflib.get_close_matches(
                str(layout), VALID_LAYOUTS, n=1, cutoff=0.5
            )
            hint = f" Did you mean {close[0]!r}?" if close else ""
            valid = ", ".join(repr(v) for v in VALID_LAYOUTS)
            msgs.append(
                f"hockey.scores layout={layout!r} is not valid. "
                f"Choose one of: {valid}.{hint}"
            )
        try:
            ZoneInfo(cfg.get("timezone", "America/New_York"))
        except ZoneInfoNotFoundError, ValueError, TypeError:
            msgs.append("hockey.scores timezone must name an IANA timezone")
        n = cfg.get("max_games", 8)
        if not _is_int(n) or n < 1:
            msgs.append(f"hockey.scores max_games must be a positive int, got {n!r}")
        hold = cfg.get("final_hold_hours", 6)
        if not _is_int(hold) or hold < 0:
            msgs.append(
                f"hockey.scores final_hold_hours must be an int >= 0, got {hold!r}"
            )
        for name in ("hold_time", "padding"):
            if name in cfg:
                v = cfg[name]
                if not _is_number(v) or v < 0:
                    msgs.append(
                        f"hockey.scores {name} must be a number >= 0, got {v!r}"
                    )
        logos = cfg.get("logos")
        if logos is not None and not isinstance(logos, bool):
            msgs.append(
                f"hockey.scores logos must be a bool (true/false), got {logos!r}"
            )
        flash = cfg.get("celebration_flash")
        if flash is not None and not isinstance(flash, bool):
            msgs.append(
                f"hockey.scores celebration_flash must be a bool (true/false), "
                f"got {flash!r}"
            )
        demo = cfg.get("demo")
        if demo is not None and not isinstance(demo, bool):
            msgs.append(f"hockey.scores demo must be a bool (true/false), got {demo!r}")
        if "update_interval" in cfg:
            iv = cfg["update_interval"]
            if not _is_int(iv) or iv < 1:
                msgs.append(
                    f"hockey.scores update_interval must be a positive int "
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
        if widget.celebration_flash:
            logger.warning(
                "hockey.scores: celebration_flash is on. Celebrations open with a "
                "full-panel flash (~5 Hz), a photosensitive-epilepsy hazard; "
                "set celebration_flash = false on signs in shared spaces"
            )
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
            "hockey.scores: %d stories, mode=%s, polling every %ds",
            len(widget.feed_stories),
            widget.mode,
            interval,
        )
        # splay=False: core's default adds a fixed random 0-60 s to the
        # interval at startup (football saw a 15 s live poll become 29 s on
        # longboi). The shared source already rate-limits itself.
        spawn_tracked(run_monitor_loop(widget, interval, splay=False))
        return widget

    # --- stories -----------------------------------------------------

    def _new_card(self, game: GameInfo) -> HockeyGameCard:
        return HockeyGameCard(
            game=game,
            tz=self._tz or ZoneInfo(self.timezone),
            cfg_layout=self.layout,
            padding=self.padding,
            now_fn=time.time,
            tracked=frozenset(self.teams),
            base_hold=self.hold_time,
            bg_color=self.bg_color,
            font=self.font if self.font is not None else FONT_DEFAULT,
            small_font=self.small_font,
            font_color=self.font_color,
            logos=self.logos,
            flash=self.celebration_flash,
        )

    def _load_demo(self) -> None:
        games = build_demo_games(time.time())
        self._cards = {g.game_id: self._new_card(g) for g in games}
        for card in self._cards.values():
            if card.game.state == "live" and card.game.goals:
                # Celebrate on the first visit, then after every 3rd.
                card.demo_goals = card.game.goals
                card.queue_goals(list(card.game.goals))
        self.feed_stories = list(self._cards.values())
        logger.info("hockey.scores demo: %d stories", len(self.feed_stories))

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
            logger.exception("hockey.scores update failed; keeping last stories")

    def _rebuild(self, source: NHLSource, snap: Snapshot) -> None:
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
        cards: dict[_CardKey, HockeyGameCard] = {}
        for game in chosen:
            key: _CardKey = (
                game.game_id
                if game.game_id in snap.games
                else next_keys.get(game.game_id, game.game_id)
            )
            card = self._cards.get(key)
            if card is None:
                card = self._new_card(game)
            card.game = game
            card.drop_overturned()
            card.stale = snap.stale
            cards[key] = card
        self._cards = cards
        self._queue_goals(source, snap)
        source.note_displayed(self, {k for k in cards if isinstance(k, int)})
        self.feed_stories = list(cards.values())
        logger.info(
            "hockey.scores updated: %d stories%s",
            len(self.feed_stories),
            " (stale)" if snap.stale else "",
        )

    def _queue_goals(self, source: NHLSource, snap: Snapshot) -> None:
        """Queue goals this widget hasn't celebrated onto their cards.

        A game's first sight by THIS widget is a silent baseline, so a hot
        reload with a surviving shared source never replays old goals. A
        new key whose score snapshot was already celebrated or queued is a
        scoring change (the feed re-keys a goal when the scorer is
        corrected): it replaces the pending entry, never celebrates again.
        Snapshots above the current score are forgotten (a disallowed
        goal), so the next real goal at that score still celebrates.
        """
        for gid, game in snap.games.items():
            goals = source.goals_after_baseline(gid)
            seen = self._celebrated.get(gid)
            if seen is None:
                self._celebrated[gid] = {g.key for g in goals}
                self._celebrated_scores[gid] = {
                    (g.away_score, g.home_score) for g in game.goals
                }
                continue
            scores = {
                s
                for s in self._celebrated_scores.get(gid, set())
                if s[0] <= game.away_score and s[1] <= game.home_score
            }
            self._celebrated_scores[gid] = scores
            new = [g for g in goals if g.key not in seen]
            if not new:
                continue
            seen.update(g.key for g in new)
            fresh: list[Goal] = []
            changed: list[Goal] = []
            for g in new:
                score = (g.away_score, g.home_score)
                (changed if score in scores else fresh).append(g)
                scores.add(score)
            card = self._cards.get(gid)
            if card is not None:
                card.queue_goals(fresh)
                card.replace_goals(changed)
        self._celebrated = {
            gid: keys for gid, keys in self._celebrated.items() if gid in snap.games
        }
        self._celebrated_scores = {
            gid: s for gid, s in self._celebrated_scores.items() if gid in snap.games
        }
