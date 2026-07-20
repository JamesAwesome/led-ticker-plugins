# flair.lightning Transition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `flair.lightning` transition — a zigzag bolt strikes across the outgoing widget, then the crack pulls apart revealing the incoming widget underneath.

**Architecture:** Single new module `lightning.py` in the flair package: a pure planning function (`plan_bolt` → per-column crack y) plus a `Lightning` class with poker's phase shape (strike t<0.45 over outgoing; peel = `snap_reset` + full `incoming.draw` + complement blackout + glowing edges; snap ≥0.95). Everything per-frame is a pure function of `t` — no caches, no memos, no warm threads (poker-arc perf contract). Paints at physical resolution via `unwrap_to_real`.

**Tech Stack:** Python 3.12+, led-ticker plugin API (`led_ticker.plugin`: `SNAP_THRESHOLD`, `is_scaled`, `snap_reset`, `unwrap_to_real`), pytest. Repo `led-ticker-plugins`, checkout `/Users/james/projects/github/jamesawesome/led-ticker-plugins-flight`, branch `flair-lightning`.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-19-flair-lightning-transition-design.md` — including its **mandatory Performance verification section** (frame-time sweep + refire, fresh-process first firing, committed work-count tripwire).
- Work ONLY on branch `flair-lightning`; run `git branch --show-current` first, abort otherwise.
- No new runtime dependencies; no `from __future__ import annotations` (PEP 649 rule).
- Perf contract: no caches/memos/warm threads; per-firing state is the bolt polyline only.
- Constants (exact values): `_CUTOVER = 0.45`, `_OPEN_END = 0.9`, vertex pitch 6–10 LOGICAL px, y band = center third (h/2 ± h/6), head color `(255, 255, 255)`, default trail `(150, 190, 255)`, flicker brightness floor `0.72`, thickness `max(1, scale // 2)`, `min_frames = 24`.
- Knobs: `seed` (int, optional), `color` ([r,g,b] 0–255 ints, optional). Nothing else.
- Lint gates from `plugins/flair/`: `uv run --extra dev ruff check src/ tests/`, `uv run --extra dev ruff format --check src/ tests/`, `PYRIGHT_PYTHON_FORCE_VERSION=latest uv run --extra dev pyright src/`.
- Task 4 ends at a HARD STOP: James reviews the visual-gate GIFs before Task 5.
- The eventual PR body carries a "Test on the sign" section (branch-ref requirements-plugins.txt line + `down -v` note) and the benchmark numbers.

All `pytest`/`ruff` commands run from `/Users/james/projects/github/jamesawesome/led-ticker-plugins-flight/plugins/flair/`.

---

### Task 1: `plan_bolt` — the pure planning half

**Files:**
- Create: `plugins/flair/src/led_ticker_flair/flair/lightning.py`
- Test: `plugins/flair/tests/test_flair_lightning_plan.py`

**Interfaces:**
- Consumes: nothing outside stdlib (`random`, `math`) + `led_ticker.plugin` imports staged for Task 2.
- Produces: `plan_bolt(w: int, h: int, scale: int, rng: random.Random) -> list[int]` — per-REAL-column crack y; module constants named in Global Constraints. Task 2's `Lightning` calls `plan_bolt` and reads `_CUTOVER`, `_OPEN_END`, `_HEAD_COLOR`, `_TRAIL_COLOR`, `_FLICKER_LO`.

- [ ] **Step 1: Write the failing tests**

Create `plugins/flair/tests/test_flair_lightning_plan.py`:

```python
import random

from led_ticker_flair.flair.lightning import plan_bolt

BIG = (256, 64, 4)
SMALL = (160, 16, 1)


class TestPlanBolt:
    def test_deterministic_per_seed(self):
        a = plan_bolt(*BIG, random.Random(4))
        b = plan_bolt(*BIG, random.Random(4))
        assert a == b

    def test_covers_every_column(self):
        for w, h, s in (BIG, SMALL):
            crack = plan_bolt(w, h, s, random.Random(1))
            assert len(crack) == w

    def test_y_confined_to_center_third(self):
        for w, h, s in (BIG, SMALL):
            for seed in range(10):
                crack = plan_bolt(w, h, s, random.Random(seed))
                lo, hi = h / 2 - h / 6 - 1, h / 2 + h / 6 + 1  # ±1 rounding slack
                assert all(lo <= y <= hi for y in crack), (w, h, seed)

    def test_zigzags_direction_alternates(self):
        # A true zigzag crosses the panel midline repeatedly: count sign
        # changes of (y - h/2) at the planned vertices via the column walk —
        # at least 3 crossings on a bigsign-width bolt.
        w, h, s = BIG
        crack = plan_bolt(w, h, s, random.Random(2))
        mid = h / 2
        signs = [1 if y > mid else -1 for y in crack if y != mid]
        crossings = sum(1 for a, b in zip(signs, signs[1:], strict=False) if a != b)
        assert crossings >= 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --extra dev pytest tests/test_flair_lightning_plan.py -q`
Expected: FAIL/ERROR with `ModuleNotFoundError`/`ImportError` (module doesn't exist)

- [ ] **Step 3: Implement `plan_bolt`**

Create `plugins/flair/src/led_ticker_flair/flair/lightning.py`:

```python
"""flair.lightning — a zigzag bolt strikes across the outgoing widget, then
the crack pulls apart revealing the incoming widget underneath.

Spec: docs/superpowers/specs/2026-07-19-flair-lightning-transition-design.md
Perf contract (poker-arc lesson): everything per-frame is a pure function of
``t`` — no caches, no memos, no warm threads. The only per-firing state is
the bolt polyline, flattened to one crack-y per real column at plan time.
"""

import math
import random
from typing import Any

from led_ticker.plugin import SNAP_THRESHOLD, is_scaled, snap_reset, unwrap_to_real

_CUTOVER = 0.45  # strike ends / peel begins
_OPEN_END = 0.9  # fraction of the peel phase over which the gap fully opens
_SEG_MIN_LOGICAL = 6  # zigzag vertex pitch bounds, LOGICAL px
_SEG_MAX_LOGICAL = 10
_HEAD_COLOR = (255, 255, 255)
_TRAIL_COLOR = (150, 190, 255)  # electric blue-white default
_FLICKER_LO = 0.72  # per-frame trail brightness floor
_HEAD_W_LOGICAL = 2  # head cluster half-width, LOGICAL px


def plan_bolt(w: int, h: int, scale: int, rng: random.Random) -> list[int]:
    """Per-REAL-column crack y for a fresh bolt.

    Random-walk zigzag: a vertex every _SEG_MIN.._SEG_MAX logical px with
    strictly alternating vertical direction, y confined to the center third
    of the panel (h/2 ± h/6). Piecewise-linear between vertices."""
    band_half = h / 6.0
    cy = h / 2.0
    xs = [0]
    while xs[-1] < w - 1:
        step = rng.randint(_SEG_MIN_LOGICAL, _SEG_MAX_LOGICAL) * scale
        xs.append(min(w - 1, xs[-1] + step))
    if len(xs) < 2:  # degenerate 1px-wide panel
        xs.append(w - 1)
    sign = rng.choice((-1, 1))
    ys = []
    for _ in xs:
        ys.append(cy + sign * rng.uniform(0.35, 1.0) * band_half)
        sign = -sign
    crack = [0] * w
    seg = 0
    for x in range(w):
        while x > xs[seg + 1]:
            seg += 1
        x0, x1 = xs[seg], xs[seg + 1]
        y0, y1 = ys[seg], ys[seg + 1]
        f = 0.0 if x1 == x0 else (x - x0) / (x1 - x0)
        crack[x] = int(round(y0 + (y1 - y0) * f))
    return crack
```

(The `led_ticker.plugin` import and `math`/`Any` are used by Task 2's class in this same module; if ruff flags them as unused at THIS commit, add `math`/`Any`/plugin imports in Task 2 instead.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --extra dev pytest tests/test_flair_lightning_plan.py -q`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add plugins/flair/src/led_ticker_flair/flair/lightning.py plugins/flair/tests/test_flair_lightning_plan.py
git commit -m "feat(lightning): plan_bolt zigzag planner (pure half)"
```

---

### Task 2: `Lightning` class — strike, peel, snap, refire

**Files:**
- Modify: `plugins/flair/src/led_ticker_flair/flair/lightning.py`
- Test: `plugins/flair/tests/test_flair_lightning_transition.py` (new)

**Interfaces:**
- Consumes: `plan_bolt`, constants from Task 1.
- Produces: `Lightning(color: Any = None, seed: Any = None)` with `min_frames = 24` and `frame_at(t, canvas, outgoing, incoming, **kwargs) -> canvas` honoring `outgoing_scroll_pos` + `incoming_bg_color`; internals `_crack: list[int]`, `_last_t: float`, `_gap_d(t) -> float` (Task 3's perf test and Task 4's benchmark rely on the public shape only).

- [ ] **Step 1: Write the failing tests**

Create `plugins/flair/tests/test_flair_lightning_transition.py` (stub canvas / widget copied per this repo's per-file-duplication convention):

```python
"""flair.lightning — the ``Lightning`` strike-and-peel transition class.

Stub canvas / widget fixtures copied from test_flair_poker_transition.py
(the per-file duplication is this repo's convention).
"""

from typing import Any
from unittest import mock

import pytest
from led_ticker.plugin import ScaledCanvas

from led_ticker_flair import flair as flair_pkg
from led_ticker_flair.flair.lightning import Lightning


class _StubCanvas:
    """Minimal scale=1 real-canvas stub."""

    def __init__(self, width: int = 160, height: int = 16) -> None:
        self.width = width
        self.height = height
        self._pixels: dict[tuple[int, int], tuple[int, int, int]] = {}
        self.calls: list[tuple[int, int, int, int, int]] = []

    def SetPixel(self, x: int, y: int, r: int, g: int, b: int) -> None:  # noqa: N802
        self._pixels[(x, y)] = (r, g, b)
        self.calls.append((x, y, r, g, b))

    def SubFill(  # noqa: N802
        self, x: int, y: int, w: int, h: int, r: int, g: int, b: int
    ) -> None:
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                self.SetPixel(xx, yy, r, g, b)

    def Clear(self) -> None:  # noqa: N802
        self._pixels.clear()

    def Fill(self, r: int, g: int, b: int) -> None:  # noqa: N802
        for y in range(self.height):
            for x in range(self.width):
                self.SetPixel(x, y, r, g, b)


def _make_widget(draw_pixel: bool = True, fill: Any = None) -> Any:
    widget = mock.Mock()
    widget.hold_time = 0.0

    def _draw(canvas: Any, cursor_pos: int = 0, **kw: Any) -> tuple[Any, int]:
        if fill is not None:
            canvas.Fill(*fill)
        if draw_pixel:
            canvas.SetPixel(0, 0, 255, 0, 0)
        return (canvas, cursor_pos)

    widget.draw.side_effect = _draw
    return widget


class TestKnobValidation:
    def test_bad_seed_rejected(self):
        for bad in ("7", 1.5, True):
            with pytest.raises(ValueError, match="seed"):
                Lightning(seed=bad)

    def test_bad_color_rejected(self):
        for bad in ([255, 0], [255, 0, "x"], [300, 0, 0], "red", [True, 0, 0]):
            with pytest.raises(ValueError, match="color"):
                Lightning(color=bad)

    def test_valid_knobs(self):
        assert Lightning().trail_color == (150, 190, 255)
        assert Lightning(color=[255, 92, 38]).trail_color == (255, 92, 38)
        Lightning(seed=7)  # no raise


class TestEndpoints:
    def test_t_zero_draws_outgoing_only(self) -> None:
        p = Lightning(seed=1)
        canvas = _StubCanvas()
        outgoing = _make_widget(draw_pixel=False)
        incoming = _make_widget(draw_pixel=False)

        result = p.frame_at(0.0, canvas, outgoing, incoming)

        outgoing.draw.assert_called_once()
        incoming.draw.assert_not_called()
        assert canvas._pixels == {}  # no bolt paint at t=0
        assert result is canvas

    def test_snap_draws_incoming_on_bg(self) -> None:
        p = Lightning(seed=1)
        canvas = _StubCanvas()
        outgoing = _make_widget(draw_pixel=False)
        incoming = _make_widget(draw_pixel=True)

        result = p.frame_at(
            0.96, canvas, outgoing, incoming, incoming_bg_color=(9, 9, 9)
        )

        outgoing.draw.assert_not_called()
        incoming.draw.assert_called_once_with(canvas, cursor_pos=0)
        assert canvas._pixels[(0, 0)] == (255, 0, 0)
        assert canvas._pixels[(5, 5)] == (9, 9, 9)
        assert result is canvas

    def test_no_outgoing_paint_after_cutover(self) -> None:
        p = Lightning(seed=2)
        canvas = _StubCanvas()
        outgoing = _make_widget(draw_pixel=False)
        incoming = _make_widget(draw_pixel=False)

        p.frame_at(0.6, canvas, outgoing, incoming)

        outgoing.draw.assert_not_called()
        incoming.draw.assert_called_once_with(canvas, cursor_pos=0)

    def test_strike_paints_bolt_over_outgoing(self) -> None:
        p = Lightning(seed=3)
        canvas = _StubCanvas()
        o = _make_widget(draw_pixel=False)
        i = _make_widget(draw_pixel=False)
        p.frame_at(0.3, canvas, o, i)
        o.draw.assert_called_once()
        i.draw.assert_not_called()
        assert canvas._pixels  # bolt pixels present
        # head is white-hot somewhere
        assert (255, 255, 255) in canvas._pixels.values()


class TestFullReveal:
    """At t just below SNAP the gap must cover the whole panel: the incoming
    fills (7, 7, 7), so any black pixel is a reveal gap. Deterministic — the
    gap bound is a pure function of t (no frame sweep needed)."""

    @pytest.mark.parametrize("seed", range(8))
    @pytest.mark.parametrize(
        ("width", "height", "scale"), [(160, 16, 1), (256, 64, 4)]
    )
    def test_full_reveal_before_snap(self, width, height, scale, seed) -> None:
        real = _StubCanvas(width=width, height=height)
        canvas = (
            ScaledCanvas(real, scale=scale, content_height=16)
            if scale > 1
            else real
        )
        p = Lightning(seed=seed)
        o = _make_widget(draw_pixel=False)
        i = _make_widget(draw_pixel=False, fill=(7, 7, 7))
        p.frame_at(0.94, canvas, o, i)
        black = [
            (x, y)
            for y in range(height)
            for x in range(width)
            if real._pixels.get((x, y), (0, 0, 0)) == (0, 0, 0)
        ]
        assert not black, f"{len(black)} unrevealed px, first: {black[:5]}"


class TestRefire:
    def test_seedless_refire_replans(self) -> None:
        p = Lightning()  # seed=None
        canvas = _StubCanvas()
        o = _make_widget(draw_pixel=False)
        i = _make_widget(draw_pixel=False)
        for t in (0.3, 0.6, 0.96):
            p.frame_at(t, canvas, o, i)
        first = p._crack
        assert first
        p.frame_at(0.05, canvas, o, i)  # t regressed -> new firing
        assert p._crack is not first

    def test_seeded_refire_keeps_plan(self) -> None:
        p = Lightning(seed=9)
        canvas = _StubCanvas()
        o = _make_widget(draw_pixel=False)
        i = _make_widget(draw_pixel=False)
        p.frame_at(0.3, canvas, o, i)
        first = p._crack
        p.frame_at(0.96, canvas, o, i)
        p.frame_at(0.05, canvas, o, i)
        assert p._crack is first


class TestPhysicalResolution:
    def test_bolt_paints_real_canvas_thin(self) -> None:
        """Through a ScaledCanvas the bolt must land on the REAL canvas at
        ~2px thickness (max(1, scale//2)) — a wrapper-drawn bolt would
        block-expand to >= scale (4) rows per column."""
        real = _StubCanvas(width=256, height=64)
        canvas = ScaledCanvas(real, scale=4, content_height=16)
        p = Lightning(seed=5)
        o = _make_widget(draw_pixel=False)
        i = _make_widget(draw_pixel=False)
        p.frame_at(0.4, canvas, o, i)
        assert real._pixels
        # column 5 is deep in the trail at t=0.4 (head ~89% across): trail
        # thickness is 2 real px there, never a 4px block.
        rows = [y for (x, y) in real._pixels if x == 5]
        assert rows
        assert len(rows) <= 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --extra dev pytest tests/test_flair_lightning_transition.py -q`
Expected: FAIL/ERROR — `ImportError: cannot import name 'Lightning'`

- [ ] **Step 3: Implement the `Lightning` class**

Append to `plugins/flair/src/led_ticker_flair/flair/lightning.py`:

```python
class Lightning:
    """Zigzag bolt strike + crack-open reveal.

    Strike (t < _CUTOVER): outgoing draws normally; the bolt draws itself
    left->right with a white-hot head and a flickering blue-white trail.
    Peel (t >= _CUTOVER): the outgoing cuts out; each frame draws the
    incoming in full, blacks out everything outside the opened gap
    (crack +/- d(t)), and paints glowing crack edges at the boundary.
    Knobs: ``seed`` pins the bolt (default None = fresh bolt every firing,
    detected via t regressing); ``color`` tints the trail."""

    min_frames = 24

    def __init__(self, color: Any = None, seed: Any = None) -> None:
        if seed is not None and (isinstance(seed, bool) or not isinstance(seed, int)):
            raise ValueError(f"seed must be an int; got {seed!r}")
        if color is not None and (
            not isinstance(color, (list, tuple))
            or len(color) != 3
            or not all(
                isinstance(c, int) and not isinstance(c, bool) and 0 <= c <= 255
                for c in color
            )
        ):
            raise ValueError(f"color must be [r, g, b] 0-255 ints; got {color!r}")
        self.seed = seed
        self.trail_color: tuple[int, int, int] = (
            (color[0], color[1], color[2]) if color is not None else _TRAIL_COLOR
        )
        self._rng = random.Random(seed) if seed is not None else random.Random()
        self._crack: list[int] = []  # empty == needs (re)plan
        self._plan_key: tuple[int, int, int] | None = None
        self._dims: tuple[int, int] = (0, 0)
        self._scale = 1
        self._thickness = 1
        self._d_need = 0.0
        self._flicker_seed = 0
        self._last_t = 1.0

    def _ensure_plan(self, canvas):
        # `real` is re-derived on EVERY call and never cached on self:
        # frame.swap() hands back a different back-buffer each tick
        # (constraint #1). Only geometry-derived data is retained.
        scale = canvas.scale if is_scaled(canvas) else 1
        real = unwrap_to_real(canvas) if is_scaled(canvas) else canvas
        key = (real.width, real.height, scale)
        if not self._crack or self._plan_key != key:
            self._crack = plan_bolt(real.width, real.height, scale, self._rng)
            self._plan_key = key
            self._dims = (real.width, real.height)
            self._scale = scale
            self._thickness = max(1, scale // 2)
            h = real.height
            # Smallest half-gap that reveals every pixel in every column,
            # plus edge thickness so the glowing edges are off-panel too.
            self._d_need = (
                max(max(cy, h - cy) for cy in self._crack) + self._thickness + 1
            )
            self._flicker_seed = self._rng.randrange(1 << 30)
        return real

    def _flicker(self, t: float) -> tuple[int, int, int]:
        """Deterministic per-frame trail brightness (no wall clock, no
        global random): keyed on the firing's flicker seed + quantized t."""
        r = random.Random((self._flicker_seed, round(t * 997)))
        b = _FLICKER_LO + (1.0 - _FLICKER_LO) * r.random()
        tr, tg, tb = self.trail_color
        return (int(tr * b), int(tg * b), int(tb * b))

    def _paint_bolt(self, real, t):
        w, h = self._dims
        crack = self._crack
        thk = self._thickness
        set_pixel = real.SetPixel
        s = min(1.0, t / _CUTOVER)
        head_x = int(round(s * (w - 1)))
        col = self._flicker(t)
        for x in range(0, head_x + 1):
            y0 = crack[x] - (thk - 1) // 2
            for y in range(y0, y0 + thk):
                if 0 <= y < h:
                    set_pixel(x, y, *col)
        hw = max(1, _HEAD_W_LOGICAL * self._scale)
        for x in range(max(0, head_x - hw), min(w, head_x + hw + 1)):
            y0 = crack[x] - (thk - 1) // 2
            for y in range(y0 - 1, y0 + thk + 1):
                if 0 <= y < h:
                    set_pixel(x, y, *_HEAD_COLOR)

    def _gap_d(self, t: float) -> float:
        """Half-height of the open gap at t: smoothstep from 0 at cutover to
        _d_need at _OPEN_END of the peel phase (fully open well before SNAP,
        guaranteeing deterministic full reveal)."""
        p = (t - _CUTOVER) / (SNAP_THRESHOLD - _CUTOVER)
        p = min(1.0, max(0.0, p / _OPEN_END))
        ease = p * p * (3.0 - 2.0 * p)
        return ease * self._d_need

    def _paint_peel(self, real, t):
        w, h = self._dims
        crack = self._crack
        thk = self._thickness
        d = self._gap_d(t)
        set_pixel = real.SetPixel
        col = self._flicker(t)
        for x in range(w):
            lo = crack[x] - d  # gap: lo < y < hi
            hi = crack[x] + d
            top_black_end = min(h, max(0, math.ceil(lo)))  # [0, end) black
            bot_black_start = max(0, math.floor(hi) + 1)  # [start, h) black
            for y in range(0, top_black_end):
                set_pixel(x, y, 0, 0, 0)
            for y in range(bot_black_start, h):
                set_pixel(x, y, 0, 0, 0)
            # glowing crack edges over the innermost black rows
            for y in range(max(0, top_black_end - thk), top_black_end):
                set_pixel(x, y, *col)
            for y in range(bot_black_start, min(h, bot_black_start + thk)):
                set_pixel(x, y, *col)

    def frame_at(self, t, canvas, outgoing, incoming, **kwargs):
        if t <= 0.0:
            outgoing.draw(canvas, cursor_pos=kwargs.get("outgoing_scroll_pos", 0))
            return canvas
        if t >= SNAP_THRESHOLD:
            snap_reset(canvas, kwargs.get("incoming_bg_color"))
            incoming.draw(canvas, cursor_pos=0)
            self._last_t = 1.0
            return canvas

        refired = t < self._last_t
        if refired and self.seed is None:
            self._crack = []  # re-fire from fresh entropy (empty == replan)
            self._plan_key = None
            self._rng = random.Random()
        self._last_t = t

        real = self._ensure_plan(canvas)

        if t < _CUTOVER:
            outgoing.draw(canvas, cursor_pos=kwargs.get("outgoing_scroll_pos", 0))
            self._paint_bolt(real, t)
        else:
            snap_reset(canvas, kwargs.get("incoming_bg_color"))
            incoming.draw(canvas, cursor_pos=0)
            self._paint_peel(real, t)
        return canvas
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --extra dev pytest tests/test_flair_lightning_transition.py tests/test_flair_lightning_plan.py -q`
Expected: all pass (30 tests: 4 plan + 26 transition — FullReveal is 16 parametrized cases)

- [ ] **Step 5: Commit**

```bash
git add plugins/flair/src/led_ticker_flair/flair/lightning.py plugins/flair/tests/test_flair_lightning_transition.py
git commit -m "feat(lightning): Lightning strike-and-peel transition class"
```

---

### Task 3: Registration + perf-uniformity tripwire + gates

**Files:**
- Modify: `plugins/flair/src/led_ticker_flair/flair/__init__.py:46-62` (`register`)
- Test: `plugins/flair/tests/test_flair_lightning_transition.py` (append)

**Interfaces:**
- Consumes: `Lightning` from Task 2.
- Produces: config type `transition = "flair.lightning"`.

- [ ] **Step 1: Write the failing tests**

Append to `plugins/flair/tests/test_flair_lightning_transition.py`:

```python
class _RecordingAPI:
    """Minimal PluginAPI stand-in recording registrations."""

    def __init__(self) -> None:
        self.animations: dict[str, type] = {}
        self.transitions: dict[str, type] = {}
        self.widgets: dict[str, type] = {}

    def animation(self, name):
        def _dec(cls):
            self.animations[name] = cls
            return cls

        return _dec

    def transition(self, name):
        def _dec(cls):
            self.transitions[name] = cls
            return cls

        return _dec

    def widget(self, name):
        def _dec(cls):
            self.widgets[name] = cls
            return cls

        return _dec


class TestRegistration:
    def test_lightning_registered(self) -> None:
        api = _RecordingAPI()
        flair_pkg.register(api)
        assert api.transitions["lightning"] is Lightning


class TestPerfUniformity:
    """Spec's committed CI-safe perf gate: count WORK per frame, not time.
    A poker-style deferred-backlog bug (one frame paying accumulated state)
    fails the absolute bound deterministically."""

    def test_per_frame_paint_volume_bounded(self) -> None:
        canvas = _StubCanvas(width=160, height=16)
        o = _make_widget(draw_pixel=False)
        i = _make_widget(draw_pixel=False)
        p = Lightning(seed=4)
        counts = []
        t = 0.02
        while t < 1.0:
            before = len(canvas.calls)
            p.frame_at(round(t, 3), canvas, o, i)
            counts.append((round(t, 2), len(canvas.calls) - before))
            t += 0.02
        panel = 160 * 16
        worst_t, worst = max(counts, key=lambda c: c[1])
        assert worst <= int(1.5 * panel), (
            f"frame at t={worst_t} painted {worst} px (> 1.5x panel {panel}) — "
            "per-frame work must stay bounded by panel size"
        )

    def test_refire_frames_equally_bounded(self) -> None:
        # Poker's root cause only showed on RE-fires (seed=None replans).
        canvas = _StubCanvas(width=160, height=16)
        o = _make_widget(draw_pixel=False)
        i = _make_widget(draw_pixel=False)
        p = Lightning()  # seed=None
        for t in (0.3, 0.6, 0.96):
            p.frame_at(t, canvas, o, i)
        panel = 160 * 16
        t = 0.02
        while t < 1.0:
            before = len(canvas.calls)
            p.frame_at(round(t, 3), canvas, o, i)
            assert len(canvas.calls) - before <= int(1.5 * panel)
            t += 0.02
```

- [ ] **Step 2: Run tests to verify the registration test fails**

Run: `uv run --extra dev pytest tests/test_flair_lightning_transition.py -q -k "Registration or PerfUniformity"`
Expected: `test_lightning_registered` FAILS with `KeyError: 'lightning'`; the perf tests may already pass (that's fine — they're tripwires, not feature tests).

- [ ] **Step 3: Register the transition**

In `plugins/flair/src/led_ticker_flair/flair/__init__.py`, inside `register(api)` add the import (alphabetical among the existing ones) and registration:

```python
    from led_ticker_flair.flair.lightning import Lightning  # noqa: PLC0415
```

and after `api.transition("poker")(Poker)`:

```python
    api.transition("lightning")(Lightning)
```

- [ ] **Step 4: Run the full flair suite + lint gates**

Run: `uv run --extra dev pytest tests/ -q`
Expected: all pass (existing suite + 33 new lightning tests)

Run: `uv run --extra dev ruff check src/ tests/ && uv run --extra dev ruff format --check src/ tests/ && PYRIGHT_PYTHON_FORCE_VERSION=latest uv run --extra dev pyright src/`
Expected: all clean

- [ ] **Step 5: Commit**

```bash
git add plugins/flair/src/led_ticker_flair/flair/__init__.py plugins/flair/tests/test_flair_lightning_transition.py
git commit -m "feat(lightning): register flair.lightning + perf-uniformity tripwires"
```

---

### Task 4: Benchmarks + visual gate (HARD STOP for James)

**Files:**
- Create (scratch, not committed): `$CLAUDE_JOB_DIR/tmp/lightning_frametime.py`, `$CLAUDE_JOB_DIR/tmp/lightning-gate-smallsign.toml`, `$CLAUDE_JOB_DIR/tmp/lightning-gate-bigsign.toml`

**Interfaces:**
- Consumes: the complete `flair.lightning` from Tasks 1–3.
- Produces: benchmark numbers for the PR body; two GIFs for James's review.

- [ ] **Step 1: Frame-time sweep (spec perf gate 1)**

Write `$CLAUDE_JOB_DIR/tmp/lightning_frametime.py`:

```python
import time
from unittest import mock

from led_ticker.plugin import ScaledCanvas
from led_ticker_flair.flair.lightning import Lightning


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


def sweep(p, canvas, o, i, label):
    times = []
    t = 0.02
    while t < 1.0:
        t0 = time.perf_counter()
        p.frame_at(round(t, 4), canvas, o, i)
        times.append((round(t, 2), (time.perf_counter() - t0) * 1000))
        t += 0.02
    ordered = sorted(times, key=lambda x: -x[1])
    avg = sum(ms for _, ms in times) / len(times)
    print(f"{label}: avg {avg:.2f}ms  worst {ordered[0][1]:.2f}ms @ t={ordered[0][0]}")
    print(f"  top5: {[(t, round(ms, 2)) for t, ms in ordered[:5]]}")
    return avg, ordered[0][1]


canvas = ScaledCanvas(Stub(256, 64), scale=4, content_height=16)
o, i = widget(), widget()
p = Lightning()  # seed=None: the smoke-config shape
avg1, worst1 = sweep(p, canvas, o, i, "firing 1 (fresh instance)")
avg2, worst2 = sweep(p, canvas, o, i, "firing 2 (seedless REFIRE)")
assert worst1 <= 5 * avg1 and worst2 <= 5 * avg2, "spike gate FAILED"
print("spike gate OK (worst <= 5x avg, both firings)")
```

Run from `plugins/flair/`: `uv run --extra dev python $CLAUDE_JOB_DIR/tmp/lightning_frametime.py`
Expected: both firings ms-class, `spike gate OK`. Record the numbers for the PR body.

- [ ] **Step 2: Fresh-process construction + first-frame check (spec perf gate 2)**

Run from `plugins/flair/`:

```bash
uv run --extra dev python -c "
import time
from unittest import mock
from led_ticker.plugin import ScaledCanvas
from led_ticker_flair.flair.lightning import Lightning
class Stub:
    def __init__(s, w, h): s.width, s.height = w, h
    def SetPixel(s, *a): pass
    def Clear(s): pass
    def Fill(s, *a): pass
w = mock.Mock(); w.draw.side_effect = lambda c, cursor_pos=0, **k: (c, cursor_pos)
t0 = time.perf_counter(); p = Lightning(seed=7)
print(f'construction: {(time.perf_counter()-t0)*1000:.2f}ms')
canvas = ScaledCanvas(Stub(256, 64), scale=4, content_height=16)
t0 = time.perf_counter(); p.frame_at(0.3, canvas, w, w)
print(f'first-ever frame: {(time.perf_counter()-t0)*1000:.2f}ms')
"
```

Expected: both < 10ms. Record for the PR body.

- [ ] **Step 3: Render visual-gate GIFs**

The core repo's demo renderer needs the local flair build installed. From the CORE repo (`/Users/james/projects/github/jamesawesome/led-ticker`):

```bash
uv pip install -e /Users/james/projects/github/jamesawesome/led-ticker-plugins-flight/plugins/flair
```

Write two gate configs. `$CLAUDE_JOB_DIR/tmp/lightning-gate-smallsign.toml`:

```toml
# render-duration: 14
[display]
rows = 16
cols = 32
chain = 5
default_scale = 1
brightness = 60

[title]
delay = 0

[transitions]
default = "flair.lightning"
duration = 2.5
between_sections = "flair.lightning"

[[playlist.section]]
mode = "slideshow"
hold_time = 2
loop_count = 0

[[playlist.section.widget]]
type = "message"
text = "OLD WIDGET TEXT"
font_color = [255, 183, 3]

[[playlist.section.widget]]
type = "message"
text = "NEW WIDGET TEXT"
font_color = [80, 220, 120]
```

`$CLAUDE_JOB_DIR/tmp/lightning-gate-bigsign.toml`: same playlist but

```toml
# render-duration: 14
[display]
rows = 32
cols = 64
chain = 8
default_scale = 4
brightness = 60
pixel_mapper_config = ""
```

(If the renderer rejects the bigsign display block, copy the `[display]` block verbatim from `docs/site/demos-pinned/` bigsign demos in the core repo and keep the playlist.)

Render both:

```bash
uv run python tools/render_demo/render.py $CLAUDE_JOB_DIR/tmp/lightning-gate-smallsign.toml -o $CLAUDE_JOB_DIR/tmp/lightning-smallsign.gif --duration 14
uv run python tools/render_demo/render.py $CLAUDE_JOB_DIR/tmp/lightning-gate-bigsign.toml -o $CLAUDE_JOB_DIR/tmp/lightning-bigsign.gif --duration 14
```

- [ ] **Step 4: HARD STOP — send both GIFs to James**

Send the two GIFs with the benchmark numbers. Ask specifically about: bolt jaggedness (segment pitch), flicker intensity, head size, open easing, trail color. DO NOT proceed to Task 5 until James approves the look. Iterate constants in `lightning.py` + re-render as directed (each iteration: re-run the full lightning test files + re-render).

---

### Task 5 (post-gate): Smoke config, README, PR

**Files:**
- Create: `plugins/flair/examples/config.lightning-smoke.bigsign.toml`
- Modify: `plugins/flair/README.md` (transitions section — follow the poker/stickers entry format found there)

**Interfaces:**
- Consumes: gate-approved `flair.lightning`.
- Produces: the PR.

- [ ] **Step 1: Write the bigsign smoke config**

Create `plugins/flair/examples/config.lightning-smoke.bigsign.toml` following `config.poker-smoke.bigsign.toml`'s exact conventions (header comment block: `# requires-plugins: led-ticker-flair`, prereqs, preflight validate note, WHAT TO LOOK FOR list). Sections to include (mode = "slideshow", hold_time = 1.5, loop_count = 0, two message widgets each, `[display]` block copied from `config.poker-smoke.bigsign.toml`):

1. DEFAULT — `transition = "flair.lightning"`: fresh bolt shape every firing; strike L→R, crack opens, incoming revealed inside the gap against black.
2. SEEDED — `transition = {type = "flair.lightning", seed = 99}`: identical bolt every firing.
3. TINTED — `transition = {type = "flair.lightning", color = [255, 92, 38]}`: flame-orange trail, head stays white.
4. BG HOLD — incoming widget carries `bg_color`; the gap must show the bg color immediately, clean snap, no black flash.
5. PERF FEEL — note text: motion stays smooth through strike AND open; no hitch at the crack-open moment; first transition after boot as smooth as later ones.

WHAT TO LOOK FOR must state the approved constraint: the peel reveals the incoming AGAINST BLACK outside the gap (design decision, not a bug).

- [ ] **Step 2: Validate the smoke config**

From the CORE repo: `uv run led-ticker validate /Users/james/projects/github/jamesawesome/led-ticker-plugins-flight/plugins/flair/examples/config.lightning-smoke.bigsign.toml`
Expected: no errors (warnings acceptable only if rule-66-class informational).

- [ ] **Step 3: README entry**

Add a `flair.lightning` entry to `plugins/flair/README.md`'s transitions list, matching the poker entry's format: one-paragraph description (strike → crack-open reveal, peel is against black), knob table (`seed`, `color`), config example with the inline-table form.

- [ ] **Step 4: Full suite + lint + commit**

Run from `plugins/flair/`: `uv run --extra dev pytest tests/ -q` and the three lint gates from Global Constraints.

```bash
git add plugins/flair/examples/config.lightning-smoke.bigsign.toml plugins/flair/README.md
git commit -m "docs(lightning): bigsign smoke config + README entry"
git push -u origin flair-lightning
```

- [ ] **Step 5: Open the PR**

`gh pr create` from the branch. Body must include: what/why, the design decisions (peel-against-black, name choice), the benchmark numbers from Task 4 (both firings' avg/worst + fresh-process construction/first-frame), the two gate GIFs (attach or link), the perf-tripwire description, and the **"Test on the sign"** section:

```
## Test on the sign
config/requirements-plugins.txt:
  led-ticker-flair @ git+https://github.com/JamesAwesome/led-ticker-plugins.git@flair-lightning#subdirectory=plugins/flair
then: docker compose down -v && docker compose up -d
Copy plugins/flair/examples/config.lightning-smoke.bigsign.toml to config/config.toml and make restart.
```

Do NOT merge — James merges after hardware validation.
