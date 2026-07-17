# Stocks state-dimming redesign — Design

**Date:** 2026-07-17
**Package:** `plugins/stocks` (led-ticker-stocks)
**Branch / PR:** `stocks-state-dimming` / plugins PR #58 (amends the branch in place)
**Status:** approved (from-scratch brainstorm after #58 was built conversation-to-code)

## Why a redesign

PR #58 was built on the fly (no spec) to answer "why are some cards dimmer than
others on longboi" — the answer being per-symbol market-state dimming, with Twelve
Data's binary `is_market_open` producing a harsh 100%→45% cliff at 4pm. The
on-the-fly fix refined TD's CLOSED via a US/Eastern wall clock **inside
`parse_quote`**, which an antagonistic review then flagged three findings against —
all three caused by that one decision:

1. US market **holidays** mislabel evenings as PRE/AH (the clock only models the
   regular-session window).
2. A **clock failure** (missing tzdata) originally aborted whole poll cycles.
3. **Foreign non-pair listings** get US-Eastern session windows stamped on them.

The from-scratch brainstorm re-opened the foundational question — *what should a
closed market look like on the sign?* — and the answer chosen ("gently dimmer, no
time logic") deletes the entire class of findings rather than patching them.

## Decisions (user-approved 2026-07-16)

1. **Closed look = gently dimmer, no time logic.** No wall clock in the quote
   path; TD state stays the truthful binary its API reports.
2. **Scope = both providers.** The softened CLOSED dim is a change to the shared
   `STATE_META`, so Finnhub's overnight look softens identically. One truth.
3. **Keep the `dim_by_state` opt-out knob** exactly as #58 built it (it survived
   the hostile review with zero findings).

## Principle

**Market state is data; dim is presentation.** State comes only from what a
provider actually reports (Finnhub's status endpoint with its real PRE/AH
sessions; TD's binary `is_market_open`). Fabricating a richer state from a wall
clock to drive a presentation effect puts presentation logic in the data layer —
that was #58's mistake. Dimming is a per-state constant plus one opt-out knob,
applied at draw time.

The one pre-existing clock call site stays: `StocksTicker.update()`'s Finnhub
status-fetch **failure fallback** (`state_now_from_clock()` when the status
endpoint is unreachable). That is a data-availability fallback, correctly placed,
and out of scope here.

## Changes

### 1. Revert the TD clock refinement (`twelvedata.py`)

`parse_quote` returns to:

```python
state = MarketState.OPEN if payload.get("is_market_open") else MarketState.CLOSED
```

Deleted: the `state_now_from_clock()` call, its try/except degradation, the
`"/" not in sym` US-equity heuristic, and the KNOWN APPROXIMATIONS comment block.
TD symbols therefore only ever render OPEN (1.0) or CLOSED (0.70 after change 2).

Also deleted, because they document removed behavior:

- `TestClosedEquityClockRefinement` (6 tests) in `tests/test_twelvedata.py`.
- The README holiday/foreign-listing caveats attached to the `dim_by_state` row
  (the row itself stays — see change 3).

`state.py`'s `state_now_from_clock` / `state_from_clock` are untouched (Finnhub
fallback consumer remains).

### 2. Soften shared CLOSED dim: `0.45 → 0.70` (`state.py`)

```python
MarketState.CLOSED: StateMeta(0.70, "CLSD", (255, 60, 60), False),
```

- Preserves the monotone ordering OPEN 1.0 > PRE/AH 0.85 > CLOSED 0.70.
- TD's worst cliff becomes 100→70 at 4pm; Finnhub overnight softens identically.
- Chip label/color/pulse unchanged — CLSD still carries the state unambiguously.
- A comment on the entry records why 0.70: readable at storefront distance in a
  mixed-state multi-asset rotation; 0.45 read as a broken panel next to LIVE
  cards. Value is tunable on hardware later; 0.70 is the design value.

### 3. Keep `dim_by_state` as built (no changes)

Widget-level `dim_by_state: bool = True` on `StocksTicker` → `_StockStory` →
all three layouts (`card`/`crawl`/`dashboard`), each computing
`dim = STATE_META[state].dim if dim_by_state else 1.0`. The #58 wiring test
(`test_ticker.py`) and luminance test (`test_card.py`) stay.

### 4. Collateral

- **Tests:** any test asserting the 0.45 CLOSED dim updates to 0.70. The
  `test_card.py` luminance test's expected values re-derive from 0.70.
- **Smoke configs** (`config.stocks-multiasset.{bigsign,longboi}.toml`): the
  "2b BRIGHTNESS FOLLOWS STATE" WHAT-TO-LOOK-FOR item rewrites to the new
  reality — TD symbols: LIVE 100% vs CLSD 70%, no PRE/AH claims; Finnhub keeps
  its real PRE/AH at 85%.
- **README:** `dim_by_state` row stays, caveat-free; the CLOSED percentage
  anywhere it's mentioned becomes 70%.

## Out of scope

- Configurable dim values (per-state floats in TOML) — YAGNI; the bool knob plus
  a better default covers the observed need.
- Any TD PRE/AH support — would require a data source that actually reports
  sessions, not a clock.
- Finnhub status-fallback behavior (`state_now_from_clock` in `update()`).

## Testing

- Existing suite (230 tests at #58 head) minus the 6 deleted clock-refinement
  tests, with dim-value assertions updated.
- One new/adjusted test pinning the truthful binary: TD `is_market_open: false`
  → `MarketState.CLOSED` regardless of wall-clock time (freeze/monkeypatch not
  required once the clock call is gone — the test simply asserts CLOSED at any
  runtime).
- `STATE_META` ordering tripwire: assert
  `OPEN.dim > PRE.dim == AFTER.dim > CLOSED.dim` so a future tweak can't
  silently invert the brightness semantics.

## Rollout

Amend `stocks-state-dimming` (PR #58) — branch already merged with current main.
After merge: release **stocks-v0.7.0** via `scripts/cut_release.py stocks minor`
(first dogfood of the release-order guard).
