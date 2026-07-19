# flair.poker Background Geometry Warm Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate the first-ever poker firing's synchronous geometry-rasterization stall (~0.77s dev / ~2–3s Pi) by warming suit geometry in a background daemon thread at Poker construction (boot time).

**Architecture:** All warm inputs are process constants (suits known in `__init__`; radius bound derived from `GRID`, panel-independent). `Poker.__init__` dispatches each suit once per process to a daemon thread that fills the `functools.cache`'d `_ring_geom`/`_interior_geom` caches with small sleeps between radii. The existing synchronous warm in `_ensure_plan` stays as the fallback. Tests never see a live thread: a session-scoped conftest fixture pre-warms the whole process synchronously and saturates the dispatch set.

**Tech Stack:** Python 3.12+ (plugins monorepo), `threading`, `functools.cache`, pytest. Repo: `led-ticker-plugins`, working checkout `/Users/james/projects/github/jamesawesome/led-ticker-plugins-flight`, branch `flair-poker-perf` (rides PR #71).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-19-flair-poker-background-warm-design.md`.
- Work ONLY on branch `flair-poker-perf` — run `git branch --show-current` first; abort if it prints anything else.
- No new runtime dependencies (flair depends only on `led-ticker-core>=4.18`).
- No `from __future__ import annotations` (PEP 649 project rule).
- Render output must be byte-identical — this change may not alter any painted pixel.
- Warm thread must be `daemon=True`, must never raise out of its body, and `Poker.__init__` must not block on it.
- The warm worker calls `_interior_geom` / `_ring_geom` directly (per-radius cache granularity) — NOT `_warm_suit_geometry`.
- `_ensure_plan`'s synchronous `_warm_suit_geometry` fallback stays.
- No live warm thread may run during tests (session fixture pre-warms + saturates dispatch).
- Lint gate before push: `uv run --extra dev ruff check src/ tests/` and `uv run --extra dev ruff format --check src/ tests/` from `plugins/flair/`.

All `pytest`/`ruff` commands below run from `/Users/james/projects/github/jamesawesome/led-ticker-plugins-flight/plugins/flair/`.

---

### Task 1: `_warm_worker` + radius constants + session pre-warm fixture

**Files:**
- Modify: `plugins/flair/src/led_ticker_flair/flair/poker.py` (imports at lines 8–15; geometry-cache section around lines 155–178; `_ensure_plan` warm block around lines 283–288)
- Modify: `plugins/flair/tests/conftest.py`
- Test: `plugins/flair/tests/test_flair_poker_transition.py`

**Interfaces:**
- Consumes: existing `_interior_geom(suit, r)`, `_ring_geom(suit, r_int)`, `max_radius(cell_w, cell_h)`, `GRID`, `GLYPH_R`, `SUITS` in `poker.py`.
- Produces: `_MAX_RI: int` and `_GLYPH_RI: int` module constants; `_warm_worker(suits: list[str], yield_s: float = 0.005) -> None` — Task 2's thread target and the conftest fixture's pre-warm entry point.

- [ ] **Step 1: Write the failing test**

Append to `plugins/flair/tests/test_flair_poker_transition.py` (uses the existing `_StubCanvas`, `_make_widget`, and the `_mask_spy` idiom from `TestNoPerFiringRasterization` in the same file):

```python
class TestWarmWorker:
    """First-firing warm stall (2026-07-19): geometry warming moves off the
    render path into a background thread started at construction. The worker
    must cover EVERY radius a firing can request — a gap would surface as
    lazy rasterization mid-transition on the Pi."""

    def test_worker_covers_every_radius_a_firing_needs(self, monkeypatch) -> None:
        import led_ticker_flair.flair.poker as m

        try:
            # Cold-start the process for one suit, warm it via the worker
            # ONLY, then spy the masks: any rasterization during a full
            # firing afterwards is a coverage gap in the worker.
            m._ring_geom.cache_clear()
            m._interior_geom.cache_clear()
            m._warm_suit_geometry.cache_clear()
            m._warm_worker(["diamonds"], yield_s=0)

            calls = TestNoPerFiringRasterization._mask_spy(monkeypatch)
            canvas = _StubCanvas(width=256, height=64)
            o = _make_widget(draw_pixel=False)
            i = _make_widget(draw_pixel=False)
            p = Poker(suits=["diamonds"], seed=5)
            t = 0.02
            while t < 1.0:
                p.frame_at(round(t, 3), canvas, o, i)
                t += 0.02
            assert not calls, (
                f"firing rasterized {len(calls)} mask points after a full "
                "worker warm — _warm_worker's radius range has a gap"
            )
        finally:
            # Restore the fully-warmed-process invariant for later tests.
            m._warm_worker(list(m.SUITS), yield_s=0)

    def test_worker_swallows_exceptions(self, monkeypatch) -> None:
        import led_ticker_flair.flair.poker as m

        def _boom(suit, r_int):
            raise RuntimeError("rasterizer exploded")

        monkeypatch.setattr(m, "_ring_geom", _boom)
        m._warm_worker(["hearts"], yield_s=0)  # must not raise
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --extra dev pytest tests/test_flair_poker_transition.py -q -k WarmWorker`
Expected: 2 FAILED / ERROR with `AttributeError: module 'led_ticker_flair.flair.poker' has no attribute '_warm_worker'`

- [ ] **Step 3: Implement `_warm_worker` + constants**

In `plugins/flair/src/led_ticker_flair/flair/poker.py`, add to the stdlib imports (keep alphabetical):

```python
import colorsys
import functools
import logging
import math
import random
import threading
import time
```

In the process-wide geometry-cache section, immediately BEFORE the `@functools.cache` / `def _warm_suit_geometry(...)` block, add:

```python
# Radius bounds are process CONSTANTS (panel-independent): _max_r is always
# max_radius(GRID, GRID), so the warm needs nothing from the canvas.
_MAX_RI = int(math.ceil(max_radius(GRID, GRID)))
_GLYPH_RI = int(math.ceil(GLYPH_R))


def _warm_worker(suits: list[str], yield_s: float = 0.005) -> None:
    """Synchronously warm the process-wide geometry caches for ``suits``.

    Runs as the body of the background warm thread (see
    _start_background_warm) and, with ``yield_s=0``, as the test suite's
    session pre-warm. Interiors first (glyph bodies render earliest), then
    rings ascending (pulse consumption order). Calls the per-radius cache
    functions DIRECTLY — not _warm_suit_geometry — so a concurrent sync
    fallback in _ensure_plan only pays whatever radii remain uncached.
    ``yield_s`` sleeps between radii keep GIL impact on the render loop
    invisible. A warm failure must never crash the app (the sync fallback
    still guarantees correctness), hence the blanket except."""
    try:
        for suit in suits:
            for rr in range(0, _GLYPH_RI + 1):
                _interior_geom(suit, rr)
                if yield_s:
                    time.sleep(yield_s)
            for rr in range(0, _MAX_RI + 1):
                _ring_geom(suit, rr)
                if yield_s:
                    time.sleep(yield_s)
    except Exception:
        logging.getLogger(__name__).debug(
            "poker background geometry warm failed", exc_info=True
        )
```

(`threading` is imported now but first used in Task 2 — if ruff flags F401 at this commit, add it in Task 2's step instead.)

In `_ensure_plan`, replace the warm block's local bound computation:

```python
            max_ri = int(math.ceil(self._max_r))
            glyph_ri = int(math.ceil(GLYPH_R))
            for suit in {g.suit for g in self._plan}:
                _warm_suit_geometry(suit, max_ri, glyph_ri)
```

with the shared constants (identical values — `self._max_r` is always `max_radius(GRID, GRID)`):

```python
            for suit in {g.suit for g in self._plan}:
                _warm_suit_geometry(suit, _MAX_RI, _GLYPH_RI)
```

- [ ] **Step 4: Add the session pre-warm fixture**

Append to `plugins/flair/tests/conftest.py`:

```python
@pytest.fixture(autouse=True, scope="session")
def _prewarm_poker_geometry():
    """Warm ALL poker suit geometry synchronously before any test runs, so
    the background warm introduced for the first-firing stall never has a
    live thread during tests (a mid-test thread would pollute the mask-spy
    counts in TestNoPerFiringRasterization)."""
    from led_ticker_flair.flair import poker

    poker._warm_worker(list(poker.SUITS), yield_s=0)
    yield
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run --extra dev pytest tests/test_flair_poker_transition.py tests/test_flair_poker_plan.py tests/test_flair_poker_shapes.py -q`
Expected: all PASS (including the 2 new ones)

- [ ] **Step 6: Commit**

```bash
git add plugins/flair/src/led_ticker_flair/flair/poker.py plugins/flair/tests/conftest.py plugins/flair/tests/test_flair_poker_transition.py
git commit -m "perf(poker): extract _warm_worker + radius constants; session pre-warm in tests"
```

---

### Task 2: Background dispatch at construction

**Files:**
- Modify: `plugins/flair/src/led_ticker_flair/flair/poker.py` (below `_warm_worker`; end of `Poker.__init__` around line 256)
- Modify: `plugins/flair/tests/conftest.py`
- Test: `plugins/flair/tests/test_flair_poker_transition.py`

**Interfaces:**
- Consumes: `_warm_worker(suits, yield_s=0.005)` from Task 1.
- Produces: `_start_background_warm(suits: list[str]) -> None`; module state `_warm_lock: threading.Lock`, `_warm_dispatched: set[str]`, `_warm_threads: list[threading.Thread]`.

- [ ] **Step 1: Write the failing tests**

Append to `plugins/flair/tests/test_flair_poker_transition.py`:

```python
class TestBackgroundWarm:
    """Construction dispatches the geometry warm to a daemon thread — once
    per suit per process — so the first firing renders like every other
    firing instead of stalling ~2-3s on the Pi."""

    def test_saturated_process_spawns_no_thread(self) -> None:
        import led_ticker_flair.flair.poker as m

        # The session fixture saturated _warm_dispatched, so constructions
        # here must not spawn threads (this is also what keeps every other
        # test in the suite free of live warm threads).
        before = len(m._warm_threads)
        Poker(seed=1)
        Poker(suits=["hearts", "clubs"], seed=2)
        assert len(m._warm_threads) == before

    def test_new_suits_spawn_single_daemon_thread(self, monkeypatch) -> None:
        import led_ticker_flair.flair.poker as m

        started: list = []

        class _SpyThread:
            def __init__(self, *args, **kwargs):
                self.kwargs = kwargs

            def start(self):
                started.append(self)

        monkeypatch.setattr(m.threading, "Thread", _SpyThread)
        monkeypatch.setattr(m, "_warm_dispatched", set())
        monkeypatch.setattr(m, "_warm_threads", [])

        Poker(seed=3)  # default pool = all four suits
        assert len(started) == 1
        assert started[0].kwargs["daemon"] is True
        assert started[0].kwargs["target"] is m._warm_worker
        assert sorted(started[0].kwargs["args"][0]) == sorted(SUITS)

        Poker(seed=4)  # same pool again -> deduped, nothing new
        assert len(started) == 1

    def test_partial_overlap_dispatches_only_new_suits(self, monkeypatch) -> None:
        import led_ticker_flair.flair.poker as m

        started: list = []

        class _SpyThread:
            def __init__(self, *args, **kwargs):
                self.kwargs = kwargs

            def start(self):
                started.append(self)

        monkeypatch.setattr(m.threading, "Thread", _SpyThread)
        monkeypatch.setattr(m, "_warm_dispatched", {"hearts", "spades"})
        monkeypatch.setattr(m, "_warm_threads", [])

        Poker(suits=["hearts", "diamonds"], seed=6)
        assert len(started) == 1
        assert started[0].kwargs["args"][0] == ["diamonds"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --extra dev pytest tests/test_flair_poker_transition.py -q -k BackgroundWarm`
Expected: FAIL — `test_saturated_process_spawns_no_thread` with `AttributeError: ... no attribute '_warm_threads'`; the other two likewise (no dispatch exists).

- [ ] **Step 3: Implement `_start_background_warm` + `__init__` hook**

In `poker.py`, immediately below `_warm_worker`, add:

```python
_warm_lock = threading.Lock()
_warm_dispatched: set[str] = set()
_warm_threads: list[threading.Thread] = []


def _start_background_warm(suits: list[str]) -> None:
    """Dispatch a daemon thread warming any not-yet-dispatched suits.

    Called from Poker.__init__ — i.e. at CONFIG LOAD, many seconds before
    the first firing (there is no entry transition into the first boot
    section), so the warm wins its race against first use by a wide
    margin. Each suit is dispatched once per process no matter how many
    poker sections the config declares. Threads are kept in _warm_threads
    so tests can inspect/join; a firing that somehow beats the warm still
    falls back to the synchronous _warm_suit_geometry in _ensure_plan."""
    with _warm_lock:
        new = [s for s in suits if s not in _warm_dispatched]
        if not new:
            return
        _warm_dispatched.update(new)
        thread = threading.Thread(
            target=_warm_worker, args=(new,), daemon=True, name="poker-geom-warm"
        )
        _warm_threads.append(thread)
        thread.start()
```

At the very end of `Poker.__init__` (after `self._last_t = 1.0`), add:

```python
        # Warm suit geometry off the render path — see _start_background_warm.
        _start_background_warm(self.suits)
```

- [ ] **Step 4: Saturate the dispatch set in the session fixture**

In `plugins/flair/tests/conftest.py`, update `_prewarm_poker_geometry` so no thread ever spawns during tests:

```python
@pytest.fixture(autouse=True, scope="session")
def _prewarm_poker_geometry():
    """Warm ALL poker suit geometry synchronously before any test runs, so
    the background warm introduced for the first-firing stall never has a
    live thread during tests (a mid-test thread would pollute the mask-spy
    counts in TestNoPerFiringRasterization)."""
    from led_ticker_flair.flair import poker

    poker._warm_worker(list(poker.SUITS), yield_s=0)
    poker._warm_dispatched.update(poker.SUITS)
    yield
```

- [ ] **Step 5: Run the full flair suite**

Run: `uv run --extra dev pytest tests/ -q`
Expected: all PASS (487: 482 existing + 5 new across Tasks 1–2)

- [ ] **Step 6: Commit**

```bash
git add plugins/flair/src/led_ticker_flair/flair/poker.py plugins/flair/tests/conftest.py plugins/flair/tests/test_flair_poker_transition.py
git commit -m "perf(poker): background geometry warm at construction (first-firing stall)"
```

---

### Task 3: Verification, lint, PR body

**Files:**
- Modify: PR #71 body (via `gh pr edit`)
- No source changes expected

**Interfaces:**
- Consumes: everything from Tasks 1–2.
- Produces: pushed branch, updated PR body.

- [ ] **Step 1: Fresh-subprocess end-to-end verification (not committed)**

Write `/Users/james/.claude/jobs/517fe32c/tmp/poker_firstfire.py`:

```python
"""Fresh process: construct Poker (dispatches warm), wait as a boot would,
then time the first frame. Before this feature the first frame paid ~770ms
(dev); now it should be ~ms."""

import time
from unittest import mock

from led_ticker.plugin import ScaledCanvas
from led_ticker_flair.flair import poker
from led_ticker_flair.flair.poker import Poker


class Stub:
    def __init__(self, w, h):
        self.width, self.height = w, h

    def SetPixel(self, *a):
        pass

    def Clear(self):
        pass

    def Fill(self, *a):
        pass


def widget():
    w = mock.Mock()
    w.draw.side_effect = lambda c, cursor_pos=0, **k: (c, cursor_pos)
    return w


t0 = time.perf_counter()
p = Poker(seed=7)
construct_ms = (time.perf_counter() - t0) * 1000
print(f"construction: {construct_ms:.1f}ms (must be ~0 — non-blocking)")

for th in poker._warm_threads:
    th.join(timeout=30)  # stand-in for the boot + first-section-hold window
print("warm thread(s) joined")

canvas = ScaledCanvas(Stub(256, 64), scale=4, content_height=16)
o, i = widget(), widget()
t0 = time.perf_counter()
p.frame_at(0.3, canvas, o, i)
first_ms = (time.perf_counter() - t0) * 1000
print(f"first-ever frame after warm: {first_ms:.1f}ms (was ~770ms dev)")
```

Run: `uv run --extra dev python /Users/james/.claude/jobs/517fe32c/tmp/poker_firstfire.py`
Expected: construction < 10ms; first frame < 10ms.

- [ ] **Step 2: Lint gate**

Run: `uv run --extra dev ruff check src/ tests/ && uv run --extra dev ruff format --check src/ tests/`
Expected: `All checks passed!` / `already formatted`

- [ ] **Step 3: Push**

```bash
git push
```

- [ ] **Step 4: Update PR #71 body**

Replace the "Remaining honest note" paragraph with a short "First-firing warm (commit 4+)" section: geometry now warms in a boot-time daemon thread (dispatched at config load, per-radius yields, sync fallback intact); first firing measured <10ms construction + <10ms first frame in a fresh process; tests never run a live thread (session pre-warm fixture). Keep the existing "Test on the sign" section, updating the expectation line to "first poker transition is smooth too". Use `gh pr edit 71 --body-file <tmp file>`.
