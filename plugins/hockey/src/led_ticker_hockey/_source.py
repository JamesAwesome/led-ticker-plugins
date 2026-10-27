"""Shared NHL snapshots: one fetcher per session, cadence-driven.

Every `hockey.scores` widget on a session shares one `NHLSource`, so the
public API sees one request per endpoint per interval however many widgets
are configured. A failed request keeps the last good games and backs off.
A game that drops out of the feed keeps its last state: a final is never
inferred from a game disappearing.
"""

import asyncio
import dataclasses
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import aiohttp

from led_ticker_hockey._models import (
    GameInfo,
    Goal,
    final_in_hold,
    parse_game,
    parse_situation,
)

logger: logging.Logger = logging.getLogger(__name__)

BASE_URL = "https://api-web.nhle.com"
LIVE_INTERVAL = 15
PREGAME_INTERVAL = 300
IDLE_INTERVAL = 3600
SEASON_INTERVAL = 6 * 3600
MIN_INTERVAL = 10
MAX_BACKOFF = 4 * 3600
LIVE_GRACE = 30 * 60  # a live game missing from one payload stays live this long
REQUEST_TIMEOUT = 20
_MAX_SHARED_SOURCES = 8
_USER_AGENT = "led-ticker-hockey (+https://github.com/JamesAwesome/led-ticker-plugins)"
_UPCOMING_STATES = ("FUT", "PRE")
_DISPLAYED_TTL = 600  # seconds a consumer's displayed set stays valid


@dataclass
class Snapshot:
    games: dict[int, GameInfo] = field(default_factory=dict)
    next_games: dict[str, GameInfo] = field(default_factory=dict)
    stale: bool = False
    error: str | None = None


class _FetchError(Exception):
    pass


class NHLSource:
    def __init__(
        self,
        session: Any,
        *,
        clock: Callable[[], float] = time.monotonic,
        wall: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.session = session
        self._clock = clock
        self._wall = wall
        self._lock = asyncio.Lock()
        self._teams: set[str] = set()
        self._all_games = False
        self._tz: ZoneInfo = ZoneInfo("UTC")
        self._hold_hours = 0
        # The SHORTEST widget hold: past it some widget needs the next game.
        self._next_hold_hours: int | None = None
        self._live_interval = LIVE_INTERVAL
        self._displayed_by: dict[int, tuple[float, set[int]]] = {}
        self._latest_ids: set[int] = set()
        self._games: dict[int, GameInfo] = {}
        self._last_seen: dict[int, datetime] = {}
        self._yesterday_ids: set[int] = set()
        self._next: dict[str, GameInfo] = {}
        self._next_month_at: dict[str, float] = {}
        self._next_season_at: dict[str, float] = {}
        self._known_goals: dict[int, set[str]] = {}
        self._situations: dict[int, Any] = {}
        self._backoff = 0
        self._ever_ok = False
        self._next_allowed = float("-inf")
        self.snapshot = Snapshot()

    # ------------------------------------------------------------ interest

    def want(
        self,
        *,
        teams: set[str],
        all_games: bool,
        tz: ZoneInfo,
        final_hold_hours: int,
        live_interval: int = LIVE_INTERVAL,
    ) -> None:
        """Union interest: teams union, all_games OR, latest tz, max hold
        (min hold for the next-game lookup), fastest live cadence."""
        grew = bool(
            {t.upper() for t in teams} - self._teams
            or (all_games and not self._all_games)
        )
        self._teams |= {t.upper() for t in teams}
        self._all_games = self._all_games or all_games
        self._tz = tz
        self._hold_hours = max(self._hold_hours, final_hold_hours)
        self._next_hold_hours = (
            final_hold_hours
            if self._next_hold_hours is None
            else min(self._next_hold_hours, final_hold_hours)
        )
        self._live_interval = min(self._live_interval, live_interval)
        if grew:
            self._next_allowed = float("-inf")

    def _displayed_union(self) -> set[int]:
        now = self._clock()
        self._displayed_by = {
            k: v for k, v in self._displayed_by.items() if now - v[0] < _DISPLAYED_TTL
        }
        return set().union(*(ids for _, ids in self._displayed_by.values()))

    def note_displayed(self, consumer: object, game_ids: set[int]) -> None:
        """Per-consumer displayed ids; landing calls use the union."""
        before = self._displayed_union()
        self._displayed_by[id(consumer)] = (self._clock(), set(game_ids))
        if self._displayed_union() - before:
            self._next_allowed = float("-inf")

    def _wanted(self, game: GameInfo) -> bool:
        return self._all_games or game.away in self._teams or game.home in self._teams

    # ------------------------------------------------------------- cadence

    def _active(self) -> list[GameInfo]:
        """Games that drive cadence only (`_playing` keeps iterating `_games`):
        this payload's, plus a LIVE game a partial payload left out, for
        `LIVE_GRACE` after it was last seen (the card still shows it live, so
        polling must stay live)."""
        now_utc = self._wall()
        out: list[GameInfo] = []
        for gid, g in self._games.items():
            if gid in self._latest_ids:
                out.append(g)
            elif g.state == "live":
                seen = self._last_seen.get(gid)
                if seen is not None and (now_utc - seen).total_seconds() <= LIVE_GRACE:
                    out.append(g)
        return out

    def _cadence(self) -> float:
        games = self._active()
        if any(g.state == "live" for g in games):
            return max(MIN_INTERVAL, self._live_interval)
        if any(g.state == "future" for g in games):
            return PREGAME_INTERVAL
        return IDLE_INTERVAL

    def next_delay(self) -> float:
        if self._backoff:
            return float(self._backoff)
        return float(max(MIN_INTERVAL, self._cadence()))

    def goals_after_baseline(self, game_id: int) -> tuple[Goal, ...]:
        """Goals in the current feed that weren't there on first sight.

        Non-consuming: every widget sees the same result and dedupes itself.
        """
        game = self._games.get(game_id)
        baseline = self._known_goals.get(game_id)
        if game is None or baseline is None:
            return ()
        return tuple(g for g in game.goals if g.key not in baseline)

    # ---------------------------------------------------------------- poll

    async def poll(self) -> Snapshot:
        """Never raises. Gated so widgets sharing the source don't double up."""
        async with self._lock:
            try:
                if self._clock() < self._next_allowed:
                    return self.snapshot
                await self._poll()
            except Exception as exc:  # noqa: BLE001 — never into the loop
                self._fail(f"unexpected error: {exc.__class__.__name__}: {exc}")
            self._next_allowed = self._clock() + self.next_delay()
            return self.snapshot

    def _fail(self, message: str) -> None:
        # Before anything ever loaded the cadence reads IDLE (no games): a
        # sign that boots before its network must retry in seconds, not hours.
        base = max(MIN_INTERVAL, self._cadence()) if self._ever_ok else LIVE_INTERVAL
        self._backoff = (
            min(MAX_BACKOFF, self._backoff * 2) if self._backoff else 2 * base
        )
        self._backoff = min(MAX_BACKOFF, self._backoff)
        self.snapshot = Snapshot(
            games=dict(self._games),
            next_games=dict(self._next),
            stale=True,
            error=message,
        )
        logger.warning("hockey: %s; next request in %ds", message, self._backoff)

    async def _get(self, url: str) -> Any:
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
        headers = {"Accept": "application/json", "User-Agent": _USER_AGENT}
        async with self.session.get(url, headers=headers, timeout=timeout) as resp:
            status = int(getattr(resp, "status", 200))
            if status >= 400:
                raise _FetchError(f"HTTP {status} from {url}")
            return await resp.json()

    async def _fetch_scores(self, day: Any, polled_at: float) -> dict[int, GameInfo]:
        body = await self._get(f"{BASE_URL}/v1/score/{day.isoformat()}")
        rows = body.get("games") if isinstance(body, dict) else None
        if not isinstance(rows, list):
            raise _FetchError("malformed score feed (no games list)")
        out: dict[int, GameInfo] = {}
        for row in rows:
            game = parse_game(row, polled_at=polled_at)
            if game is not None:
                out[game.game_id] = game
        return out

    async def _poll(self) -> None:
        # Wall epoch, the time base renderers tick clocks against
        # (`time.time()`); the gate/TTL/cadence stay on the monotonic clock.
        now_utc = self._wall()
        polled_at = now_utc.timestamp()
        local = now_utc.astimezone(self._tz)
        today = local.date()
        since_midnight = local - local.replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        hold = timedelta(hours=self._hold_hours)

        fetched: dict[int, GameInfo] = {}
        yday_ids: set[int] = set()
        want_yday = since_midnight < hold or any(
            self._games[i].state != "final"
            for i in self._yesterday_ids
            if i in self._games
        )
        try:
            fetched.update(await self._fetch_scores(today, polled_at))
            if want_yday:
                yday = await self._fetch_scores(today - timedelta(days=1), polled_at)
                yday_ids = set(yday) - set(fetched)
                for gid, game in yday.items():
                    fetched.setdefault(gid, game)
        except _FetchError as exc:
            self._fail(str(exc))
            return
        except TimeoutError:
            self._fail("request timed out")
            return
        except aiohttp.ClientError as exc:
            self._fail(f"network error: {exc.__class__.__name__}")
            return
        except Exception as exc:  # noqa: BLE001
            self._fail(f"unexpected error: {exc.__class__.__name__}: {exc}")
            return

        # Commit: merge, remember last-seen, drop anything past the hold.
        self._yesterday_ids = yday_ids
        self._latest_ids = {g for g, v in fetched.items() if self._wanted(v)}
        for gid, game in fetched.items():
            if self._wanted(game):
                self._games[gid] = game
                self._last_seen[gid] = now_utc
                self._track_goals(game)
        for gid in [g for g, t in self._last_seen.items() if now_utc - t > hold]:
            self._games.pop(gid, None)
            self._last_seen.pop(gid, None)
            self._situations.pop(gid, None)
            self._known_goals.pop(gid, None)
        for gid in [g for g in self._games if not self._wanted(self._games[g])]:
            self._games.pop(gid)

        await self._attach_situations()
        await self._refresh_next(fetched)

        self._backoff = 0
        self._ever_ok = True
        self.snapshot = Snapshot(
            games=dict(self._games), next_games=dict(self._next), stale=False
        )

    def _track_goals(self, game: GameInfo) -> None:
        # First sight: whatever is already scored is the silent baseline.
        self._known_goals.setdefault(game.game_id, {g.key for g in game.goals})

    async def _attach_situations(self) -> None:
        displayed = self._displayed_union()
        for gid, game in list(self._games.items()):
            if game.state != "live" or gid not in displayed:
                self._situations.pop(gid, None)
                continue
            try:
                landing = await self._get(f"{BASE_URL}/v1/gamecenter/{gid}/landing")
                self._situations[gid] = parse_situation(landing)
            except Exception as exc:  # noqa: BLE001 — soft: keep previous
                logger.debug("hockey: landing %d failed: %s", gid, exc)
            self._games[gid] = dataclasses.replace(
                game, situation=self._situations.get(gid)
            )

    def _playing(self) -> set[str]:
        """Teams whose card comes from `_games`, not the next-game lookup:
        a live game, or a final still inside the hold under the SAME
        predicate `select_stories` uses (at the shortest widget hold). A
        future game does not count: one after local midnight isn't
        "later today", so the lookup is what shows it before puck drop."""
        now_dt = self._wall()
        hold = self._next_hold_hours or 0
        return {
            t
            for g in self._games.values()
            if g.state == "live"
            or (g.state == "final" and final_in_hold(g, now_dt, hold))
            for t in (g.away, g.home)
        }

    async def _refresh_next(self, fetched: dict[int, GameInfo]) -> None:
        playing = self._playing()
        now = self._clock()
        for team in sorted(self._teams):
            if team in playing:
                self._next.pop(team, None)
                continue
            if team in self._next_month_at and (
                now - self._next_month_at[team] < IDLE_INTERVAL
            ):
                continue
            self._next_month_at[team] = now
            wall = self._wall().timestamp()
            game = await self._first_future(
                f"{BASE_URL}/v1/club-schedule/{team}/month/now", wall
            )
            if game is None and (
                team not in self._next_season_at
                or now - self._next_season_at[team] >= SEASON_INTERVAL
            ):
                self._next_season_at[team] = now
                game = await self._first_future(
                    f"{BASE_URL}/v1/club-schedule-season/{team}/now", wall
                )
            if game is not None:
                self._next[team] = game

    async def _first_future(self, url: str, polled_at: float) -> GameInfo | None:
        try:
            body = await self._get(url)
            rows = body.get("games") if isinstance(body, dict) else None
            for row in rows if isinstance(rows, list) else []:
                if isinstance(row, dict) and row.get("gameState") in _UPCOMING_STATES:
                    game = parse_game(row, polled_at=polled_at)
                    if game is not None:
                        return game
        except Exception as exc:  # noqa: BLE001 — soft: schedule is optional
            logger.debug("hockey: schedule fetch failed (%s): %s", url, exc)
        return None


_SHARED_SOURCES: dict[int, NHLSource] = {}


def shared_source(session: Any) -> NHLSource:
    """One source per session; capped, oldest evicted (hot reloads add sessions)."""
    key = id(session)
    source = _SHARED_SOURCES.pop(key, None)
    if source is None:
        source = NHLSource(session)
    _SHARED_SOURCES[key] = source
    while len(_SHARED_SOURCES) > _MAX_SHARED_SOURCES:
        del _SHARED_SOURCES[next(iter(_SHARED_SOURCES))]
    return source
