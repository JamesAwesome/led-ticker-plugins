"""Async token-bucket rate limiter for provider requests.

Twelve Data's free tier caps requests per MINUTE (≈8), not just per day. A
boot burst (multiple consumers priming a shared cache) or a symbol list longer
than the per-minute cap trips a 429 even when the daily budget is fine. This
limiter smooths that: `acquire()` returns instantly while burst tokens remain
(so a small symbol set still paints fast) and otherwise sleeps until the next
token refills, capping sustained volume at `rpm`/minute.

`clock`/`sleep` are injectable so the token accounting is unit-testable without
real waiting.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable


class AsyncRateLimiter:
    def __init__(
        self,
        rpm: int,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        # Seconds per token; 0/None rpm => unlimited (acquire is a no-op).
        self._interval: float = 60.0 / rpm if rpm and rpm > 0 else 0.0
        self._capacity: float = float(rpm) if rpm and rpm > 0 else 0.0
        self._tokens: float = self._capacity
        self._clock = clock
        self._sleep = sleep
        self._last: float = clock()

    async def acquire(self) -> None:
        """Consume one token, sleeping until one is available if the bucket is dry."""
        if self._interval <= 0:
            return
        now = self._clock()
        self._tokens = min(
            self._capacity, self._tokens + (now - self._last) / self._interval
        )
        self._last = now
        if self._tokens < 1.0:
            wait = (1.0 - self._tokens) * self._interval
            await self._sleep(wait)
            self._tokens = 1.0
            self._last = self._clock()
        self._tokens -= 1.0
