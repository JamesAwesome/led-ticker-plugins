"""football.scores — live NFL scores from ESPN's public scoreboard API (no key).

One story (a `FootballGameCard`) per game, in the widget's `feed_stories`.
Modes:

- `teams` (default): per tracked team, in config order, its live game,
  else a final inside `final_hold_hours`, else its game later this week,
  else its next scheduled game (flagged `BYE WEEK` when the team is on
  its bye). A head-to-head is one card. Nothing scheduled (the offseason)
  means no story at all.
- `league`: tracked-team games first, then other live games, then finals
  inside the hold, then the rest of the week's games by kickoff. Capped.
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
    FONT_SMALL,
    Color,
    ColorProvider,
    Font,
    run_monitor_loop,
    spawn_tracked,
)

from led_ticker_football._card import FootballGameCard
from led_ticker_football._models import (
    GameInfo,
    ScoringPlay,
    build_demo_games,
    final_in_hold,
    pre_extra_score,
)
from led_ticker_football._source import (
    LIVE_INTERVAL,
    MIN_INTERVAL,
    ESPNSource,
    Snapshot,
    shared_source,
)
from led_ticker_football.layouts import VALID_LAYOUTS
from led_ticker_football.teams import NFL_TEAMS, normalize_team

__all__ = ["FootballScoreMonitor", "FootballGameCard", "select_stories"]

logger: logging.Logger = logging.getLogger(__name__)

MODES: tuple[str, ...] = ("teams", "league", "live")
_FAR_FUTURE = datetime.max.replace(tzinfo=UTC)
DEFAULT_FINAL_HOLD_HOURS = 24


# ------------------------------------------------------------ selection


def _start_key(g: GameInfo) -> tuple[int, datetime, str]:
    # TBD kickoffs sort after every timed game of the week.
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


def _key_within(key: str, away: int, home: int) -> bool:
    """True when a play key (`gid:away:home`) is at or below the score."""
    try:
        _, a, h = key.rsplit(":", 2)
        return int(a) <= away and int(h) <= home
    except ValueError:
        return True


@attrs.define
class FootballScoreMonitor:
    """Live NFL scores, one card per game."""

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
    small_font: Font = attrs.field(default=FONT_SMALL, kw_only=True)
    layout: str = attrs.field(default="auto", kw_only=True)
    _tz: ZoneInfo | None = attrs.field(init=False, default=None)
    _source: ESPNSource | None = attrs.field(init=False, default=None)
    _cards: dict[_CardKey, FootballGameCard] = attrs.field(init=False, factory=dict)
    _celebrated: dict[str, set[str]] = attrs.field(init=False, factory=dict)
    # Per game: pre-try (away, home) snapshots already celebrated or queued.
    _celebrated_scores: dict[str, set[tuple[int, int]]] = attrs.field(
        init=False, factory=dict
    )
    feed_stories: list[FootballGameCard] = attrs.field(init=False, factory=list)

    _LIST_FIELD_HINTS = {
        "mode": ('"teams" | "league" | "live"', "which games to show", '"teams"'),
        "teams": (
            'list of NFL codes, e.g. ["PHI", "NYG"]',
            "tracked teams (required in teams mode)",
            "[]",
        ),
        "layout": ('"auto" | "scoreboard" | "ticker"', "game render shape", '"auto"'),
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
                f"football.scores mode={mode!r} is not valid. "
                f"Choose one of: {valid}.{hint}"
            )
        teams = cfg.get("teams", [])
        if not isinstance(teams, list) or any(not isinstance(t, str) for t in teams):
            msgs.append(
                'football.scores teams must be a list of strings, e.g. ["PHI", "NYG"]'
            )
        else:
            for code in teams:
                if normalize_team(code) is None:
                    close = difflib.get_close_matches(
                        code.strip().upper(), list(NFL_TEAMS), n=1, cutoff=0.5
                    )
                    hint = f" Did you mean {close[0]!r}?" if close else ""
                    msgs.append(
                        f"football.scores teams has unknown code {code!r}.{hint}"
                    )
            if mode == "teams" and not teams and cfg.get("demo") is not True:
                msgs.append(
                    'football.scores mode="teams" needs a non-empty teams list, '
                    'e.g. teams = ["PHI", "NYG"] (or use mode="league")'
                )
        layout = cfg.get("layout", "auto")
        if layout not in VALID_LAYOUTS:
            close = difflib.get_close_matches(
                str(layout), VALID_LAYOUTS, n=1, cutoff=0.5
            )
            hint = f" Did you mean {close[0]!r}?" if close else ""
            valid = ", ".join(repr(v) for v in VALID_LAYOUTS)
            msgs.append(
                f"football.scores layout={layout!r} is not valid. "
                f"Choose one of: {valid}.{hint}"
            )
        try:
            ZoneInfo(cfg.get("timezone", "America/New_York"))
        except ZoneInfoNotFoundError, ValueError, TypeError:
            msgs.append("football.scores timezone must name an IANA timezone")
        n = cfg.get("max_games", 8)
        if not _is_int(n) or n < 1:
            msgs.append(f"football.scores max_games must be a positive int, got {n!r}")
        hold = cfg.get("final_hold_hours", DEFAULT_FINAL_HOLD_HOURS)
        if not _is_int(hold) or hold < 0:
            msgs.append(
                f"football.scores final_hold_hours must be an int >= 0, got {hold!r}"
            )
        for name in ("hold_time", "padding"):
            if name in cfg:
                v = cfg[name]
                if not _is_number(v) or v < 0:
                    msgs.append(
                        f"football.scores {name} must be a number >= 0, got {v!r}"
                    )
        demo = cfg.get("demo")
        if demo is not None and not isinstance(demo, bool):
            msgs.append(
                f"football.scores demo must be a bool (true/false), got {demo!r}"
            )
        if "update_interval" in cfg:
            iv = cfg["update_interval"]
            if not _is_int(iv) or iv < 1:
                msgs.append(
                    f"football.scores update_interval must be a positive int "
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
            "football.scores: %d stories, mode=%s, polling every %ds",
            len(widget.feed_stories),
            widget.mode,
            interval,
        )
        # splay=False: core's default adds a fixed random 0-60 s to the
        # interval at startup (a 15 s live poll became 29 s on longboi,
        # 2026-10-26). The shared source already rate-limits itself.
        spawn_tracked(run_monitor_loop(widget, interval, splay=False))
        return widget

    # --- stories -----------------------------------------------------

    def _new_card(self, game: GameInfo) -> FootballGameCard:
        return FootballGameCard(
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
        )

    def _load_demo(self) -> None:
        games, td = build_demo_games(time.time())
        self._cards = {g.game_id: self._new_card(g) for g in games}
        live = self._cards[td.key.split(":")[0]]
        live.demo_plays = (td,)
        live.queue_plays([td])
        self._cards["demo-bye"].bye = True
        self.feed_stories = list(self._cards.values())
        logger.info("football.scores demo: %d stories", len(self.feed_stories))

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
            logger.exception("football.scores update failed; keeping last stories")

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
        next_keys = {g.game_id: (t, f"next:{t}") for t, g in snap.next_games.items()}
        cards: dict[_CardKey, FootballGameCard] = {}
        for game in chosen:
            team, key = (
                (None, game.game_id)
                if game.game_id in snap.games
                else next_keys.get(game.game_id, (None, game.game_id))
            )
            card = self._cards.get(key)
            if card is None:
                card = self._new_card(game)
            card.game = game
            card.drop_overturned()
            card.stale = snap.stale
            card.bye = team is not None and team in snap.bye_teams
            cards[key] = card
        self._queue_plays(source, snap, cards)
        # A game that left the selection (live mode: it just went final)
        # on the very poll that scored keeps its card until the score has
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
            "football.scores updated: %d stories%s",
            len(self.feed_stories),
            " (stale)" if snap.stale else "",
        )

    def _queue_plays(
        self,
        source: ESPNSource,
        snap: Snapshot,
        cards: dict[_CardKey, FootballGameCard],
    ) -> None:
        """Queue scoring plays this widget hasn't celebrated onto their cards.

        A game's first sight by THIS widget is a silent baseline, so a hot
        reload with a surviving shared source never replays old plays. A
        new key whose PRE-TRY snapshot was already celebrated or queued is
        a follow-up (the extra point re-keys a touchdown at the new score):
        it replaces the pending entry and never celebrates again. Snapshots
        above the current score are forgotten (a correction), so the next
        real score at that snapshot still celebrates.
        """
        for gid, game in snap.games.items():
            plays = source.plays_after_baseline(gid)
            seen = self._celebrated.get(gid)
            if seen is None:
                self._celebrated[gid] = {p.key for p in plays}
                self._celebrated_scores[gid] = {
                    pre_extra_score(p, game.home) for p in plays
                }
                continue
            scores = {
                s
                for s in self._celebrated_scores.get(gid, set())
                if s[0] <= game.away_score and s[1] <= game.home_score
            }
            self._celebrated_scores[gid] = scores
            # A correction also forgets the KEYS above the current score: a
            # touchdown overturned on review and scored again on the next
            # snap re-uses its key and must still celebrate.
            seen.difference_update(
                {
                    k
                    for k in seen
                    if not _key_within(k, game.away_score, game.home_score)
                }
            )
            new = [p for p in plays if p.key not in seen]
            if not new:
                continue
            seen.update(p.key for p in new)
            fresh: list[ScoringPlay] = []
            changed: list[ScoringPlay] = []
            for p in new:
                snap_key = pre_extra_score(p, game.home)
                (changed if snap_key in scores else fresh).append(p)
                scores.add(snap_key)
            card = cards.get(gid) or self._cards.get(gid)
            if card is not None:
                card.queue_plays(fresh)
                card.replace_plays(changed)
        self._celebrated = {
            gid: keys for gid, keys in self._celebrated.items() if gid in snap.games
        }
        self._celebrated_scores = {
            gid: s for gid, s in self._celebrated_scores.items() if gid in snap.games
        }
