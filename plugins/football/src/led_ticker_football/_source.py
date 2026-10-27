"""Shared ESPN snapshots: one fetcher per session, cadence-driven.

Every `football.scores` widget on a session shares one `ESPNSource`, so the
public API sees one request per interval however many widgets are
configured. A failed request keeps the last good games and backs off. A game
that drops out of the week payload keeps its last state: a final is never
inferred from a game disappearing.

Hosts are tried in order within ONE poll (`site.api` first, then the
`site.web.api` mirror that stayed up through the August 2026 403s); only
both failing counts as a failure.

Scoring plays are derived here from score deltas (`_models.diff_scores`) so
every widget sees the same plays; the first sight of a game is a silent
baseline.
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

from led_ticker_football._models import (
    GameInfo,
    ScoringPlay,
    diff_scores,
    parse_event,
)

logger: logging.Logger = logging.getLogger(__name__)

HOSTS: tuple[str, ...] = ("https://site.api.espn.com", "https://site.web.api.espn.com")
PATH = "/apis/site/v2/sports/football/nfl"
LIVE_INTERVAL = 15
KICKOFF_INTERVAL = 60
KICKOFF_WINDOW = 30 * 60
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
    "led-ticker-football (+https://github.com/JamesAwesome/led-ticker-plugins)"
)
_HELD_STATUS = "STATUS_IN_PROGRESS"  # the only status whose possession carries over


@dataclass
class Snapshot:
    games: dict[str, GameInfo] = field(default_factory=dict)
    next_games: dict[str, GameInfo] = field(default_factory=dict)
    bye_teams: frozenset[str] = frozenset()
    week: int | None = None
    stale: bool = False
    error: str | None = None


class _FetchError(Exception):
    pass


def _int_or_none(v: Any) -> int | None:
    return v if isinstance(v, int) and not isinstance(v, bool) else None


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
        self._bye: set[str] = set()
        self._bye_weeks: dict[str, int] = {}  # team -> byeWeek from its schedule
        self._week: int | None = None
        # Scoring: last seen (away, home) per game, plays since first sight,
        # and the one touchdown still waiting for its extra point.
        self._prev: dict[str, tuple[int, int]] = {}
        self._plays: dict[str, list[ScoringPlay]] = {}
        self._open_td: dict[str, ScoringPlay] = {}
        self._open_td_period: dict[str, int] = {}
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
            if -KICKOFF_WINDOW <= until <= KICKOFF_WINDOW:
                return KICKOFF_INTERVAL
        today = now_utc.astimezone(self._tz).date()
        if any(start.astimezone(self._tz).date() == today for start in starts):
            return PREGAME_INTERVAL
        return IDLE_INTERVAL

    def next_delay(self) -> float:
        if self._backoff:
            return float(self._backoff)
        return float(max(MIN_INTERVAL, self._cadence()))

    def plays_after_baseline(self, game_id: str) -> tuple[ScoringPlay, ...]:
        """Scoring plays since this game was first seen (the baseline is
        silent). Non-consuming: every widget sees the same result and
        dedupes itself by key."""
        return tuple(self._plays.get(game_id, ()))

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
            bye_teams=frozenset(self._bye),
            week=self._week,
            stale=True,
            error=message,
        )
        logger.warning("football: %s; next request in %ds", message, self._backoff)

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
                    logger.debug("football: %s failed (%s); trying mirror", host, exc)
        assert last is not None
        raise last

    async def _fetch_week(self, polled_at: float) -> tuple[dict[str, GameInfo], dict]:
        body = await self._get(f"{PATH}/scoreboard")
        rows = body.get("events") if isinstance(body, dict) else None
        if not isinstance(rows, list):
            raise _FetchError("malformed scoreboard (no events list)")
        out: dict[str, GameInfo] = {}
        for row in rows:
            game = parse_event(row, polled_at=polled_at)
            if game is not None:
                out[game.game_id] = game
        return out, body

    async def _poll(self) -> None:
        now_utc = self._wall()
        polled_at = now_utc.timestamp()
        hold = timedelta(hours=self._hold_hours)
        try:
            fetched, body = await self._fetch_week(polled_at)
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

        week_raw = body.get("week")
        week: dict[str, Any] = week_raw if isinstance(week_raw, dict) else {}
        self._week = _int_or_none(week.get("number"))
        byes = week.get("teamsOnBye")
        self._bye = {
            str(t.get("abbreviation", "")).upper()
            for t in (byes if isinstance(byes, list) else [])
            if isinstance(t, dict) and t.get("abbreviation")
        } | {t for t, wk in self._bye_weeks.items() if wk == self._week}

        self._latest_ids = {g for g, v in fetched.items() if self._wanted(v)}
        for gid, game in fetched.items():
            if not self._wanted(game):
                continue
            game = self._hold_possession(game)
            self._games[gid] = game
            self._last_seen[gid] = now_utc
            self._track_scores(game)
        for gid in [g for g, t in self._last_seen.items() if now_utc - t > hold]:
            for store in (
                self._games,
                self._last_seen,
                self._prev,
                self._plays,
                self._open_td,
                self._open_td_period,
            ):
                store.pop(gid, None)
        for gid in [g for g in self._games if not self._wanted(self._games[g])]:
            self._games.pop(gid)

        await self._refresh_next()

        self._backoff = 0
        self._ever_ok = True
        self.snapshot = Snapshot(
            games=dict(self._games),
            next_games=dict(self._next),
            bye_teams=frozenset(self._bye),
            week=self._week,
            stale=False,
        )

    def _hold_possession(self, game: GameInfo) -> GameInfo:
        """A dead-ball poll drops `possession` for a few seconds; carry the
        previous poll's over while the game is in progress in the same
        period. Halftime, end of period, a period change or a final clear
        it (the new game simply has no possession to hold)."""
        sit = game.situation
        if sit is None or sit.possession is not None:
            return game
        if game.state != "live" or game.status != _HELD_STATUS:
            return game
        old = self._games.get(game.game_id)
        if (
            old is None
            or old.state != "live"
            or old.status != _HELD_STATUS
            or old.period != game.period
            or old.situation is None
            or old.situation.possession is None
        ):
            return game
        held = dataclasses.replace(sit, possession=old.situation.possession)
        return dataclasses.replace(game, situation=held)

    def _track_scores(self, game: GameInfo) -> None:
        gid = game.game_id
        cur = (game.away_score, game.home_score)
        prev = self._prev.get(gid)
        self._prev[gid] = cur
        plays = self._plays.setdefault(gid, [])
        if prev is None:
            return  # first sight: whatever is already scored is the baseline
        td = self._open_td.get(gid)
        if td is not None and self._try_over(game, td):
            self._close_td(gid)
        if cur[0] < prev[0] or cur[1] < prev[1]:
            # Correction: forget plays the new score no longer supports.
            plays[:] = [
                p for p in plays if p.away_score <= cur[0] and p.home_score <= cur[1]
            ]
            td = self._open_td.get(gid)
            if td is not None:
                # Only the TD team's OWN side going down overturns it; a
                # correction to the other side leaves its try to come.
                side = 0 if td.team == game.away else 1
                if cur[side] < prev[side]:
                    self._close_td(gid)
            return
        if cur == prev:
            return
        new, follow = diff_scores(game, prev, self._open_td.get(gid))
        if follow is not None:
            old = self._open_td.pop(gid, None)
            if old is not None and any(p.key == old.key for p in plays):
                plays[:] = [follow if p.key == old.key else p for p in plays]
            else:
                plays.append(follow)
        if new:
            # Any fresh score closes a touchdown still waiting for its try:
            # a later +1/+2 can't belong to it any more.
            self._close_td(gid)
        for p in new:
            plays.append(p)
            if p.kind == "TD" and not p.extra:
                self._open_td[gid] = p
                self._open_td_period[gid] = game.period

    def _close_td(self, gid: str) -> None:
        self._open_td.pop(gid, None)
        self._open_td_period.pop(gid, None)

    def _try_over(self, game: GameInfo, td: ScoringPlay) -> bool:
        """A touchdown waits for its try only until the try is over: a
        period change, or the OTHER team running a live down (a try is
        never the opponent's down). A later +2 is then a SAFETY."""
        if game.period != self._open_td_period.get(game.game_id, game.period):
            return True
        sit = game.situation
        return (
            sit is not None
            and sit.possession is not None
            and sit.possession != td.team
            and bool(sit.down_distance)
        )

    def _playing(self) -> set[str]:
        """Teams whose card comes from `_games`: a live game or a game still
        to come this week. A held final does NOT count: its hold expires
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
                logger.debug("football: schedule fetch failed (%s): %s", team, exc)
                body = None
            if not isinstance(body, dict):
                # One failure must not blank a bye-week team's card for 6 h:
                # retry soon — but sparingly while a game is live, since this
                # fetch runs inside the poll and delays the live snapshot.
                live = any(g.state == "live" for g in self._active())
                retry = SCHEDULE_RETRY_LIVE if live else SCHEDULE_RETRY
                self._next_at[team] = now - SCHEDULE_INTERVAL + retry
                continue
            bye = _int_or_none(body.get("byeWeek"))
            if bye is not None:
                self._bye_weeks[team] = bye
                if self._week is not None and bye == self._week:
                    self._bye.add(team)
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
