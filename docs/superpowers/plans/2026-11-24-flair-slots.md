# flair.slots Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `flair.slots.{forward,reverse,alternating,random}` — characters spin vertically like slot-machine reels, all starting together and stopping one after another — on a firing-loop base extracted from `flair.splitflap`, to the visual gate.

**Architecture:** PR 1 (Tasks 1–2) is a behaviour-free refactor: splitflap's `frame_at` / `_plan` / ripple move into `_board_transition.BoardTransition` with three hooks (constructor, `_schedule`, `_paint`); splitflap becomes a thin subclass pinned by its existing tests. PR 2 (Tasks 3–7) adds a pure reel painter (`slots_paint.py`), a pure motion profile and the `Slots` subclasses (`slots.py`), reusing `splitflap_board.build_board` untouched, then docs, smoke configs and the visual gate.

**Tech Stack:** Python 3.14, led-ticker plugin API (`led_ticker.plugin`), pytest, uv workspace (`plugins/flair`), pyright.

**Spec:** `docs/superpowers/specs/2026-11-24-flair-slots-transition-design.md`

## Global Constraints

- Import only from `led_ticker.plugin` (never `led_ticker.<internal>`); no `from __future__ import annotations`.
- Core floor unchanged: `led-ticker-core>=4.35` (pyproject already).
- `scale_switch_at = 1.0`; snap at `t >= SNAP_THRESHOLD` via `snap_reset(canvas, incoming_bg_color)` + `incoming.draw(canvas, cursor_pos=0)`; new firing rule `t == 0.0 or t < self._last_t`; `real` re-derived every call, never cached.
- `splitflap_board.py`, `splitflap_paint.py`, `_deck_snapshot.py` are NOT modified by any task.
- Splitflap rendering byte-identical after PR 1; its three test files pass with exactly one edit (the monkeypatch target in `test_snap_draws_incoming`).
- Slots knobs: `spins` int in `[0, 6]` default 3; `stagger` float in `[0.0, 0.9]` default 0.5; bool rejected (`ValueError`). `min_frames = 60`. Reels spin DOWN (next symbol enters from the top).
- Constants (spec, tune only at the visual gate): `U_IN = 0.15`, `CRUISE_END = 0.45`, `SETTLE_START = 0.9`, `SPIN_SHADE = 0.6`, `gap = max(1, round(P / 4))`, `pitch = P + gap`, `B = min(gap, max(1, round(pitch / 8)))`.
- Work in a git worktree (James's rule: never on the primary checkout's branch). PR 1 branch `refactor/flair-board-transition`; PR 2 branch `feat/flair-slots` stacked on it until PR 1 merges. `gh pr create` needs James's go-ahead: write the body to a file in a separate command, then ask.
- Run tests from `plugins/flair`: `uv run pytest tests/<file> -q`. Before each push: `make lint` from the repo root (ruff + pyright) and `make test`.

## Review Focus

1. A reel whose `stop` is tiny (`stagger = 0.9`, first-ranked reel: `stop = 0.1`) must still land exactly and never divide by zero or produce `k = 0`. Test: `test_reel_advances_floor_is_one` (Task 4), `test_high_stagger_first_reel_lands_exactly` (Task 5).
2. A reel whose `seq` has no in-betweens (`spins = 0`, or a pool that only held the pair's own glyphs) but `k > 1` cycles outgoing/blank rather than indexing past the tuple. Test: `test_strip_symbols_without_in_betweens_alternates_blank` (Task 3).
3. The settle must never paint outside the band window or above/below the panel (smallsign `P = 7`, `B = 1`; two_row bands adjacent). Test: `test_paint_reel_clips_to_window_and_panel` (Task 3).
4. Long reels (`stagger = 0.9`, `spins = 6`, last reel `k ≈ 70`) on a full-panel picture must stay within splitflap's per-frame perf budget — paint only the symbols that can intersect the window. Test: `test_perf_full_panel_picture_firing` (Task 5).
5. First and last frames of every reel are the plain glyph (no brightness pop). Test: `test_t0_paints_outgoing_exactly`, `test_all_landed_before_snap`, `test_shade_is_plain_at_ends_and_dim_in_cruise` (Tasks 4–5).

---

### Task 1: Extract `BoardTransition` (PR 1, behaviour-free)

**Files:**
- Create: `plugins/flair/src/led_ticker_flair/flair/_board_transition.py`
- Modify: `plugins/flair/src/led_ticker_flair/flair/splitflap.py` (becomes a thin subclass + re-exports)
- Modify: `plugins/flair/tests/test_flair_splitflap_transition.py:148` (monkeypatch target only)
- Test: `plugins/flair/tests/test_flair_board_transition.py`

**Interfaces:**
- Produces (`_board_transition.py`):
  - `ORDERS = ("forward", "reverse", "random")`, `LAND = 0.9`, `MAX_STAGGER = 0.9`
  - `coerce_steps(value: Any, name: str, cap: int) -> int` — bool / non-int / outside `[0, cap]` → `ValueError(f"{name} must be an int in [0, {cap}]; got {value!r}")`
  - `coerce_stagger(stagger: Any) -> float` — today's `_coerce_stagger`, message unchanged
  - `flap_start(order, centre_x, x_min, x_max, stagger, rand) -> float` — moved verbatim
  - `paint_pixels(set_px: Any, pixels: tuple[Pixel, ...]) -> None` — today's `_paint_pixels`, made module-public so both effects import it (splitflap's `_paint` switches to it)
  - `class BoardTransition(DeckSnapshotMixin)`: `min_frames = 36`, `scale_switch_at = 1.0`, `_order = "forward"`; `__init__(self, steps: int, stagger: float)` stores `self.steps`, `self.stagger`, calls `_init_deck_snapshot(False)`, sets `_board = None`, `_times: list[float] = []`, `_last_t = 1.0`, `_rng = random.Random()`; `frame_at(...)` verbatim from today's splitflap except `self._times = self._schedule(self._board)` and `build_board(out_plan, in_plan, self.steps, self._rng)`; `_schedule(self, board: Board) -> list[float]` = today's `_ripple` body (start times via `flap_start`); `_paint(self, real: Any, board: Board, s: float) -> None` raises `NotImplementedError`.
- Produces (`splitflap.py`): `MAX_FLIPS = 12`; `SplitFlap(BoardTransition)` with `__init__(self, flips: Any = 3, stagger: Any = 0.5)` → `self.flips = coerce_steps(flips, "flips", MAX_FLIPS)`; `super().__init__(self.flips, coerce_stagger(stagger))`; `_paint` as today reading `self._times`; `SplitFlapReverse` / `SplitFlapRandom` / `SplitFlapAlternating` unchanged; re-exports `LAND`, `ORDERS`, `MAX_STAGGER`, `flap_start` so existing test imports resolve.

- [ ] **Step 1: Create the worktree and branch**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-plugins
git worktree add ../led-ticker-plugins-slots -b refactor/flair-board-transition main
cd ../led-ticker-plugins-slots && pwd && git branch --show-current
```
Expected: `refactor/flair-board-transition`. Every later command in this plan runs inside that worktree.

- [ ] **Step 2: Write the failing tripwire tests**

`plugins/flair/tests/test_flair_board_transition.py`:

```python
import pytest

from led_ticker_flair.flair import _board_transition as bt
from led_ticker_flair.flair.splitflap import SplitFlap


def test_splitflap_subclasses_board_transition_and_does_not_fork_frame_at():
    assert issubclass(SplitFlap, bt.BoardTransition)
    assert "frame_at" not in SplitFlap.__dict__
    assert "_schedule" not in SplitFlap.__dict__  # splitflap keeps the base ripple


def test_base_paint_is_abstract():
    with pytest.raises(NotImplementedError):
        bt.BoardTransition(0, 0.0)._paint(None, None, 0.0)


@pytest.mark.parametrize("bad", [-1, True, 1.5, "3", 7])
def test_coerce_steps_rejects_with_callers_name(bad):
    with pytest.raises(ValueError, match=r"spins must be an int in \[0, 6\]"):
        bt.coerce_steps(bad, "spins", 6)


def test_coerce_steps_accepts_edges():
    assert bt.coerce_steps(0, "x", 6) == 0 and bt.coerce_steps(6, "x", 6) == 6


def test_splitflap_keeps_its_cap_and_message():
    with pytest.raises(ValueError, match=r"flips must be an int in \[0, 12\]"):
        SplitFlap(flips=13)
    assert SplitFlap(flips=12).flips == 12 and SplitFlap(flips=12).steps == 12
```

- [ ] **Step 3: Run to verify failure**

Run: `cd plugins/flair && uv run pytest tests/test_flair_board_transition.py -q`
Expected: FAIL — `ModuleNotFoundError: led_ticker_flair.flair._board_transition`.

- [ ] **Step 4: Create `_board_transition.py` and slim `splitflap.py`**

Move the symbols listed under Interfaces. The module docstring names it the ONE firing loop for board-style transitions and points at both specs. `splitflap.py` keeps its docstring, `MAX_FLIPS`, the four classes, and the re-export line `from ._board_transition import LAND, MAX_STAGGER, ORDERS, flap_start  # noqa: F401`.

- [ ] **Step 5: Re-point the one monkeypatch**

In `tests/test_flair_splitflap_transition.py::test_snap_draws_incoming` change the target string to `"led_ticker_flair.flair._board_transition.snap_reset"`. No other test edit.

- [ ] **Step 6: Run the splitflap suites and the new file**

Run: `uv run pytest tests/test_flair_board_transition.py tests/test_flair_splitflap_transition.py tests/test_flair_splitflap_board.py tests/test_flair_splitflap_paint.py tests/test_import_purity.py -q`
Expected: all PASS. Then `git diff --stat tests/` shows only `test_flair_splitflap_transition.py` (1 line) and the new file.

- [ ] **Step 7: Lint + full suite**

Run from the worktree root: `make lint && make test`
Expected: ruff clean, pyright 0 errors, tests green.

- [ ] **Step 8: Commit**

```bash
git add plugins/flair/src/led_ticker_flair/flair/_board_transition.py plugins/flair/src/led_ticker_flair/flair/splitflap.py plugins/flair/tests/test_flair_board_transition.py plugins/flair/tests/test_flair_splitflap_transition.py
git commit -m "refactor(flair): extract BoardTransition firing loop from splitflap

Behaviour-free. Precursor for flair.slots (second board-style effect).

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: PR 1 docs + open the PR

**Files:**
- Modify: `plugins/flair/CLAUDE.md` (the `## flair.splitflap transition invariants` section)
- Add: `docs/superpowers/specs/2026-11-24-flair-slots-transition-design.md`, `docs/superpowers/plans/2026-11-24-flair-slots.md` (already written; commit them here)

- [ ] **Step 1: Add the CLAUDE.md bullet**

First bullet of the splitflap invariants section:

> - **The firing loop lives in `_board_transition.BoardTransition`** (`frame_at`, refire rule, snap, lazy `build_board`, per-call `unwrap_to_real`, `s = min(t / SNAP_THRESHOLD / LAND, 1)`) with three hooks: the constructor (`steps`, `stagger`), `_schedule(board) -> list[float]` (default: splitflap's ripple starts via `flap_start`) and `_paint(real, board, s)`. Splitflap and slots are subclasses; never re-fork `frame_at` into an effect module. Tripwire: `tests/test_flair_board_transition.py`.

- [ ] **Step 2: Commit docs**

```bash
git add plugins/flair/CLAUDE.md docs/superpowers/specs/2026-11-24-flair-slots-transition-design.md docs/superpowers/plans/2026-11-24-flair-slots.md
git commit -m "docs(flair): BoardTransition invariant; slots spec + plan

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

- [ ] **Step 3: Push and prepare the PR body, then ASK James before `gh pr create`**

```bash
git push -u origin refactor/flair-board-transition
cat > /private/tmp/claude-501/-Users-james-projects-github-jamesawesome-led-ticker/e377e583-9caf-4bed-9bca-407823bf1018/scratchpad/pr1-body.md <<'EOF'
Behaviour-free precursor for `flair.slots` (spec: docs/superpowers/specs/2026-11-24-flair-slots-transition-design.md).

- `_board_transition.BoardTransition`: splitflap's firing loop (`frame_at`, refire rule, snap, lazy `build_board`) with `_schedule` / `_paint` hooks.
- `splitflap.py` is now a thin subclass; `splitflap_board.py` / `splitflap_paint.py` untouched.
- One test edit: the `snap_reset` monkeypatch target moves with `frame_at`.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
```
Then stop and ask James for the go-ahead to run `gh pr create --draft --title "refactor(flair): extract BoardTransition firing loop from splitflap" --body-file <that file>`.

---

### Task 3: Reel painter (`slots_paint.py`) — PR 2

**Files:**
- Create: `plugins/flair/src/led_ticker_flair/flair/slots_paint.py`
- Test: `plugins/flair/tests/test_flair_slots_paint.py`

**Interfaces:**
- Consumes: `splitflap_board.BandGeom` (`lo`, `hi`), `FlapCell` (`slot`, `rows: dict[int, Row]`), `splitflap_paint.SetPx`, `paint_cell`.
- Produces:
  - `SPIN_SHADE = 0.6`
  - `reel_pitch(band: BandGeom) -> tuple[int, int]` → `(pitch, gap)` with `P = band.hi - band.lo + 1`, `gap = max(1, round(P / 4))`, `pitch = P + gap`
  - `overshoot_rows(pitch: int, gap: int) -> int` → `min(gap, max(1, round(pitch / 8)))`
  - `strip_symbols(seq: tuple[FlapCell | None, ...], k: int) -> tuple[FlapCell | None, ...]` — length `k + 1`: `seq[0]`, then `k - 1` symbols cycling `seq[1:-1]` in order (or cycling `(None, seq[0])` when `seq` has no in-betweens), then `seq[-1]`. Requires `k >= 1`, `len(seq) >= 2`.
  - `paint_reel(set_px: SetPx, strip, band: BandGeom, d: float, shade: float, w: int, h: int) -> None` — symbol `j` is drawn with its rows shifted by `round(d) - j * pitch`; a pixel is written only if its shifted `y` is in `[band.lo, band.hi]` and `[0, h)` and `x` in `[0, w)`; rgb scaled by `shade` (`round(c * shade)`; `shade == 1.0` writes exact values). Iterate only `j` in `[max(0, ceil((d - P) / pitch)), min(k, floor((d + P) / pitch))]`.

- [ ] **Step 1: Branch for PR 2**

```bash
git checkout -b feat/flair-slots   # from refactor/flair-board-transition, in the same worktree
```

- [ ] **Step 2: Write the failing tests**

`tests/test_flair_slots_paint.py` (fixtures `_cell`, `_record`, `RED`, `GREEN` copied from `test_flair_splitflap_paint.py`; `BAND = BandGeom(lo=4, hinge=8, hi=11)` so the window is rows 4–11, `P = 8`, `W, H = 32, 16`):

```python
def test_reel_pitch_and_gap():
    assert reel_pitch(BAND) == (10, 2)
    assert reel_pitch(BandGeom(0, 3, 6)) == (9, 2)      # P = 7 smallsign
    assert reel_pitch(BandGeom(0, 1, 2)) == (4, 1)      # gap floors at 1


def test_overshoot_rows_capped_by_gap():
    assert overshoot_rows(10, 2) == 1
    assert overshoot_rows(40, 8) == 5
    assert overshoot_rows(4, 1) == 1


def test_strip_symbols_cycles_in_betweens():
    a, m1, m2, b = _cell(RED), _cell(GREEN), _cell((0, 0, 200)), _cell((9, 9, 9))
    assert strip_symbols((a, m1, m2, b), 1) == (a, b)
    assert strip_symbols((a, m1, m2, b), 3) == (a, m1, m2, b)
    assert strip_symbols((a, m1, m2, b), 6) == (a, m1, m2, m1, m2, m1, b)


def test_strip_symbols_without_in_betweens_alternates_blank():
    a, b = _cell(RED), _cell(GREEN)
    assert strip_symbols((a, b), 4) == (a, None, a, None, b)
    assert strip_symbols((None, b), 3) == (None, None, None, b)


def test_paint_reel_d0_is_outgoing_in_place_exact():
    got, set_px = _record()
    paint_reel(set_px, strip_symbols((_cell(RED, range(4, 12)), _cell(GREEN, range(4, 12))), 1), BAND, 0.0, 1.0, W, H)
    assert set(got) == {(x, y) for x in range(2, 5) for y in range(4, 12)}
    assert set(got.values()) == {RED}


def test_paint_reel_landed_is_incoming_in_place_exact():
    got, set_px = _record()
    strip = strip_symbols((_cell(RED, range(4, 12)), _cell(GREEN, range(4, 12))), 1)
    paint_reel(set_px, strip, BAND, 10.0, 1.0, W, H)   # d = k * pitch
    assert set(got) == {(x, y) for x in range(2, 5) for y in range(4, 12)}
    assert set(got.values()) == {GREEN}


def test_paint_reel_mid_travel_shows_two_symbols_and_a_gap():
    got, set_px = _record()
    strip = strip_symbols((_cell(RED, range(4, 12)), _cell(GREEN, range(4, 12))), 1)
    paint_reel(set_px, strip, BAND, 5.0, 1.0, W, H)
    rows = _rows(got)
    assert rows[9] == RED and rows[11] == RED        # outgoing moved down 5: rows 9..11 visible
    assert rows[4] == GREEN and rows[6] == GREEN     # incoming entering from the top: rows 4..6
    assert 7 not in rows and 8 not in rows           # the 2-row gap between them


def test_paint_reel_overshoot_dips_and_leaves_bg_above():
    got, set_px = _record()
    strip = strip_symbols((_cell(RED, range(4, 12)), _cell(GREEN, range(4, 12))), 1)
    paint_reel(set_px, strip, BAND, 11.0, 1.0, W, H)   # D + B, B = 1
    rows = _rows(got)
    assert 4 not in rows and all(rows[y] == GREEN for y in range(5, 12))


def test_paint_reel_shade_scales_rgb():
    got, set_px = _record()
    paint_reel(set_px, (_cell(RED, range(4, 12)),), BAND, 0.0, 0.6, W, H)
    assert set(got.values()) == {(120, 0, 0)}


def test_paint_reel_clips_to_window_and_panel():
    got, set_px = _record()
    tall = _cell(RED, range(0, 16))                     # taller than the window
    paint_reel(set_px, strip_symbols((tall, tall), 1), BAND, 3.0, 1.0, W, H)
    assert {y for _, y in got} <= set(range(4, 12))
    got2, set_px2 = _record()
    paint_reel(set_px2, strip_symbols((_cell(RED, range(0, 4), slot=30), _cell(GREEN, range(0, 4), slot=30)), 1), BandGeom(0, 2, 3), 2.0, 1.0, W, H)
    assert all(0 <= x < W and 0 <= y < H for x, y in got2)


def test_paint_reel_only_visits_visible_symbols():
    calls = []
    class _Cell:  # noqa: D401 - counts row lookups
        slot, width = 2, 3
        @property
        def rows(self):
            calls.append(1)
            return {}
    strip = tuple(_Cell() for _ in range(71))
    paint_reel(lambda *a: None, strip, BAND, 350.0, 1.0, W, H)
    assert len(calls) <= 3
```

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest tests/test_flair_slots_paint.py -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 4: Implement `slots_paint.py`** per Interfaces. Pure module: no canvas imports, writes only through `set_px`.

- [ ] **Step 5: Run to verify pass**

Run: `uv run pytest tests/test_flair_slots_paint.py -q` → PASS.

- [ ] **Step 6: Commit**

```bash
git add plugins/flair/src/led_ticker_flair/flair/slots_paint.py plugins/flair/tests/test_flair_slots_paint.py
git commit -m "feat(flair): slots reel painter (pure)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: Reel motion profile (`slots.py`, pure functions)

**Files:**
- Create: `plugins/flair/src/led_ticker_flair/flair/slots.py` (pure functions first; classes in Task 5)
- Test: `plugins/flair/tests/test_flair_slots_motion.py`

**Interfaces:**
- Consumes: `_board_transition.flap_start`.
- Produces (module constants + functions):
  - `MAX_SPINS = 6`, `U_IN = 0.15`, `CRUISE_END = 0.45`, `SETTLE_START = 0.9`
  - `reel_stop(order: str, centre_x: int, x_min: int, x_max: int, stagger: float, rand: float) -> float` → `(1.0 - stagger) + flap_start(order, centre_x, x_min, x_max, stagger, rand)`
  - `reel_advances(spins: int, stop: float, stagger: float) -> int` → `max(1, round((spins + 1) * stop / (1.0 - stagger)))`
  - `speed_norm(u: float) -> float` — trapezoid: `u / U_IN` on `[0, U_IN)`; `1.0` on `[U_IN, CRUISE_END)`; `(SETTLE_START - u) / (SETTLE_START - CRUISE_END)` on `[CRUISE_END, SETTLE_START)`; `0.0` on `[SETTLE_START, 1]`. `u` clamped to `[0, 1]`.
  - `displacement(u: float, travel: float, overshoot: int) -> float` — `u` clamped; for `u <= SETTLE_START`: `travel * I(u) / I(SETTLE_START)` where `I` is the closed-form integral of `speed_norm` (so `I(SETTLE_START) = U_IN/2 + (CRUISE_END - U_IN) + (SETTLE_START - CRUISE_END)/2 = 0.6`); for `u > SETTLE_START`: `travel + overshoot * sin(pi * (u - SETTLE_START) / (1 - SETTLE_START))`.
  - `shade_for(u: float) -> float` → `1.0 - (1.0 - SPIN_SHADE) * speed_norm(u)` (imports `SPIN_SHADE` from `slots_paint`).

- [ ] **Step 1: Write the failing tests**

```python
import math
import pytest
from led_ticker_flair.flair import slots as S


def test_reel_stop_first_and_last():
    assert S.reel_stop("forward", 0, 0, 100, 0.5, 0.0) == pytest.approx(0.5)
    assert S.reel_stop("forward", 100, 0, 100, 0.5, 0.0) == pytest.approx(1.0)
    assert S.reel_stop("reverse", 0, 0, 100, 0.5, 0.0) == pytest.approx(1.0)
    assert S.reel_stop("random", 0, 0, 100, 0.5, 0.3) == pytest.approx(0.65)
    assert S.reel_stop("forward", 0, 0, 100, 0.0, 0.0) == pytest.approx(1.0)


def test_reel_advances_scales_with_stop():
    assert S.reel_advances(3, 0.5, 0.5) == 4          # first reel: spins + 1
    assert S.reel_advances(3, 1.0, 0.5) == 8          # last reel spins twice as long
    assert S.reel_advances(0, 1.0, 0.0) == 1


def test_reel_advances_floor_is_one():
    assert S.reel_advances(0, 0.1, 0.9) == 1


def test_speed_norm_trapezoid():
    assert S.speed_norm(0.0) == 0.0
    assert S.speed_norm(0.075) == pytest.approx(0.5)
    assert S.speed_norm(0.3) == 1.0
    assert S.speed_norm(0.675) == pytest.approx(0.5)
    assert S.speed_norm(0.9) == 0.0 and S.speed_norm(1.0) == 0.0
    assert S.speed_norm(-1) == 0.0 and S.speed_norm(2) == 0.0


def test_displacement_endpoints_and_monotone_travel():
    assert S.displacement(0.0, 100.0, 3) == 0.0
    assert S.displacement(0.9, 100.0, 3) == pytest.approx(100.0)
    assert S.displacement(1.0, 100.0, 3) == pytest.approx(100.0, abs=1e-9)
    xs = [S.displacement(i / 90, 100.0, 3) for i in range(82)]   # travel only: u <= 0.9
    assert all(b >= a for a, b in zip(xs, xs[1:]))


def test_displacement_overshoots_by_b_at_settle_midpoint():
    assert S.displacement(0.95, 100.0, 3) == pytest.approx(103.0)
    assert S.displacement(0.95, 100.0, 1) == pytest.approx(101.0)


def test_displacement_cruise_speed_matches_area():
    # cruise: d' = travel / 0.6 per unit u
    d1, d2 = S.displacement(0.3, 60.0, 1), S.displacement(0.4, 60.0, 1)
    assert (d2 - d1) / 0.1 == pytest.approx(100.0)


def test_shade_is_plain_at_ends_and_dim_in_cruise():
    assert S.shade_for(0.0) == 1.0 and S.shade_for(0.9) == 1.0 and S.shade_for(1.0) == 1.0
    assert S.shade_for(0.3) == pytest.approx(0.6)
```

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/test_flair_slots_motion.py -q` → `ModuleNotFoundError`.

- [ ] **Step 3: Implement the functions** in `slots.py` with the module docstring (one-breath design, spec path). Closed-form `I(u)`:
  `u < U_IN: u²/(2·U_IN)`; `u < CRUISE_END: U_IN/2 + (u − U_IN)`; else `U_IN/2 + (CRUISE_END − U_IN) + (SETTLE_START − CRUISE_END)/2 · (1 − ((SETTLE_START − u)/(SETTLE_START − CRUISE_END))²)`.

- [ ] **Step 4: Run to verify pass** → PASS.

- [ ] **Step 5: Commit**

```bash
git add plugins/flair/src/led_ticker_flair/flair/slots.py plugins/flair/tests/test_flair_slots_motion.py
git commit -m "feat(flair): slots reel motion profile (pure)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: `Slots` transition classes, registration, transition-level tests

**Files:**
- Modify: `plugins/flair/src/led_ticker_flair/flair/slots.py` (add classes)
- Modify: `plugins/flair/src/led_ticker_flair/flair/__init__.py` (imports + 4 `api.transition` lines after the splitflap block; docstring mention)
- Modify: `plugins/flair/tests/test_flair_board_transition.py` (extend the tripwire to `Slots`)
- Test: `plugins/flair/tests/test_flair_slots_transition.py`

**Interfaces:**
- Consumes: `BoardTransition`, `coerce_steps`, `coerce_stagger` (Task 1); `reel_pitch`, `overshoot_rows`, `strip_symbols`, `paint_reel`, `paint_cell` (Task 3); motion functions (Task 4); `_variants.Cycling`; `splitflap_board.Board`.
- Produces:
  - `@dataclass(frozen=True) class Reel: stop: float; k: int; strip: tuple[FlapCell | None, ...]`
  - `class Slots(BoardTransition)`: `min_frames = 60`, `_order = "forward"`; `__init__(self, spins: Any = 3, stagger: Any = 0.5)` → `self.spins = coerce_steps(spins, "spins", MAX_SPINS)`; `super().__init__(self.spins, coerce_stagger(stagger))`; `self._reels: list[Reel] = []`.
    `_schedule(board)`: `xs = [f.centre_x for f in board.flaps]`; stops via `reel_stop(self._order, x, lo, hi, self.stagger, self._rng.random())`; for each flap build `Reel(stop, k = reel_advances(self.spins, stop, self.stagger), strip = strip_symbols(flap.seq, k))` (static flaps: `Reel(stop, 1, flap.seq)` — never painted through the strip); sets `self._reels`; returns the stops.
    `_paint(real, board, s)`: `under_out`/`ring_out` before `s < 0.5`, else `_in`, via `_board_transition.paint_pixels`; per flap/reel: static → `paint_cell(set_px, seq[0], w, h)`; else `u = min(1.0, s / reel.stop)`; `pitch, gap = reel_pitch(band)`; `d = displacement(u, reel.k * pitch, overshoot_rows(pitch, gap))`; `paint_reel(set_px, reel.strip, band, d, shade_for(u), w, h)`.
  - `SlotsReverse(Slots)` `_order = "reverse"`; `SlotsRandom(Slots)` `_order = "random"`; `SlotsAlternating(Cycling)` with `__init__(self, spins=3, stagger=0.5)` → `super().__init__([Slots(spins, stagger), SlotsReverse(spins, stagger)])`.
  - Registration names: `"slots.forward"`, `"slots.reverse"`, `"slots.alternating"`, `"slots.random"`.

- [ ] **Step 1: Write the failing tests**

`tests/test_flair_slots_transition.py` — copy `_StubCanvas`, `_widget`, `_block`, `_two_cells`, `_frame`, `_t` and the `TestRealCoreWidgets` / `TestPerf` fixtures from the splitflap transition test (per-file duplication is this repo's convention), importing `LAND` from `_board_transition` and the classes from `slots`. `_two_cells` gives two 3-wide, 8-tall cells at x 0–2 and 10–12 on a 16×8 canvas (`P = 8`, `pitch = 10`, `B = 1`).

```python
class TestKnobs:
    @pytest.mark.parametrize("kw", [{"spins": -1}, {"spins": True}, {"spins": 1.5}, {"spins": "3"}, {"spins": 7}, {"stagger": 0.95}, {"stagger": -0.1}, {"stagger": True}])
    def test_knob_validation(self, kw):
        with pytest.raises(ValueError):
            Slots(**kw)

    def test_defaults(self):
        p = Slots()
        assert (p.spins, p.stagger) == (3, 0.5)
        assert p.min_frames == 60 and p.scale_switch_at == 1.0
        assert Slots(spins=6).spins == 6


class TestFrames:
    def test_t0_paints_outgoing_exactly(self):           # as splitflap's
    def test_snap_draws_incoming(self, monkeypatch):      # patch "led_ticker_flair.flair._board_transition.snap_reset"
    def test_all_landed_before_snap(self):                # as splitflap's (0.92 * SNAP_THRESHOLD == incoming exactly)

    def test_all_reels_start_together(self):
        c = _StubCanvas(16, 8)
        o, i = _two_cells(RED), _two_cells(GREEN)
        p = Slots(spins=0, stagger=0.5)
        at0 = _frame(p, 0.0, c, o, i)
        early = _frame(p, _t(0.1), c, o, i)
        left = lambda px: {k: v for k, v in px.items() if k[0] < 5}
        right = lambda px: {k: v for k, v in px.items() if k[0] >= 10}
        assert left(early) != left(at0) and right(early) != right(at0)

    def test_forward_left_reel_stops_first(self):
        c = _StubCanvas(16, 8)
        o, i = _two_cells(RED), _two_cells(GREEN)
        p = Slots(spins=0, stagger=0.5)
        p.frame_at(0.0, c, o, i)
        px = _frame(p, _t(0.5), c, o, i)
        assert all(px[(x, y)] == GREEN for x in range(3) for y in range(8))   # left landed
        right = {k: v for k, v in px.items() if k[0] >= 10}
        assert right != {(x, y): RED for x in range(10, 13) for y in range(8)}
        assert right != {(x, y): GREEN for x in range(10, 13) for y in range(8)}

    def test_reverse_right_reel_stops_first(self):        # mirror of the above with SlotsReverse

    def test_high_stagger_first_reel_lands_exactly(self):
        c = _StubCanvas(16, 8)
        o, i = _two_cells(RED), _two_cells(GREEN)
        p = Slots(spins=0, stagger=0.9)                   # first reel stop = 0.1
        p.frame_at(0.0, c, o, i)
        px = _frame(p, _t(0.1), c, o, i)
        assert all(px[(x, y)] == GREEN for x in range(3) for y in range(8))

    def test_overshoot_dips_incoming_by_one_row(self):
        c = _StubCanvas(16, 8)
        o, i = _two_cells(RED), _two_cells(GREEN)
        p = Slots(spins=0, stagger=0.0)                   # every reel: stop = 1, settle on s in (0.9, 1]
        p.frame_at(0.0, c, o, i)
        px = _frame(p, _t(0.95), c, o, i)
        assert (1, 0) not in px and all(px[(1, y)] == GREEN for y in range(1, 8))

    def test_mid_spin_is_dimmed(self):
        c = _StubCanvas(16, 8)
        o, i = _two_cells(RED), _two_cells(GREEN)
        p = Slots(spins=0, stagger=0.0)
        p.frame_at(0.0, c, o, i)
        px = _frame(p, _t(0.3), c, o, i)                  # cruise: shade 0.6
        reds = {v for v in px.values() if v[1] == 0 and v[2] == 0}
        assert reds and all(0 < r < 255 for r, _, _ in reds)

    def test_long_reel_cycles_in_betweens(self):
        # three distinct cells so the pool has in-betweens; stagger 0.9 -> last reel k = round(4 * 1.0 / 0.1) = 40
        p = Slots(spins=3, stagger=0.9)
        c = _StubCanvas(40, 8)
        o = _widget(_block(0, 3, 8, RED) + _block(10, 13, 8, GREEN) + _block(20, 23, 8, BLUE))
        i = _widget(_block(0, 3, 8, GREEN) + _block(10, 13, 8, BLUE) + _block(20, 23, 8, RED))
        p.frame_at(0.0, c, o, i)
        last = max(p._reels, key=lambda r: r.stop)
        assert last.k == 40 and len(last.strip) == 41
        mids = last.strip[1:-1]
        assert len(set(id(m) for m in mids)) < len(mids)  # cycled, not 39 fresh picks

    def test_both_empty_paints_nothing_until_snap(self):  # as splitflap's
    def test_empty_outgoing_spins_from_blank(self):        # as splitflap's test_empty_outgoing_flips_from_blank
    def test_border_ring_static(self):                     # as splitflap's
    def test_image_widget_spins_as_strips(self):           # as splitflap's test_image_widget_flips_as_strips


class TestVariantsRegistration:
    def test_alternating_cycles_forward_reverse(self):    # as splitflap's
    def test_random_order_seeded_reproducible(self):      # as splitflap's
    def test_random_stop_order_differs_between_seeds(self):
        def landed_left(seed: int) -> bool:
            c = _StubCanvas(16, 8)
            p = SlotsRandom(spins=0, stagger=0.9)       # stop = 0.1 + 0.9 * rand
            p._rng = random.Random(seed)
            p.frame_at(0.0, c, _two_cells(RED), _two_cells(GREEN))
            px = _frame(p, _t(0.5), c, _two_cells(RED), _two_cells(GREEN))
            return all(px.get((x, y)) == GREEN for x in range(3) for y in range(8))
        assert len({landed_left(seed) for seed in range(8)}) == 2
    def test_registration_four_types(self):               # reg["slots.forward"] is Slots, etc.


class TestRealCoreWidgets:  # identical to splitflap's four tests, Slots()/SlotsReverse()
class TestPerf:             # identical bodies; same bounds (first < 0.6 s, worst frame < 0.05 s, text firing < 0.5 s), Slots(spins=6, stagger=0.9) for the text firing
```

Extend `tests/test_flair_board_transition.py`:

```python
def test_slots_subclasses_board_transition_and_does_not_fork_frame_at():
    from led_ticker_flair.flair.slots import Slots
    assert issubclass(Slots, bt.BoardTransition)
    assert "frame_at" not in Slots.__dict__
    assert "_schedule" in Slots.__dict__ and "_paint" in Slots.__dict__
```

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/test_flair_slots_transition.py tests/test_flair_board_transition.py -q` → `ImportError: cannot import name 'Slots'`.

- [ ] **Step 3: Implement the classes** per Interfaces; register in `flair/__init__.py` (import block + four `api.transition("slots.<v>")` lines directly after the splitflap ones); add `flair.slots.<order>` to the `__init__` docstring's variant list.

- [ ] **Step 4: Run to verify pass** — the two files, then `uv run pytest tests -q` for the whole flair suite (import purity, registration counts) → PASS.

- [ ] **Step 5: Lint** — `make lint` from the worktree root → clean.

- [ ] **Step 6: Commit**

```bash
git add plugins/flair/src/led_ticker_flair/flair/slots.py plugins/flair/src/led_ticker_flair/flair/__init__.py plugins/flair/tests/test_flair_slots_transition.py plugins/flair/tests/test_flair_board_transition.py
git commit -m "feat(flair): flair.slots.{forward,reverse,alternating,random} reel transition

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: User docs, invariants, smoke configs

**Files:**
- Modify: `plugins/flair/README.md` (new `## Slot-machine transition` section right after `## Split-flap transition`'s Notes, before `## Fisheye animation`)
- Modify: `plugins/flair/CLAUDE.md` (head paragraph + namespace bullet lists gain `flair.slots.*`; new `## flair.slots transition invariants` section after the splitflap one)
- Modify: `plugins/flair/pyproject.toml:4` (`description` adds `slots` next to `split-flap`)
- Create: `plugins/flair/examples/config.slots-smoke.bigsign.toml`, `plugins/flair/examples/config.slots-smoke.smallsign.toml`

- [ ] **Step 1: README section** — same shape as split-flap. Copy to use verbatim for the intro and knobs:

> `flair.slots` is a slot machine. Every character of the old message is a reel: on the first frame all the reels start spinning downward through a few in-between characters, then they stop one after another, left to right, each one slowing down, overshooting its landing by a hair and settling back. The reels spin in place, in your widget's own font, size and colour, on the normal panel background. It's meant to be watched, so give it about three seconds.
>
> Requires **led-ticker-core >= 4.35**. Four variants, named by the order the reels stop:

Variants table: `flair.slots.forward` left → right (the classic); `.reverse` right → left; `.alternating` forward, then reverse, one per firing; `.random` in a random order, fresh each firing.

Config block: `duration = 3.0  # floor: min_frames = 60, i.e. 3.0 s at the default 20 fps` and `transition = "flair.slots.forward"`; a second example `{type = "flair.slots.forward", spins = 0, stagger = 0.8}` captioned "one turn per reel, stopping slowly across the message".

Knobs table: `spins` — int, 0 to 6, default 3 — "In-between characters the FIRST reel passes before it lands. Reels that stop later keep spinning at the same speed, so they pass more (cycling through the same in-betweens). `0` is one turn: the old character scrolls out and the new one scrolls in." `stagger` — number, 0 to 0.9, default 0.5 — "Share of the transition spent stopping the reels one after another. `0` stops every reel together; higher values spread the stops out, and the last reel spins for most of the transition — pair a high `stagger` with a longer `duration`."

Notes: reuse split-flap's bullets (borrowed in-betweens, unchanged characters stay put, different lengths, two-row, images as strips, borders stay put, backgrounds/cross-scale) with "flip" → "spin"; add "**Smallsign.** At 16 rows a reel is 7 or 8 LEDs tall with a 2-LED gap; the visual gate decides whether that reads."

- [ ] **Step 2: CLAUDE.md** — add `flair.slots.*` to both transition lists in the head paragraph / namespace bullet, and the new section:

> ## `flair.slots` transition invariants (`src/led_ticker_flair/flair/slots*.py`)
>
> - **Board verbatim.** Slots consumes `splitflap_board.build_board` unchanged (pairing, bands, pool, strips, `static`); the hinge is unused. Any pairing change belongs in the board layer and is tested there.
> - **Start together, stop in sequence.** Every reel starts at `s = 0`; `_schedule` returns STOP times `(1 − stagger) + flap_start(...)` (so `.random` randomises the stop order). All reels cruise at the same speed: `reel_advances` scales the symbol count with the stop time and `strip_symbols` cycles the in-betweens (or outgoing/blank when there are none). Never give reels equal spin lengths — that is a vertical splitflap. Tripwires: `test_all_reels_start_together`, `test_long_reel_cycles_in_betweens`.
> - **Window = the band's lit extent `[lo, hi]`;** `paint_reel` clips every write to it and to the panel, and visits only the symbols that can intersect it (long reels are O(visible), not O(k)). Pitch `P + gap`, `gap = max(1, round(P/4))`.
> - **Trapezoid motion with settle** (`speed_norm` / `displacement`): ease-in `U_IN`, cruise to `CRUISE_END`, ease-out to `SETTLE_START`, then a `B = min(gap, max(1, round(pitch/8)))`-row overshoot and return. Shade is `1 − 0.4·speed_norm`, so the first and last frames are the plain glyph; nothing peeks in above the dipped glyph (the strip ends at the incoming symbol). Tripwires: `tests/test_flair_slots_motion.py`, `test_overshoot_dips_incoming_by_one_row`.
> - **`min_frames = 60`, `MAX_SPINS = 6`** — pace, not taste: at splitflap's 36 a bigsign reel moves over a third of a symbol per frame. Re-derive the pace table in the spec before loosening either.

- [ ] **Step 3: Smoke configs** — copy both splitflap smoke files; `sed 's/splitflap/slots/g; s/flips = 0/spins = 0/'`; rewrite the header comment (sections list; "clatters" → "spins"; knob section says `spins = 0, stagger = 0.8`); bigsign section 9 texts "9 KNOBS" / "ONE TURN". Run `uv run led-ticker validate <file>` on each from the worktree root (plugins resolve via the workspace) → no errors.

- [ ] **Step 4: Commit**

```bash
git add plugins/flair/README.md plugins/flair/CLAUDE.md plugins/flair/pyproject.toml plugins/flair/examples/config.slots-smoke.bigsign.toml plugins/flair/examples/config.slots-smoke.smallsign.toml
git commit -m "docs(flair): slots README, invariants, smoke configs

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: Visual gate, then open PR 2

**Files:**
- Read: the smoke configs from Task 6; `tools/render_demo` in `../led-ticker` (render via `uv run --project ../led-ticker-plugins`, per James's render notes); constants in `slots_paint.py` / `slots.py` if tuning is needed.

- [ ] **Step 1: Render** — invoke the `making-a-gif` skill for each smoke config (bigsign copy and smallsign) to get the `--duration` and the exact `make render-demo` command; write GIFs to the scratchpad directory; view them with Read.

- [ ] **Step 2: Judge against the spec's anti-goals** — reels (not a wipe/push, not flicker); decelerate + visible settle; no brightness pop; no blank frame; ring static. Adjust only the named constants, re-run Tasks 3–5 tests (update expected values where a constant changed), re-render.

- [ ] **Step 3: Show James** both GIFs (paths in full) and ask the two gate questions from the spec: does the smallsign read, and should the default `stagger` be higher than 0.5. Apply the answer (README default + `Slots.__init__` default + tests) if it changes.

- [ ] **Step 4: Final checks + push**

Run: `make lint && make test` from the worktree root → clean; `git push -u origin feat/flair-slots`.

- [ ] **Step 5: PR body file, then ASK James before `gh pr create`**

Body: one paragraph on the effect, the knob table summary, "stacked on #<PR 1>", the two GIFs attached (James attaches or I upload via the GIF path he chooses), link to the spec, and the attribution line `🤖 Generated with [Claude Code](https://claude.com/claude-code)`. Title: `feat(flair): flair.slots slot-machine reel transition`. Stop and ask before creating.

- [ ] **Step 6: Follow-ups to list in the PR body, not to do here** — core docs site (`transitions/sprite.mdx` entry + pinned GIF, `transitions/index.mdx` catalogue line, `sprite.mdx` description, `plugins/available.mdx` family list) after the flair release; flair release via the `publishing-a-plugin` skill when James asks.
