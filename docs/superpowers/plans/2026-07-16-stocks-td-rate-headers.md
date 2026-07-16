# Stocks: Twelve Data rate header live-correction — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Twelve Data throttle self-correct in real time by reading the `api-credits-left` header off every `/quote` response and syncing the token bucket to the server's actual remaining budget — so a **second sign sharing the same key** (or a mid-run downgrade) is respected without waiting for a 429.

**Architecture:** The `TwelveDataClient` reads `api-credits-left` after each `/quote` and invokes an optional `on_credits` callback. The shared `QuoteCache` wires that callback to `AsyncRateLimiter.observe_credits_left`, which clamps its token count DOWN to the server's number (never up — the boot `/api_usage` seed still owns capacity, and a 429 still ratchets the rate). Missing/unparseable header = "no new information," never a hard stop.

**Tech Stack:** Python 3.14, attrs, aiohttp, pytest + pytest-asyncio. `led-ticker-plugins` monorepo, `plugins/stocks/`.

## Global Constraints

- No `from __future__ import annotations` anywhere; PEP-758 parenless `except A, B:` is the project style (ruff format normalizes to it).
- Plugins import core symbols ONLY via `led_ticker.plugin` (this feature touches only `led_ticker_stocks.*` internals — fine).
- Secrets env-only (`TWELVEDATA_API_KEY`); no token in config. Token-leak regressions stay green.
- **The header only clamps tokens DOWN** (`min`) — it never raises the rate above the `/api_usage`-seeded capacity, and a 429 (via `note_rate_limited`, shipped in v0.6.0) still wins. Do not change the boot seed or the 429 path.
- **Missing header = no-op.** A missing or non-integer `api-credits-left` must NEVER be read as "0 credits left" (that would freeze the panel). Only act on a valid non-negative integer.
- Finnhub path unchanged (no headers, no callback).
- CI gate (plugins monorepo, per member): `uv run ruff check plugins/stocks` + `ruff format --check` (pin `ruff==0.15.18`) + `pyright plugins/stocks/src` (pin `pyright==1.1.410`) + pytest. Verify all four before committing (e.g. `uvx ruff@0.15.18 …`, `uv run --with pyright==1.1.410 …`).
- Commit messages end with exactly:
  Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_015czjSP4i45aZxX717Zh9yS

## File Structure

- `src/led_ticker_stocks/_ratelimit.py` — **modify**: add `observe_credits_left(n)`.
- `src/led_ticker_stocks/twelvedata.py` — **modify**: `TwelveDataClient` gains an optional `on_credits` callback; `fetch_quote` reads `api-credits-left` and invokes it.
- `src/led_ticker_stocks/providers.py` — **modify**: `Provider` Protocol + both providers gain `set_credit_observer(cb)` (TD forwards to its client; Finnhub no-op).
- `src/led_ticker_stocks/_cache.py` — **modify**: after building the limiter in `ensure_started`, wire `provider.set_credit_observer(self._limiter.observe_credits_left)`.
- Tests: `tests/test_ratelimit.py`, `tests/test_twelvedata.py`, `tests/test_providers.py`, `tests/test_cache.py`.

---

## Task 1: `AsyncRateLimiter.observe_credits_left`

**Files:**
- Modify: `src/led_ticker_stocks/_ratelimit.py`
- Test: `tests/test_ratelimit.py`

**Interfaces:**
- Produces: `AsyncRateLimiter.observe_credits_left(self, credits_left: int) -> None` — clamps the bucket's token count to `min(current_tokens, credits_left)` so we never assume more budget than the server reports remaining this window. Never raises tokens (capacity/rate stay owned by the boot seed + 429 path).

- [ ] **Step 1: Write the failing test** — append to `tests/test_ratelimit.py`:

```python
async def test_observe_credits_left_clamps_tokens_down():
    """The server's api-credits-left is truth for remaining budget: sync the
    bucket DOWN to it (a sibling sign burned some), never up."""
    rl, _clock, slept = _limiter(8)  # starts full: 8 tokens
    rl.observe_credits_left(3)  # server says only 3 left this window
    # 3 acquires are now free; the 4th must wait (bucket clamped to 3)
    for _ in range(3):
        await rl.acquire()
    assert slept == []
    await rl.acquire()
    assert len(slept) == 1


async def test_observe_credits_left_never_raises_tokens():
    """A higher server number does not inflate our bucket beyond what we hold
    (capacity is owned by the /api_usage seed, not the per-request header)."""
    rl, _clock, slept = _limiter(8)
    for _ in range(8):
        await rl.acquire()  # drain to 0
    rl.observe_credits_left(8)  # server claims 8 left — must NOT refill us
    await rl.acquire()
    assert slept  # still had to wait; observe didn't hand us free tokens
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --extra dev pytest tests/test_ratelimit.py -q -k observe`
Expected: FAIL — `AttributeError: 'AsyncRateLimiter' object has no attribute 'observe_credits_left'`.

- [ ] **Step 3: Implement** in `_ratelimit.py` (add after `note_rate_limited`):

```python
    def observe_credits_left(self, credits_left: int) -> None:
        """Sync the bucket to the server's real remaining budget for this
        window (the `api-credits-left` header). Clamps tokens DOWN only — a
        shared key means fewer credits than we assumed, so back off; we never
        raise tokens above what we hold (capacity is owned by the /api_usage
        seed). A time-based refill still recovers over the minute."""
        self._tokens = min(self._tokens, float(credits_left))
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run --extra dev pytest tests/test_ratelimit.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker_stocks/_ratelimit.py tests/test_ratelimit.py
git commit -m "feat(stocks): AsyncRateLimiter.observe_credits_left — clamp tokens to server budget"
```

---

## Task 2: `TwelveDataClient` reads the credits header

**Files:**
- Modify: `src/led_ticker_stocks/twelvedata.py`
- Test: `tests/test_twelvedata.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `TwelveDataClient(token, session, on_credits: Callable[[int], None] | None = None)`. After a successful `/quote`, if `on_credits` is set and the response carries a parseable non-negative integer `api-credits-left` header, calls `on_credits(that_int)`. A missing/blank/non-integer header is skipped silently.

**Note (test mock):** `_mock_session` builds `resp` as a bare `AsyncMock`, so `resp.headers.get(...)` returns a child Mock, not `None` — the header path can't be tested until the mock sets a real `resp.headers` dict. Add a `headers=None` param to `_mock_session` that sets `resp.headers = headers or {}` (a real dict), so `.get("api-credits-left")` returns a str or `None` as production sees.

- [ ] **Step 1: Extend `_mock_session`** in `tests/test_twelvedata.py` to accept `headers`:

```python
def _mock_session(json_body, status=200, capture=None, headers=None):
    ...
    resp.status = status
    resp.headers = headers or {}  # real dict: .get() returns str or None
    resp.json = mock.AsyncMock(return_value=json_body)
    ...
```

(Leave all existing call sites unchanged — the new param defaults to an empty dict, matching the "no header" production case.)

- [ ] **Step 2: Write the failing tests** — append to `tests/test_twelvedata.py`:

```python
async def test_fetch_quote_reports_credits_left_via_callback():
    seen = []
    session = _mock_session(_FOREX, headers={"api-credits-left": "6"})
    client = TwelveDataClient("tok", session=session, on_credits=seen.append)
    await client.fetch_quote("EUR/USD")
    assert seen == [6]  # parsed int from the header


async def test_fetch_quote_no_header_does_not_call_back():
    seen = []
    session = _mock_session(_FOREX)  # no api-credits-left header
    client = TwelveDataClient("tok", session=session, on_credits=seen.append)
    await client.fetch_quote("EUR/USD")
    assert seen == []  # missing header => no signal, never "0"


async def test_fetch_quote_bad_header_is_ignored():
    seen = []
    session = _mock_session(_FOREX, headers={"api-credits-left": "n/a"})
    client = TwelveDataClient("tok", session=session, on_credits=seen.append)
    await client.fetch_quote("EUR/USD")
    assert seen == []
```

(`_FOREX` is the existing forex payload fixture in this file.)

- [ ] **Step 3: Run to verify failure**

Run: `uv run --extra dev pytest tests/test_twelvedata.py -q -k credits`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'on_credits'`.

- [ ] **Step 4: Implement** in `twelvedata.py`.

Add the import (top of file, with the others):

```python
from collections.abc import Callable
```

Change `TwelveDataClient.__init__` and `fetch_quote`:

```python
class TwelveDataClient:
    def __init__(self, token, session, on_credits: Callable[[int], None] | None = None):
        self._token = token
        self._session = session
        self._on_credits = on_credits

    async def fetch_quote(self, sym):
        params = {"symbol": sym, "apikey": self._token}
        async with self._session.get(QUOTE_URL, params=params) as resp:
            if resp.status != 200:
                logging.warning("Twelve Data /quote failed: HTTP %s", resp.status)
                resp.raise_for_status()
            body = await resp.json()
            self._report_credits(resp.headers)
            return body

    def _report_credits(self, headers) -> None:
        """Feed `api-credits-left` (remaining in the current minute window) to
        the observer, if set. Missing/non-integer header => no signal (never 0)."""
        if self._on_credits is None:
            return
        raw = headers.get("api-credits-left")
        if raw is None:
            return
        try:
            left = int(raw)
        except (TypeError, ValueError):
            return
        if left >= 0:
            self._on_credits(left)
```

(`fetch_api_usage` is unchanged — no header handling there.)

- [ ] **Step 5: Run to verify pass**

Run: `uv run --extra dev pytest tests/test_twelvedata.py -q`
Expected: PASS (including the existing `/quote` + `/api_usage` tests).

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker_stocks/twelvedata.py tests/test_twelvedata.py
git commit -m "feat(stocks): TwelveDataClient surfaces api-credits-left via on_credits callback"
```

---

## Task 3: Wire the observer through the provider + cache

**Files:**
- Modify: `src/led_ticker_stocks/providers.py`
- Modify: `src/led_ticker_stocks/_cache.py`
- Test: `tests/test_providers.py`, `tests/test_cache.py`

**Interfaces:**
- Consumes: `AsyncRateLimiter.observe_credits_left` (Task 1); `TwelveDataClient(on_credits=…)` (Task 2).
- Produces: `Provider.set_credit_observer(self, cb: Callable[[int], None]) -> None` on the Protocol; `TwelveDataProvider` sets `self._client._on_credits = cb`; `FinnhubProvider` is a no-op. `QuoteCache.ensure_started` calls `self._provider.set_credit_observer(self._limiter.observe_credits_left)` right after building the limiter.

- [ ] **Step 1: Write the failing provider test** — append to `tests/test_providers.py`:

```python
def test_twelvedata_provider_set_credit_observer_wires_client():
    client = mock.Mock()
    prov = TwelveDataProvider(client)
    cb = lambda n: None
    prov.set_credit_observer(cb)
    assert client._on_credits is cb


def test_finnhub_provider_set_credit_observer_is_noop():
    prov = FinnhubProvider(mock.Mock())
    prov.set_credit_observer(lambda n: None)  # must not raise
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --extra dev pytest tests/test_providers.py -q -k credit_observer`
Expected: FAIL — `AttributeError: … has no attribute 'set_credit_observer'`.

- [ ] **Step 3: Implement in `providers.py`.**

Add to the `Provider` Protocol (after `fetch_plan_limit`):

```python
    def set_credit_observer(self, cb: "Callable[[int], None]") -> None:
        """Register a callback fed the per-request remaining-budget signal
        (Twelve Data's api-credits-left). No-op for providers without it."""
        ...
```

Add the import at the top of `providers.py`:

```python
from collections.abc import Callable
```

`FinnhubProvider` (add a method):

```python
    def set_credit_observer(self, cb: Callable[[int], None]) -> None:
        return  # Finnhub has no per-request credit header
```

`TwelveDataProvider` (add a method):

```python
    def set_credit_observer(self, cb: Callable[[int], None]) -> None:
        self._client._on_credits = cb
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run --extra dev pytest tests/test_providers.py -q`
Expected: PASS.

- [ ] **Step 5: Wire it in `_cache.py`.**

In `ensure_started`, right after the limiter is built (the `self._limiter = AsyncRateLimiter(rpm)` line inside the `if self._provider is not None:` block), add:

```python
            self._limiter = AsyncRateLimiter(rpm)
            # Live-correct the pace from each response's api-credits-left so a
            # second sign sharing this key (or a mid-run downgrade) is respected
            # without waiting for a 429.
            self._provider.set_credit_observer(self._limiter.observe_credits_left)
```

- [ ] **Step 6: Write the cache integration test** — append to `tests/test_cache.py`:

```python
async def test_ensure_started_wires_credit_observer(monkeypatch):
    """The limiter's observe_credits_left is registered on the provider so live
    header signals reach it."""
    import led_ticker_stocks.providers as providers_mod
    from led_ticker_stocks._cache import get_cache

    monkeypatch.setenv("TWELVEDATA_API_KEY", "tdkey")
    observers = []

    def _capture(self, cb):
        observers.append(cb)

    async def _detect(self):
        return 8

    monkeypatch.setattr(providers_mod.TwelveDataProvider, "fetch_plan_limit", _detect)
    monkeypatch.setattr(
        providers_mod.TwelveDataProvider, "set_credit_observer", _capture
    )
    cache = get_cache()
    cache.register(["EUR/USD"])

    async def _noop_update():
        pass

    monkeypatch.setattr(cache, "update", _noop_update)
    await cache.ensure_started(session=object(), provider="twelvedata")
    assert observers and observers[0] == cache._limiter.observe_credits_left
```

- [ ] **Step 7: Run the full suite + all CI gates**

Run:
```bash
uv run --extra dev pytest tests/ -q
uvx ruff@0.15.18 check src/ tests/ && uvx ruff@0.15.18 format --check src/ tests/
uv run --with pyright==1.1.410 pyright src/
```
Expected: all pass; ruff + pyright clean. (Run from `plugins/stocks/` for pytest/pyright; `uvx ruff` paths are `plugins/stocks` from repo root — adjust as in the CI workflow.)

- [ ] **Step 8: Commit**

```bash
git add src/led_ticker_stocks/providers.py src/led_ticker_stocks/_cache.py tests/test_providers.py tests/test_cache.py
git commit -m "feat(stocks): wire api-credits-left live-correction into the shared limiter"
```

---

## Post-implementation

- **Live-verify** (optional, uses a real key): boot the multiasset config headless and confirm no errors and, on a shared key, the pace backing off. The unit tests cover the logic; a live run confirms the header name/casing (`api-credits-left`) matches the real response (verified this session against the live API).
- **Docs:** the config `RATE LIMITS` header note already says the rate auto-detects + a 429 ratchets down; add one clause that it also live-corrects from response headers (shared-key aware). The docs-site update rides the separate docs shore-up plan.
- **Release:** fold into the next `stocks-v0.6.1` (patch) once merged — no config surface change.

## Self-Review

**Spec coverage:** header read (Task 2) ✓; bucket sync clamped-down (Task 1) ✓; wiring through provider + cache (Task 3) ✓; missing-header = no-op (Task 2 + constraint) ✓; 429/boot-seed untouched (constraint) ✓; Finnhub no-op (Task 3) ✓.

**Placeholder scan:** every step carries full code; the test mock gap (`resp.headers`) is called out with the exact fix.

**Type consistency:** `on_credits: Callable[[int], None] | None`, `set_credit_observer(cb: Callable[[int], None])`, and `observe_credits_left(credits_left: int)` are consistent across client, provider, Protocol, and limiter. `Callable` imported in both `twelvedata.py` and `providers.py`.
