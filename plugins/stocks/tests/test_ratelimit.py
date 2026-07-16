import pytest

from led_ticker_stocks._ratelimit import AsyncRateLimiter


class _FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def _limiter(rpm):
    clock = _FakeClock()
    slept = []

    async def sleep(s):
        slept.append(s)
        clock.t += s  # a real await would let wall-clock advance; mirror it

    return AsyncRateLimiter(rpm, clock=clock, sleep=sleep), clock, slept


async def test_burst_up_to_capacity_never_sleeps():
    """A symbol set within the per-minute cap paints fast: the first `rpm`
    acquires are instant (burst tokens)."""
    rl, _clock, slept = _limiter(8)
    for _ in range(8):
        await rl.acquire()
    assert slept == []


async def test_over_capacity_throttles():
    """The (rpm+1)-th acquire in a burst waits one refill interval (60/rpm)."""
    rl, _clock, slept = _limiter(8)  # 7.5s per token
    for _ in range(8):
        await rl.acquire()
    await rl.acquire()
    assert len(slept) == 1
    assert slept[0] == pytest.approx(7.5, abs=1e-6)


async def test_refill_over_time_is_instant():
    """After draining, a token that has refilled with elapsed time is free."""
    rl, clock, slept = _limiter(8)
    for _ in range(8):
        await rl.acquire()
    clock.t += 7.5  # one token refills
    await rl.acquire()
    assert slept == []  # no wait — the refilled token covered it


async def test_zero_rpm_is_unlimited_noop():
    """rpm<=0 disables throttling entirely (never sleeps)."""

    async def _boom(_s):
        raise AssertionError("unlimited limiter must not sleep")

    rl = AsyncRateLimiter(0, clock=_FakeClock(), sleep=_boom)
    for _ in range(100):
        await rl.acquire()


async def test_note_rate_limited_halves_the_rate_and_drains():
    """A 429 ratchets the sustained rate down: 8/min -> 4/min, so an empty
    bucket now waits 15 s (60/4) for a token instead of 7.5 s."""
    rl, _clock, slept = _limiter(8)
    for _ in range(8):
        await rl.acquire()  # drain the burst
    rl.note_rate_limited()  # -> 4/min, tokens 0
    await rl.acquire()
    assert slept[-1] == pytest.approx(15.0, abs=1e-6)


async def test_note_rate_limited_floors_at_one_per_minute():
    """Repeated 429s can't drive the rate below 1/min (a 60 s wait)."""
    rl, _clock, slept = _limiter(2)
    for _ in range(10):
        rl.note_rate_limited()
    await rl.acquire()
    assert slept[-1] == pytest.approx(60.0, abs=1e-6)
