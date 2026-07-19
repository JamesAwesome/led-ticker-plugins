# flair.poker background geometry warm — design

**Date:** 2026-07-19
**Status:** approved (brainstorm with James)
**Branch:** `flair-poker-perf` (continues PR #71)

## Problem

After PR #71's fixes (process-wide geometry cache, incremental reveal, direct
geometry painting), every poker firing runs at uniform ~1ms frames — except
the **first-ever firing in a process**, which still pays the suit-geometry
rasterization synchronously inside `_ensure_plan` (~0.77s dev, ~2–3s Pi).
On the sign this reads as "the first poker transition takes a while" — not
broken, but confusing.

## Decision

**Approach A — background warm at construction** (argued against B: baked
package-data geometry; B rejected because it converts flair into a plugin
with a build artifact — generator script, committed blob, permanent CI drift
test re-run on every suit-shape tweak — to buy determinism the boot window
already provides. C — numpy-vectorized masks — rejected for the dep + a
duplicate mask implementation needing parity policing).

Key facts the design exploits:

- Transition instances are constructed at **config load / boot**
  (`core app/run.py` → `_build_trans_obj`), many seconds before the first
  firing (there is no entry transition into the first boot section, so the
  earliest firing is after the first section's full hold + scroll).
- The warm needs **nothing from the canvas**: suits are known in
  `__init__`, and the radius bound is a constant —
  `_MAX_RI = ceil(max_radius(GRID, GRID))` (= 66), independent of panel
  dims. Interiors are bounded by `ceil(GLYPH_R)` (= 7).

## Mechanism (all in `plugins/flair/src/led_ticker_flair/flair/poker.py`)

1. **`_MAX_RI` module constant** — `int(math.ceil(max_radius(GRID, GRID)))`,
   used by BOTH the warm worker and `_ensure_plan`'s existing sync fallback
   (extracted so the two can't drift).

2. **`_warm_worker(suits, yield_s=0.005)`** — module-level, synchronous.
   Per suit: warm interiors `0..ceil(GLYPH_R)` first (glyph bodies render
   earliest), then rings `0.._MAX_RI` ascending (pulse consumption order),
   calling `_interior_geom` / `_ring_geom` **directly** — NOT
   `_warm_suit_geometry` — so cache granularity stays per-radius and a
   concurrent sync fallback only pays the un-warmed remainder.
   `time.sleep(yield_s)` between radii (skipped when `yield_s == 0`) keeps
   GIL impact on the render loop invisible (~268 radii ≈ 1.3s of yield
   spread across the warm). Whole body in `try/except Exception` with a
   `logging.debug` — a warm failure must never crash the app; the sync
   fallback still guarantees correctness.

3. **`_start_background_warm(suits)`** — module `threading.Lock` +
   `_warm_dispatched: set[str]`: each suit dispatched **once per process**
   regardless of how many Poker sections the config declares. New suits
   spawn one `daemon=True` thread per batch running `_warm_worker`;
   threads appended to a module `_warm_threads` list so tests can join.

4. **`Poker.__init__`** calls `_start_background_warm(self.suits)` as its
   last statement. Construction must not block (thread start only).

5. **`_ensure_plan` unchanged** — synchronous `_warm_suit_geometry` remains
   the fallback. If a firing beats the thread (unrealistic: warm starts at
   boot), worst case is a shortened version of today's stall, once.
   `functools.cache` on the per-radius functions makes concurrent
   duplicate computation benign (both compute, one wins, no corruption).

## Test strategy

**Race hazard:** a live warm thread during tests would pollute the mask-spy
tests (`TestNoPerFiringRasterization` monkeypatches `_MASKS`; background
calls mid-test would land in the spy counts).

**Fix — no thread ever runs in tests:** a **session-scoped autouse fixture**
in flair's test conftest calls `_warm_worker(SUITS, yield_s=0)` synchronously
at session start: process fully warmed, `_warm_dispatched` saturated, every
subsequent `_start_background_warm` a no-op. The existing spy tests already
tolerate a pre-warmed process (their comments say "calls may be EMPTY").

Unit tests (new class in `test_flair_poker_transition.py`):

- **Dedupe:** after one `Poker(suits=[...])`, a second construction with the
  same suits appends no new thread to `_warm_threads` (fixture-saturated
  process makes this deterministic).
- **Daemon + non-blocking:** monkeypatch `threading.Thread` with a spy on a
  temporarily-cleared `_warm_dispatched` (restored after) and assert
  `daemon=True`, `start()` called, target covers exactly the new suits.
- **Worker warms:** with mask spies installed, a direct
  `_warm_worker(["hearts"], yield_s=0)` followed by a fresh
  `Poker(suits=["hearts"])` firing does **zero** rasterization (existing
  spy idiom).

Existing suites (482) must stay green; ruff + format clean.

## Non-goals

- No user-facing knob, no docs-site change (perf internal). PR #71's
  "first-ever firing" honest-note paragraph gets updated instead.
- No baked geometry, no numpy (escalation paths if the thread ever proves
  visible on hardware).
- No change to render output — byte-identical frames.
