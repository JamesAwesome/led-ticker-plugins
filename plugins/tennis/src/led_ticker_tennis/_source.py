"""Shared tennis snapshots, with one request per interval across all endpoints.

The 900-second floor permits 96 requests per day against the free 100/day quota.
Result lookups replace listing polls and alternate with live polls.
Only displayed matches get a lookup after disappearing from the live listing.
A failed request keeps the last good payload and backs off.
Rejected keys wait at least an hour, or longer when the interval requires it.
"""

import asyncio
import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import aiohttp

logger: logging.Logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.livetennisapi.com/api/public/v1"
ENV_KEY = "LIVETENNIS_API_KEY"
FREE_KEY_URL = "https://livetennisapi.com/subscribe/free"

MIN_UPDATE_INTERVAL = 900  # seconds — 96 requests/day on a 100/day quota
MAX_BACKOFF = 4 * 3600
KEY_REJECTED_BACKOFF = 3600
RESOLVED_TTL_INTERVALS = 4  # a looked-up match is not looked up again for this long
_MAX_SHARED_SOURCES = 8  # distinct API keys kept per process (hot reloads add keys)
REQUEST_TIMEOUT = 20  # seconds, whole request
LIVE_LIMIT = 200  # API maximum per page
UPCOMING_LIMIT = 100
_USER_AGENT = "led-ticker-tennis (+https://github.com/JamesAwesome/led-ticker-plugins)"


def resolve_api_key(configured: str | None) -> str:
    """Prefer the environment, with config as a fallback."""
    return (os.environ.get(ENV_KEY) or "").strip() or (configured or "").strip()


def clamp_interval(interval: Any) -> int:
    """`update_interval` with the free-tier floor applied. Non-numeric or
    non-positive values fall back to the floor."""
    try:
        wanted = int(interval)
    except TypeError, ValueError:
        wanted = MIN_UPDATE_INTERVAL
    if wanted < MIN_UPDATE_INTERVAL:
        logger.warning(
            "tennis: update_interval=%s is below the free-tier floor; using %ds "
            "(100 requests/day => one poll per 15 min)",
            interval,
            MIN_UPDATE_INTERVAL,
        )
        return MIN_UPDATE_INTERVAL
    return wanted


@dataclass
class Snapshot:
    """What the widget renders from. `live`/`upcoming` are raw API rows (the
    last GOOD payload of each kind — a failed fetch never blanks them)."""

    live: list[dict[str, Any]] = field(default_factory=list)
    upcoming: list[dict[str, Any]] = field(default_factory=list)
    recent: list[dict[str, Any]] = field(default_factory=list)
    stale: bool = False  # the most recent attempt failed; data is older
    last_error: str | None = None
    key_rejected: bool = False
    live_fetched_at: float | None = None  # monotonic clock
    upcoming_fetched_at: float | None = None
    requests_made: int = 0


class LiveTennisSource:
    def __init__(
        self,
        session: Any,
        api_key: str,
        *,
        interval: int = MIN_UPDATE_INTERVAL,
        base_url: str = DEFAULT_BASE_URL,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.session = session
        self.api_key = api_key
        self.interval: int = clamp_interval(interval)
        self.base_url = base_url.rstrip("/")
        self._clock = clock
        self.snapshot = Snapshot()
        self._next_allowed: float = float("-inf")
        self._backoff: int = 0
        self._last_kind: str = ""
        self._lock = asyncio.Lock()
        self._watched: dict[int, dict[str, Any]] = {}
        self._pending: dict[int, dict[str, Any]] = {}
        self._resolved: dict[int, float] = {}  # match id -> expiry (monotonic)
        self._recent: dict[int, tuple[dict[str, Any], float]] = {}
        self._last_was_detail = False

    def remember_displayed(self, match_ids: list[int]) -> None:
        """Track only matches selected for a widget's rotation."""
        selected = set(match_ids)
        for row in self.snapshot.live:
            match_id = row.get("id")
            if isinstance(match_id, int) and match_id > 0 and match_id in selected:
                self._watched[match_id] = row

    def _refresh_recent(self) -> None:
        now = self._clock()
        self._recent = {k: v for k, v in self._recent.items() if v[1] > now}
        self._resolved = {k: t for k, t in self._resolved.items() if t > now}
        self.snapshot.recent = [row for row, _ in self._recent.values()] + [
            {**row, "_stale": True} for row in self._pending.values()
        ]

    def _replace_live(self, rows: list[dict[str, Any]]) -> None:
        current = {
            match_id: row for row in rows if isinstance(match_id := row.get("id"), int)
        }
        for match_id, row in self._watched.items():
            if match_id not in current and match_id not in self._resolved:
                self._pending.setdefault(match_id, row)
        self._watched = {k: current[k] for k in self._watched if k in current}
        for match_id in current:
            self._pending.pop(match_id, None)
            self._recent.pop(match_id, None)
        self.snapshot.live = rows

    # --- scheduling ---------------------------------------------------

    def _next_kind(self) -> str:
        if self.snapshot.live:
            return "live"
        return "upcoming" if self._last_kind == "live" else "live"

    def seconds_until_allowed(self) -> float:
        return max(0.0, self._next_allowed - self._clock())

    async def poll(self) -> Snapshot:
        """Serialize callers so concurrent widgets share one request."""
        async with self._lock:
            return await self._poll()

    async def _poll(self) -> Snapshot:
        self._refresh_recent()
        now = self._clock()
        if now < self._next_allowed:
            logger.debug(
                "tennis: poll skipped, %.0fs until next allowed request",
                self._next_allowed - now,
            )
            return self.snapshot

        match_id = (
            next(iter(self._pending), None) if not self._last_was_detail else None
        )
        kind = "live" if self._last_was_detail else self._next_kind()
        # Reserve the interval before awaiting I/O, including cancellation.
        self._next_allowed = now + self.interval
        ok = await self._fetch(kind, match_id=match_id)
        self._last_was_detail = match_id is not None

        if ok:
            # Only a SUCCESSFUL fetch advances the alternation: a failed
            # live fetch is retried as live once the backoff clears.
            if match_id is None:
                self._last_kind = kind
            self._backoff = 0
            self._next_allowed = self._clock() + self.interval
        self._refresh_recent()
        return self.snapshot

    # --- fetching -----------------------------------------------------

    def _url(self, kind: str) -> str:
        limit = LIVE_LIMIT if kind == "live" else UPCOMING_LIMIT
        return f"{self.base_url}/matches?status={kind}&limit={limit}"

    def _resolve(self, match_id: int) -> None:
        ttl = RESOLVED_TTL_INTERVALS * self.interval
        self._resolved[match_id] = self._clock() + ttl

    def _fail(self, message: str, *, retry_after: int | None = None) -> None:
        snap = self.snapshot
        snap.stale = True
        snap.last_error = message
        step = self._backoff * 2 if self._backoff else self.interval * 2
        wait = max(self.interval, step, retry_after or 0)
        self._backoff = min(MAX_BACKOFF, wait)
        self._next_allowed = self._clock() + self._backoff
        logger.warning("tennis: %s; next request in %ds", message, self._backoff)

    async def _fetch(self, kind: str, *, match_id: int | None = None) -> bool:
        snap = self.snapshot
        snap.requests_made += 1
        headers = {
            "X-API-Key": self.api_key,
            "Accept": "application/json",
            "User-Agent": _USER_AGENT,
        }
        url = (
            self._url(kind)
            if match_id is None
            else f"{self.base_url}/matches/{match_id}"
        )
        try:
            timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            async with self.session.get(url, headers=headers, timeout=timeout) as resp:
                status = int(getattr(resp, "status", 200))
                if status in (401, 403):
                    snap.key_rejected = True
                    self._fail(
                        f"API key rejected (HTTP {status})",
                        retry_after=KEY_REJECTED_BACKOFF,
                    )
                    return False
                if status == 429:
                    self._fail(
                        "rate limited (HTTP 429)", retry_after=_retry_after(resp)
                    )
                    return False
                if match_id is not None and status in (404, 410):
                    # The normal answer for a match the API no longer serves,
                    # not a failure: keep the last-seen row, stop asking, and
                    # leave staleness and backoff alone for the other matches.
                    row = {**self._pending.pop(match_id), "_stale": True}
                    self._recent[match_id] = (row, self._clock() + 2 * self.interval)
                    self._resolve(match_id)
                    logger.info(
                        "tennis: match %d detail unavailable (HTTP %d)",
                        match_id,
                        status,
                    )
                    return False
                if status >= 400:
                    self._fail(f"HTTP {status} from {url}")
                    return False
                body = await resp.json()
        except TimeoutError:
            self._fail("request timed out")
            return False
        except aiohttp.ClientError as exc:
            self._fail(f"network error: {exc.__class__.__name__}")
            return False
        except Exception as exc:  # noqa: BLE001 — never into the render loop
            self._fail(f"unexpected error: {exc.__class__.__name__}: {exc}")
            return False

        if match_id is not None:
            if not isinstance(body, dict) or body.get("id") != match_id:
                self._fail("malformed match detail")
                return False
            if body.get("status") not in ("live", "upcoming", "completed", "cancelled"):
                self._fail("unknown match status")
                return False
            self._pending.pop(match_id, None)
            self._resolve(match_id)
            row = {**body, "_stale": body["status"] in ("live", "upcoming")}
            self._recent[match_id] = (row, self._clock() + 2 * self.interval)
            snap.stale = False
            snap.last_error = None
            snap.key_rejected = False
            return True

        rows = _rows(body)
        if rows is None:
            self._fail("malformed response (no `data` list)")
            return False

        now = self._clock()
        if kind == "live":
            self._replace_live(rows)
            snap.live_fetched_at = now
        else:
            snap.upcoming = rows
            snap.upcoming_fetched_at = now
        snap.stale = False
        snap.last_error = None
        snap.key_rejected = False
        logger.info("tennis: fetched %d %s match(es)", len(rows), kind)
        return True


_SHARED_SOURCES: dict[str, LiveTennisSource] = {}


def shared_source(session: Any, api_key: str, *, interval: int) -> LiveTennisSource:
    """Keep one snapshot and request gate per key in this process.

    Core has no per-widget teardown hook, so entries are not released when a
    widget goes away. The map is keyed by API key and capped: past
    `_MAX_SHARED_SOURCES` keys, the least recently requested one is dropped.
    """
    source = _SHARED_SOURCES.pop(api_key, None)
    if source is None:
        source = LiveTennisSource(session, api_key, interval=interval)
    else:
        source.interval = min(source.interval, clamp_interval(interval))
        if getattr(source.session, "closed", False) is True:
            source.session = session
    _SHARED_SOURCES[api_key] = source
    while len(_SHARED_SOURCES) > _MAX_SHARED_SOURCES:
        del _SHARED_SOURCES[next(iter(_SHARED_SOURCES))]
    return source


def _rows(body: Any) -> list[dict[str, Any]] | None:
    """`{data: [...]}` (the documented list shape) or a bare list."""
    if isinstance(body, dict):
        data = body.get("data")
        if isinstance(data, list):
            return [r for r in data if isinstance(r, dict)]
        return None
    if isinstance(body, list):
        return [r for r in body if isinstance(r, dict)]
    return None


def _retry_after(resp: Any) -> int | None:
    headers = getattr(resp, "headers", None) or {}
    try:
        value = headers.get("Retry-After")
    except AttributeError:
        return None
    try:
        return int(str(value)) if value is not None else None
    except ValueError:
        return None
