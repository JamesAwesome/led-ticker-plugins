"""Shared ESPN snapshots: one fetcher per session, cadence-driven.

Every `basketball.scores` widget on a session shares one `ESPNSource`, so the
public API sees one request per interval however many widgets are
configured. A failed request keeps the last good games and backs off. A game
that drops out of the day payload keeps its last state: a final is never
inferred from a game disappearing.

Hosts are tried in order within ONE poll (`site.api` first, then the
`site.web.api` mirror); only both failing counts as a failure.

NBA games are a DAY model: today's scoreboard, plus yesterday's when a cached
live game is missing from today's (a late game that crossed midnight). The
final buzzer is a baseline-silent event: a game first seen already final never
produces a `FinalEvent`; only a live-to-final transition observed by this
source does.
"""

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import aiohttp

from led_ticker_basketball._models import (
    ESPN_TZ,
    FinalEvent,
    GameInfo,
    final_event,
    parse_event,
)

logger: logging.Logger = logging.getLogger(__name__)

HOSTS: tuple[str, ...] = ("https://site.api.espn.com", "https://site.web.api.espn.com")
PATH = "/apis/site/v2/sports/basketball/nba"
LIVE_INTERVAL = 15
TIPOFF_INTERVAL = 60
TIPOFF_WINDOW = 30 * 60
PREGAME_INTERVAL = 300
IDLE_INTERVAL = 3600
SCHEDULE_INTERVAL = 6 * 3600
SCHEDULE_RETRY = 60  # a FAILED schedule fetch retries this soon, not in 6 h
SCHEDULE_RETRY_LIVE = (
    600  # ... but only this often while a game is live (it stalls the poll)
)
SCHEDULE_TIMEOUT = 5  # the schedule is optional: never hold a live snapshot 20 s for it
LIVE_GRACE = 30 * 60  # a live game missing from one payload stays live this long
MIN_INTERVAL = 10
MAX_BACKOFF = 4 * 3600
REQUEST_TIMEOUT = 20
_MAX_SHARED_SOURCES = 8
_USER_AGENT = (
    "led-ticker-basketball (+https://github.com/JamesAwesome/led-ticker-plugins)"
)


@dataclass
class Snapshot:
    games: dict[str, GameInfo] = field(default_factory=dict)
    next_games: dict[str, GameInfo] = field(default_factory=dict)
    stale: bool = False
    error: str | None = None


class _FetchError(Exception):
    pass


class ESPNSource:
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
        self._next_hold_hours: int | None = None
        self._live_interval = LIVE_INTERVAL
        self._latest_ids: set[str] = set()
        self._games: dict[str, GameInfo] = {}
        self._last_seen: dict[str, datetime] = {}
        self._next: dict[str, GameInfo] = {}
        self._next_at: dict[str, float] = {}
        self._yesterday_ids: set[str] = set()
        # Final-buzzer baseline: state at FIRST sight, and the finals observed
        # arriving after it (set once, never overwritten).
        self._seen_state: dict[str, str] = {}
        self._finals: dict[str, FinalEvent] = {}
        # First-ever success; failures before it back off from LIVE_INTERVAL.
        self._ever_ok = False
        self._backoff = 0
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

    def note_displayed(self, consumer: object, game_ids: set[str]) -> None:
        """API symmetry with the sibling packs; the scoreboard payload already
        carries every live situation, so no per-game request is gated."""

    def _wanted(self, game: GameInfo) -> bool:
        return self._all_games or game.away in self._teams or game.home in self._teams

    # ------------------------------------------------------------- cadence

    def _active(self) -> list[GameInfo]:
        """Games that drive cadence and selection: this payload's, plus a
        LIVE game a partial payload left out, for `LIVE_GRACE` after it was
        last seen (the card still shows it live, so polling must stay live)."""
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
        now_utc = self._wall()
        starts = [g.start_utc for g in games if g.state == "future" and g.start_utc]
        for start in starts:
            until = (start - now_utc).total_seconds()
            if -TIPOFF_WINDOW <= until <= TIPOFF_WINDOW:
                return TIPOFF_INTERVAL
        today = now_utc.astimezone(self._tz).date()
        if any(start.astimezone(self._tz).date() == today for start in starts):
            return PREGAME_INTERVAL
        return IDLE_INTERVAL

    def next_delay(self) -> float:
        if self._backoff:
            return float(self._backoff)
        return float(max(MIN_INTERVAL, self._cadence()))

    def final_after_baseline(self, game_id: str) -> FinalEvent | None:
        """The final observed arriving AFTER this game's first sight (a game
        first seen final is the silent baseline). Non-consuming: every widget
        sees the same result and dedupes itself by key."""
        return self._finals.get(game_id)

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
        logger.warning("basketball: %s; next request in %ds", message, self._backoff)

    async def _get_host(self, url: str, timeout_s: float) -> Any:
        timeout = aiohttp.ClientTimeout(total=timeout_s)
        headers = {"Accept": "application/json", "User-Agent": _USER_AGENT}
        async with self.session.get(url, headers=headers, timeout=timeout) as resp:
            status = int(getattr(resp, "status", 200))
            if status >= 400:
                raise _FetchError(f"HTTP {status} from {url}")
            return await resp.json()

    async def _get(self, path: str, *, timeout_s: float = REQUEST_TIMEOUT) -> Any:
        """GET `path` from the first host that answers; the last host's
        failure propagates (`_FetchError`, `TimeoutError`, `ClientError`,
        `OSError`)."""
        last: BaseException | None = None
        for i, host in enumerate(HOSTS):
            try:
                return await self._get_host(f"{host}{path}", timeout_s)
            except (_FetchError, TimeoutError, aiohttp.ClientError, OSError) as exc:
                last = exc
                if i + 1 < len(HOSTS):
                    logger.debug("basketball: %s failed (%s); trying mirror", host, exc)
        assert last is not None
        raise last

    async def _fetch_day(
        self, polled_at: float, query: str = ""
    ) -> dict[str, GameInfo]:
        body = await self._get(f"{PATH}/scoreboard{query}")
        rows = body.get("events") if isinstance(body, dict) else None
        if not isinstance(rows, list):
            raise _FetchError("malformed scoreboard (no events list)")
        out: dict[str, GameInfo] = {}
        for row in rows:
            game = parse_event(row, polled_at=polled_at)
            if game is not None:
                out[game.game_id] = game
        return out

    def _yesterday_date(self) -> str:
        # ESPN's default /scoreboard slate is the EASTERN calendar day, so
        # "yesterday" is too -- never the widget's tz (a PT user at 21:30 is
        # already on the next Eastern day).
        day = self._wall().astimezone(ESPN_TZ).date() - timedelta(days=1)
        return day.strftime("%Y%m%d")

    async def _poll(self) -> None:
        now_utc = self._wall()
        polled_at = now_utc.timestamp()
        hold = timedelta(hours=self._hold_hours)
        try:
            fetched = await self._fetch_day(polled_at)
        except _FetchError as exc:
            self._fail(str(exc))
            return
        except TimeoutError:
            self._fail("request timed out")
            return
        except (aiohttp.ClientError, OSError) as exc:
            self._fail(f"network error: {exc.__class__.__name__}")
            return
        except Exception as exc:  # noqa: BLE001
            self._fail(f"unexpected error: {exc.__class__.__name__}: {exc}")
            return

        yday_ids: set[str] = set()
        if any(
            g.state == "live" and gid not in fetched for gid, g in self._games.items()
        ):
            # A cached live game today's feed omits may have tipped off before
            # midnight; yesterday's feed is where it lives. Soft: a failure
            # keeps today's good payload and lets the game ride the grace.
            try:
                yday = await self._fetch_day(
                    polled_at, f"?dates={self._yesterday_date()}"
                )
            except Exception as exc:  # noqa: BLE001 — soft
                logger.debug("basketball: yesterday feed failed: %s", exc)
            else:
                yday_ids = set(yday) - set(fetched)
                for gid, game in yday.items():
                    fetched.setdefault(gid, game)
        self._yesterday_ids = yday_ids

        self._latest_ids = {g for g, v in fetched.items() if self._wanted(v)}
        for gid, game in fetched.items():
            if not self._wanted(game):
                continue
            self._games[gid] = game
            self._last_seen[gid] = now_utc
            self._track_final(game)
        grace = timedelta(seconds=LIVE_GRACE)

        def keep_for(gid: str) -> timedelta:
            # A live game a partial payload omitted must outlive the hold (0
            # is valid) long enough for `_active()`'s grace to see it.
            g = self._games.get(gid)
            return max(hold, grace) if g is not None and g.state == "live" else hold

        for gid in [g for g, t in self._last_seen.items() if now_utc - t > keep_for(g)]:
            for store in (self._games, self._last_seen, self._seen_state, self._finals):
                store.pop(gid, None)
        for gid in [g for g in self._games if not self._wanted(self._games[g])]:
            self._games.pop(gid)

        await self._refresh_next()

        self._backoff = 0
        self._ever_ok = True
        self.snapshot = Snapshot(
            games=dict(self._games), next_games=dict(self._next), stale=False
        )

    def _track_final(self, game: GameInfo) -> None:
        gid = game.game_id
        seen = self._seen_state.setdefault(gid, game.state)
        if seen == "final" or game.state != "final" or gid in self._finals:
            return
        event = final_event(game)
        if event is not None:
            self._finals[gid] = event

    def _playing(self) -> set[str]:
        """Teams whose card comes from `_games`: a live game or a game still
        to come today. A held final does NOT count: its hold expires
        between polls (idle cadence), and the widget's selection must find
        the next game ready at that moment, not an hour later."""
        return {
            t
            for g in self._active()
            if g.state in ("live", "future")
            for t in (g.away, g.home)
        }

    async def _refresh_next(self) -> None:
        playing = self._playing()
        now = self._clock()
        for team in sorted(self._teams):
            if team in playing:
                self._next.pop(team, None)
                continue
            last = self._next_at.get(team)
            if last is not None and now - last < SCHEDULE_INTERVAL:
                continue
            self._next_at[team] = now
            try:
                body = await self._get(
                    f"{PATH}/teams/{team}/schedule", timeout_s=SCHEDULE_TIMEOUT
                )
            except Exception as exc:  # noqa: BLE001 — soft: schedule is optional
                logger.debug("basketball: schedule fetch failed (%s): %s", team, exc)
                body = None
            if not isinstance(body, dict):
                # One failure must not blank a team's next-game card for 6 h:
                # retry soon — but sparingly while a game is live, since this
                # fetch runs inside the poll and delays the live snapshot.
                live = any(g.state == "live" for g in self._active())
                retry = SCHEDULE_RETRY_LIVE if live else SCHEDULE_RETRY
                self._next_at[team] = now - SCHEDULE_INTERVAL + retry
                continue
            rows = body.get("events")
            wall = self._wall().timestamp()
            for row in rows if isinstance(rows, list) else []:
                game = (
                    parse_event(row, polled_at=wall) if isinstance(row, dict) else None
                )
                if game is not None and game.state == "future":
                    self._next[team] = game
                    break


_SHARED_SOURCES: dict[int, ESPNSource] = {}


def shared_source(session: Any) -> ESPNSource:
    """One source per session; capped, oldest evicted (hot reloads add sessions)."""
    key = id(session)
    source = _SHARED_SOURCES.pop(key, None)
    if source is None:
        source = ESPNSource(session)
    _SHARED_SOURCES[key] = source
    while len(_SHARED_SOURCES) > _MAX_SHARED_SOURCES:
        del _SHARED_SOURCES[next(iter(_SHARED_SOURCES))]
    return source
