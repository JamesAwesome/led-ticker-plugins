"""LiveTennisSource — the Live Tennis API fetcher, with the free-tier
cadence ENFORCED here rather than trusted to config.

The free tier is 100 requests/day. One request every 15 minutes is 96/day,
so `MIN_UPDATE_INTERVAL = 900` is a hard floor: a smaller `update_interval`
is clamped (and logged) and, independently, `poll()` refuses to issue a
request before the previous one's interval has elapsed — however often the
engine (or a test) calls it. One tick == at most one request, except for
the very first tick after boot, which may spend a second request on the
upcoming listing when nothing is live (so the sign shows fixtures within
one tick instead of two).

Which listing a tick fetches: `status=live` whenever the last live payload
had matches; otherwise live/upcoming alternate, so a quiet sign still
notices new play within two ticks while its fixtures stay fresh.

Failure policy (never raises — `poll()` is called from the widget's
`update()`, which must never break the render loop): a 429 / 5xx /
timeout / network error keeps the last good payload, marks the snapshot
`stale`, and backs off exponentially (2x the interval, doubling, capped at
`MAX_BACKOFF`; a 429's `Retry-After` is honoured when larger). A rejected
key (401/403) parks the source for an hour and flags `key_rejected` so the
widget can say so on the panel instead of retrying into a wall.
"""

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
REQUEST_TIMEOUT = 20  # seconds, whole request
LIVE_LIMIT = 200  # API maximum per page
UPCOMING_LIMIT = 100
_USER_AGENT = "led-ticker-tennis (+https://github.com/JamesAwesome/led-ticker-plugins)"


def resolve_api_key(configured: str | None) -> str:
    """The key from config (`api_key = "..."`) or the `LIVETENNIS_API_KEY`
    environment variable, whichever is set (config wins); "" when neither."""
    key = (configured or "").strip()
    if key:
        return key
    return (os.environ.get(ENV_KEY) or "").strip()


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

    # --- scheduling ---------------------------------------------------

    def _next_kind(self) -> str:
        if self.snapshot.live:
            return "live"
        return "upcoming" if self._last_kind == "live" else "live"

    def seconds_until_allowed(self) -> float:
        return max(0.0, self._next_allowed - self._clock())

    async def poll(self) -> Snapshot:
        """Fetch if the cadence allows; return the (possibly unchanged)
        snapshot. Never raises."""
        now = self._clock()
        if now < self._next_allowed:
            logger.debug(
                "tennis: poll skipped, %.0fs until next allowed request",
                self._next_allowed - now,
            )
            return self.snapshot

        kind = self._next_kind()
        ok = await self._fetch(kind)
        if (
            ok
            and kind == "live"
            and not self.snapshot.live
            and self.snapshot.upcoming_fetched_at is None
        ):
            # Boot (or first quiet tick): nothing live and no fixtures cached
            # yet -> spend one more request now so the panel has something
            # to show. Bounded: only until the first upcoming fetch succeeds.
            # Counts as the "upcoming" turn of the alternation, so the next
            # quiet tick polls live again.
            ok = await self._fetch("upcoming")
            kind = "upcoming"

        if ok:
            # Only a SUCCESSFUL fetch advances the alternation: a failed
            # live fetch is retried as live once the backoff clears.
            self._last_kind = kind
            self._backoff = 0
            self._next_allowed = self._clock() + self.interval
        return self.snapshot

    # --- fetching -----------------------------------------------------

    def _url(self, kind: str) -> str:
        limit = LIVE_LIMIT if kind == "live" else UPCOMING_LIMIT
        return f"{self.base_url}/matches?status={kind}&limit={limit}"

    def _fail(self, message: str, *, retry_after: int | None = None) -> None:
        snap = self.snapshot
        snap.stale = True
        snap.last_error = message
        step = self._backoff * 2 if self._backoff else self.interval * 2
        wait = max(self.interval, step, retry_after or 0)
        self._backoff = min(MAX_BACKOFF, wait)
        self._next_allowed = self._clock() + self._backoff
        logger.warning("tennis: %s; next request in %ds", message, self._backoff)

    async def _fetch(self, kind: str) -> bool:
        snap = self.snapshot
        snap.requests_made += 1
        headers = {
            "X-API-Key": self.api_key,
            "Accept": "application/json",
            "User-Agent": _USER_AGENT,
        }
        url = self._url(kind)
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

        rows = _rows(body)
        if rows is None:
            self._fail("malformed response (no `data` list)")
            return False

        now = self._clock()
        if kind == "live":
            snap.live = rows
            snap.live_fetched_at = now
        else:
            snap.upcoming = rows
            snap.upcoming_fetched_at = now
        snap.stale = False
        snap.last_error = None
        snap.key_rejected = False
        logger.info("tennis: fetched %d %s match(es)", len(rows), kind)
        return True


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
