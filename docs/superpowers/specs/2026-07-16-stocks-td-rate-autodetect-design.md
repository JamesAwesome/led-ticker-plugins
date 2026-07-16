# Stocks plugin: Twelve Data self-tuning rate limit — Design (staged MVP)

**Date:** 2026-07-16
**Plugin:** `led-ticker-stocks`
**Branch:** `stocks-td-rate-autodetect` (stacked on `stocks-twelvedata-provider` / PR #51 until it merges)
**Status:** approved shape (brainstorm + PM review). This spec = the **staged MVP**; the header live-correction is a documented fast-follow.

## Problem

The Twelve Data throttle (shipped in #51) is hard-coded to the free-tier **8 requests/minute** (`TwelveDataProvider.REQUESTS_PER_MINUTE = 8`). A **paid** key (55 / 300 / 600+ req/min) is silently throttled to free-tier speed — wasted throughput, slow first paint on large watchlists. Asking the user to type their rate into config is a bad experience: *a user who just wants fresher data doesn't know their tier's req/min.*

## Product frame (PM)

Set-and-forget appliance; "restart applies changes"; no tuning dashboard. **The one felt outcome:** *"I put in my paid key and the board fills fast and stays fresh, forever, without touching a config file."* The user never sees a rate limiter. Optimize for never-think-about-this-again.

## What Twelve Data exposes (verified live)

- `GET /api_usage?apikey=…` → `{"current_usage", "plan_limit", "daily_usage", "plan_daily_limit", "plan_category"}`. **`plan_limit` is the per-minute cap** (8 on "basic"/free); `plan_category` is the tier name.
- Every `/quote` response carries headers: `api-credits-left` (remaining in the current minute window), `api-credits-used`, `api-credits-request`. *(Used by the fast-follow, not this MVP.)*

## Decision: B3 (hybrid), staged

Boot `/api_usage` sizes the starting pace; response headers correct it live. **This MVP builds the boot-seed + the 429 safety net; the header live-correction is a fast-follow** (its main added value — shared-key awareness across two signs — is real but rarer, and the boot seed already fixes the paid-key-throttled-slow case + cold-start burst).

### MVP scope (this spec)

1. **Boot seed.** On live-TD `ensure_started`, before spawning the poll loop, make one `/api_usage` call. Read `plan_limit` → build the rate limiter with that rpm. Read `plan_category` for the log line. This runs BEFORE the eager fetch so even the first cycle is paced correctly (a paid user never crawls at 8/min for even one minute).
2. **Fallback.** ANY failure of the `/api_usage` call — non-200, timeout, malformed body, missing/zero `plan_limit` — is swallowed + logged, and the limiter falls back to the safe **8/min**. The detection call must never block or crash boot (wrap like the existing eager-update tolerance).
3. **429 is law.** On a 429 from a quote fetch, multiplicatively decrease the limiter's effective rate (halve, floor 1/min) for the rest of the session, and drain its tokens (pause until refill). The detected number is only a starting point; a 429 ratchets it down and does not auto-recover this session (a restart re-detects). This is the safety net for a stale / shared / downgraded plan.
4. **Surface the tier.** One INFO log line at boot: `stocks: Twelve Data plan 'basic' — 8 req/min` (or the detected paid tier). Matches the plugin's existing monitor-log convention; gives a troubleshooting tinkerer one place to confirm detection.
5. **Buried override (keep A as escape hatch).** OPTIONAL: honor an explicit `requests_per_minute` on the source/widget if set — it wins over auto-detection (for the 1% who want to hand-cap, e.g. to protect the daily budget). Default unset → auto-detect. *(Include only if cheap; otherwise defer — the auto path is the product.)*

### Deferred — fast-follow (own PR)

- **Header live-correction (B2 half):** read `api-credits-left` off each `/quote` response and sync the token bucket to the server's real remaining budget — catches a **sibling sign sharing the same key** and a mid-run downgrade without waiting for a 429. Requires threading response headers from `TwelveDataClient` back into the limiter (`limiter.observe_credits_left(n)`); missing header = "no new info," never "zero."

### Deferred — YAGNI (not building)

Periodic `/api_usage` re-poll timer; per-symbol prioritization under tight budget; multi-key / per-widget keys; config UI/dashboard; telemetry pipeline. Plan **upgrade** takes effect on next restart (document, don't special-case).

## Implementation shape

- `AsyncRateLimiter` gains a way to lower its rate at runtime (429 path): e.g. `note_rate_limited()` → halves `_capacity`/interval (floor 1) and zeroes tokens. Keep the token-bucket core from #51.
- `providers.py`: `TwelveDataProvider` grows an `async fetch_plan_limit() -> int | None` (calls a new `TwelveDataClient.fetch_api_usage()`, returns `plan_limit`, None on any failure) + a `plan_category`/log detail. `FinnhubProvider` returns None (no auto-detect; keeps its 60 default). Add `fetch_plan_limit` to the `Provider` Protocol (returns `None` by default meaning "no detection, use REQUESTS_PER_MINUTE").
- `_cache.ensure_started`: after building the provider, `detected = await provider.fetch_plan_limit()` (tolerant); `rpm = detected or provider.REQUESTS_PER_MINUTE`; `self._limiter = AsyncRateLimiter(rpm)`; log the tier. Then the existing lock-held eager fetch.
- 429 wiring: `_fetch_one` / the poll loop catches the fetch exception; detect a 429 specifically (aiohttp `ClientResponseError.status == 429`) → `self._limiter.note_rate_limited()`.

## Testing

- `TwelveDataClient.fetch_api_usage`: parses `plan_limit` from a mocked `/api_usage`; returns None on non-200 / malformed / missing field.
- `ensure_started` builds the limiter at the detected rpm (mock provider `fetch_plan_limit` → 300 → `_limiter` sized 300); falls back to 8 when detection returns None.
- 429 handling: a `note_rate_limited()` halves the rate + drains tokens; a fetch raising a 429 triggers it (integration).
- `AsyncRateLimiter.note_rate_limited`: rate halves, floor 1, tokens drained (unit).
- Finnhub path unchanged (no `/api_usage` call; 60/min default). Existing 197 tests stay green.
- CI gate (plugins monorepo): `ruff check` + `ruff format --check` (0.15.18) + `pyright` (1.1.410) + pytest.

## Non-goals / safety recap

- Detected-but-wrong is worse than uniformly slow → the 429-is-law rule + the tier log line are the mitigations, and both are in the MVP.
- Secrets stay env-only (`TWELVEDATA_API_KEY`); `/api_usage` uses the same env token.
- Single shared limiter in the `QuoteCache` (not per-widget) — already the case.
