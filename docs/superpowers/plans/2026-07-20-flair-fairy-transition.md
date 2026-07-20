# flair.fairy Transition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tinkerbell-inspired `flair.fairy.{forward,reverse,alternating}` — a white-hot dot crosses the panel trailing gold pixie dust and a settled line; the line opens to reveal the incoming widget.

**Architecture:** Self-contained `fairy.py` in the flair package: `plan_path` (near-straight per-column path), a `Fairy` core class (flight + open phases; open-phase core deliberately duplicated from lightning per the spec's rule-of-three call), a `FairyReverse` subclass (direction class-attr), and a pacman-convention `FairyAlternating` wrapper delegating to `[Fairy, FairyReverse]` with an index that advances on refire. Sparks are stateless — pure functions of `(column, k, quantized t)` via integer mixing, no particle lists.

**Tech Stack:** Python, `led_ticker.plugin` (`SNAP_THRESHOLD`, `is_scaled`, `snap_reset`, `unwrap_to_real`), pytest. Repo `led-ticker-plugins`, checkout `/Users/james/projects/github/jamesawesome/led-ticker-plugins-flight`, branch `flair-fairy`.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-20-flair-fairy-transition-design.md` (normative for constants + behavior).
- Work ONLY on branch `flair-fairy`; `git branch --show-current` first, abort otherwise.
- No new runtime deps; no `from __future__ import annotations`.
- Perf contract: no caches/memos/warm threads/particle state; per-firing state = the path list + direction/index flags.
- Constants (exact): `_CUTOVER = 0.5`, `_OPEN_END = 0.9`, trail length `0.30` of panel width, spark scatter ±4 logical px, gold `(255, 215, 120)` / cream `(255, 240, 200)` / amber `(230, 170, 60)`, head `(255, 255, 255)`, line thickness `max(1, scale // 2)`, `min_frames = 24`.
- Knobs: `seed` (int) + `color` ([r,g,b] 0–255) ONLY; direction lives in the three registered types.
- Verified facts: `api.transition("fairy.forward")` registers key `flair.fairy.forward` (PluginAPI `_qualify` is a plain join; `get_transition_class` is a dict lookup; `_build_trans_obj` routes any dotted type through the plugin-kwargs path). Alternating convention: copy `PacmanAlternating` (`plugins/flair/src/led_ticker_flair/pacman/pacman.py:349` — `_transitions` list, `_index` advanced when `t < _last_t`, `min_frames` property peeking the NEXT variant, delegate `frame_at`).
- Lint gates from `plugins/flair/`: `uv run --extra dev ruff check src/ tests/`, `uv run --extra dev ruff format --check src/ tests/`, `PYRIGHT_PYTHON_FORCE_VERSION=latest uv run --extra dev pyright src/`.
- Task 4 ends at a HARD STOP (James reviews GIFs); Task 5 opens the PR (no merge without his word; release then = `cut_release.py flair minor` → flair-v0.12.0).
- PR body: "Test on the sign" section (branch-ref line + `down -v` note) + benchmark numbers.
- Rendering demos from the core repo requires `uv pip install -e .../plugins/flair` then `uv run --no-sync` (plain `uv run` re-syncs and uninstalls the editable plugin).

All `pytest`/`ruff` commands run from `/Users/james/projects/github/jamesawesome/led-ticker-plugins-flight/plugins/flair/`.

---

### Task 1: `plan_path` + spark-mix pure half

**Files:**
- Create: `plugins/flair/src/led_ticker_flair/flair/fairy.py`
- Test: `plugins/flair/tests/test_flair_fairy_plan.py`

**Interfaces:**
- Produces: `plan_path(w: int, h: int, scale: int, rng: random.Random) -> list[int]`; `_mix(*parts: int) -> int` (deterministic 32-bit integer mixer used for spark placement/twinkle); module constants per Global Constraints. Task 2 consumes all of these.

- [ ] **Step 1: Write the failing tests**

Create `plugins/flair/tests/test_flair_fairy_plan.py`:

```python
import random

from led_ticker_flair.flair.fairy import _mix, plan_path

BIG = (256, 64, 4)
SMALL = (160, 16, 1)


class TestPlanPath:
    def test_deterministic_per_seed(self):
        a = plan_path(*BIG, random.Random(4))
        b = plan_path(*BIG, random.Random(4))
        assert a == b

    def test_covers_every_column(self):
        for w, h, s in (BIG, SMALL):
            assert len(plan_path(w, h, s, random.Random(1))) == w

    def test_stays_on_panel_and_nearly_straight(self):
        # Near-straight (James's pick): total vertical spread bounded by
        # half the panel; every y safely on-panel.
        for w, h, s in (BIG, SMALL):
            for seed in range(10):
                ys = plan_path(w, h, s, random.Random(seed))
                assert all(0 < y < h - 1 for y in ys), (w, h, seed)
                assert max(ys) - min(ys) <= h / 2, (w, h, seed)

    def test_baseline_in_center_band(self):
        # The MEAN of the path sits in the center third (drift/wobble are
        # small excursions around it).
        for w, h, s in (BIG, SMALL):
            for seed in range(10):
                ys = plan_path(w, h, s, random.Random(seed))
                mean = sum(ys) / len(ys)
                assert h / 2 - h / 6 - 1 <= mean <= h / 2 + h / 6 + 1


class TestMix:
    def test_deterministic_and_spread(self):
        assert _mix(1, 2, 3) == _mix(1, 2, 3)
        vals = {_mix(7, x, 0) & 0xFF for x in range(200)}
        assert len(vals) > 40  # mixes, not constant/degenerate

    def test_order_sensitive(self):
        assert _mix(1, 2) != _mix(2, 1)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --extra dev pytest tests/test_flair_fairy_plan.py -q`
Expected: collection ERROR — `ModuleNotFoundError: No module named 'led_ticker_flair.flair.fairy'`

- [ ] **Step 3: Implement**

Create `plugins/flair/src/led_ticker_flair/flair/fairy.py`:

```python
"""flair.fairy — a fairy (white-hot dot) crosses the panel trailing gold
pixie dust, settling a line that then opens to reveal the incoming widget.
Tinkerbell-inspired. Variants: fairy.forward / fairy.reverse /
fairy.alternating (sprite-family convention).

Spec: docs/superpowers/specs/2026-07-20-flair-fairy-transition-design.md
Perf contract: everything per-frame is a pure function of ``t`` — no caches,
no warm threads, and NO PARTICLE STATE: every spark derives from
_mix(column, k, quantized t). Per-firing state is the path list + flags.
The open-phase gap/blackout core is duplicated from lightning.py on purpose
(rule of three — see the spec's Code shape section)."""

import math
import random
from typing import Any

from led_ticker.plugin import SNAP_THRESHOLD, is_scaled, snap_reset, unwrap_to_real

_CUTOVER = 0.5  # flight ends / open begins (flight is the star)
_OPEN_END = 0.9  # fraction of the open phase over which the gap fully opens
_TRAIL_FRAC = 0.30  # spark trail length, fraction of panel width
_DRIFT_LOGICAL = 4  # max end-to-end path drift, logical px
_WOBBLE_LOGICAL = 1.5  # max sine wobble amplitude, logical px
_SPARK_SPREAD_LOGICAL = 4  # vertical spark scatter around the path
_SPARKS_PER_COL = 3
_GOLD = (255, 215, 120)
_CREAM = (255, 240, 200)
_AMBER = (230, 170, 60)
_HEAD_COLOR = (255, 255, 255)


def _mix(*parts: int) -> int:
    """Deterministic 32-bit mixer (order-sensitive) for stateless sparks."""
    acc = 0x9E3779B9
    for p in parts:
        acc ^= (p & 0xFFFFFFFF) + 0x9E3779B9 + ((acc << 6) & 0xFFFFFFFF) + (acc >> 2)
        acc &= 0xFFFFFFFF
    return acc


def plan_path(w: int, h: int, scale: int, rng: random.Random) -> list[int]:
    """Per-REAL-column path y: nearly straight — baseline in the center
    third, a few logical px of end-to-end drift, small sine wobble.
    Single-valued per column (the reveal machinery requires it)."""
    y0 = h / 2.0 + rng.uniform(-0.8, 0.8) * (h / 6.0)
    drift = rng.uniform(-_DRIFT_LOGICAL, _DRIFT_LOGICAL) * scale
    wob_amp = rng.uniform(0.5, _WOBBLE_LOGICAL) * scale
    wob_freq = rng.uniform(1.5, 3.0) * 2.0 * math.pi / max(1, w)
    wob_phase = rng.uniform(0.0, 2.0 * math.pi)
    span = max(1, w - 1)
    path = []
    for x in range(w):
        y = (
            y0
            + drift * (x / span - 0.5)
            + wob_amp * math.sin(wob_freq * x + wob_phase)
        )
        path.append(max(1, min(h - 2, int(round(y)))))
    return path
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --extra dev pytest tests/test_flair_fairy_plan.py -q`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add plugins/flair/src/led_ticker_flair/flair/fairy.py plugins/flair/tests/test_flair_fairy_plan.py
git commit -m "feat(fairy): plan_path + _mix (pure half)"
```

---

### Task 2: `Fairy` core class + variants

**Files:**
- Modify: `plugins/flair/src/led_ticker_flair/flair/fairy.py`
- Test: `plugins/flair/tests/test_flair_fairy_transition.py` (new)

**Interfaces:**
- Consumes: Task 1's `plan_path`, `_mix`, constants.
- Produces: `Fairy(color: Any = None, seed: Any = None)` (forward, `_direction = 1`), `FairyReverse` (subclass, `_direction = -1`), `FairyAlternating(color, seed)` (pacman-convention wrapper). All expose `min_frames` and `frame_at(t, canvas, outgoing, incoming, **kwargs)`.

- [ ] **Step 1: Write the failing tests**

Create `plugins/flair/tests/test_flair_fairy_transition.py` (stub canvas / widget per the repo's per-file-duplication convention):

```python
"""flair.fairy — Fairy/FairyReverse/FairyAlternating transition classes.

Stub canvas / widget fixtures copied from test_flair_lightning_transition.py
(the per-file duplication is this repo's convention).
"""

from typing import Any
from unittest import mock

import pytest
from led_ticker.plugin import ScaledCanvas

from led_ticker_flair import flair as flair_pkg
from led_ticker_flair.flair.fairy import Fairy, FairyAlternating, FairyReverse


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
                Fairy(seed=bad)

    def test_bad_color_rejected(self):
        for bad in ([255, 0], [255, 0, "x"], [300, 0, 0], "gold", [True, 0, 0]):
            with pytest.raises(ValueError, match="color"):
                Fairy(color=bad)

    def test_valid_knobs_all_variants(self):
        assert Fairy().dust_color == (255, 215, 120)
        assert Fairy(color=[255, 92, 38]).dust_color == (255, 92, 38)
        FairyReverse(seed=7)
        FairyAlternating(color=[1, 2, 3], seed=9)


class TestEndpoints:
    def test_t_zero_draws_outgoing_only(self) -> None:
        p = Fairy(seed=1)
        canvas = _StubCanvas()
        outgoing = _make_widget(draw_pixel=False)
        incoming = _make_widget(draw_pixel=False)
        result = p.frame_at(0.0, canvas, outgoing, incoming)
        outgoing.draw.assert_called_once()
        incoming.draw.assert_not_called()
        assert canvas._pixels == {}
        assert result is canvas

    def test_snap_draws_incoming_on_bg(self) -> None:
        p = Fairy(seed=1)
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
        p = Fairy(seed=2)
        canvas = _StubCanvas()
        outgoing = _make_widget(draw_pixel=False)
        incoming = _make_widget(draw_pixel=False)
        p.frame_at(0.6, canvas, outgoing, incoming)
        outgoing.draw.assert_not_called()
        incoming.draw.assert_called_once_with(canvas, cursor_pos=0)

    def test_flight_paints_head_and_dust_over_outgoing(self) -> None:
        p = Fairy(seed=3)
        canvas = _StubCanvas()
        o = _make_widget(draw_pixel=False)
        i = _make_widget(draw_pixel=False)
        p.frame_at(0.3, canvas, o, i)
        o.draw.assert_called_once()
        i.draw.assert_not_called()
        assert canvas._pixels
        assert (255, 255, 255) in canvas._pixels.values()  # white-hot head


class TestDirections:
    @staticmethod
    def _painted_xs(cls) -> list[int]:
        canvas = _StubCanvas()
        o = _make_widget(draw_pixel=False)
        i = _make_widget(draw_pixel=False)
        p = cls(seed=5)
        p.frame_at(0.15, canvas, o, i)  # early flight: head near start edge
        return [x for (x, _y) in canvas._pixels]

    def test_forward_starts_left(self) -> None:
        xs = self._painted_xs(Fairy)
        assert max(xs) < 160 * 0.6  # everything in the left-ish half early on

    def test_reverse_starts_right(self) -> None:
        xs = self._painted_xs(FairyReverse)
        assert min(xs) > 160 * 0.4

    def test_alternating_flips_each_firing(self) -> None:
        canvas = _StubCanvas()
        o = _make_widget(draw_pixel=False)
        i = _make_widget(draw_pixel=False)
        p = FairyAlternating(seed=6)
        sides = []
        for _ in range(3):
            canvas.Clear()
            canvas.calls.clear()
            p.frame_at(0.15, canvas, o, i)  # firing N begins (t regressed)
            xs = [x for (x, _y) in canvas._pixels]
            sides.append(sum(xs) / len(xs) < 80)  # True = left-side energy
            p.frame_at(0.96, canvas, o, i)  # finish the firing
        assert sides[0] != sides[1]
        assert sides[1] != sides[2]


class TestFullReveal:
    """Just below SNAP the gap must cover the whole panel: incoming fills
    (7, 7, 7); any black pixel is a reveal gap. Deterministic (pure gap
    function of t)."""

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
        p = Fairy(seed=seed)
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
        p = Fairy()
        canvas = _StubCanvas()
        o = _make_widget(draw_pixel=False)
        i = _make_widget(draw_pixel=False)
        for t in (0.3, 0.6, 0.96):
            p.frame_at(t, canvas, o, i)
        first = p._path
        assert first
        p.frame_at(0.05, canvas, o, i)
        assert p._path is not first

    def test_seeded_refire_keeps_plan(self) -> None:
        p = Fairy(seed=9)
        canvas = _StubCanvas()
        o = _make_widget(draw_pixel=False)
        i = _make_widget(draw_pixel=False)
        p.frame_at(0.3, canvas, o, i)
        first = p._path
        p.frame_at(0.96, canvas, o, i)
        p.frame_at(0.05, canvas, o, i)
        assert p._path is first


class TestPhysicalResolution:
    def test_settled_line_is_thin_on_real_canvas(self) -> None:
        """Through a ScaledCanvas the settled line lands on the REAL canvas
        at max(1, scale//2) = 2 px — a wrapper-drawn line would block-expand
        to >= 4 rows per column."""
        real = _StubCanvas(width=256, height=64)
        canvas = ScaledCanvas(real, scale=4, content_height=16)
        p = Fairy(seed=5)
        o = _make_widget(draw_pixel=False)
        i = _make_widget(draw_pixel=False)
        p.frame_at(0.45, canvas, o, i)  # head near far edge, long settled line
        assert real._pixels
        # Column 3 is far behind the head: settled line only (sparks have
        # faded there — trail is 30% of width). <= 3 rows (thickness 2 +
        # rounding), never a 4-px block.
        rows = [y for (x, y) in real._pixels if x == 3]
        assert rows
        assert len(rows) <= 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --extra dev pytest tests/test_flair_fairy_transition.py -q`
Expected: collection ERROR — `ImportError: cannot import name 'Fairy'`

- [ ] **Step 3: Implement the classes**

Append to `plugins/flair/src/led_ticker_flair/flair/fairy.py`:

```python
def _tinted(base: tuple[int, int, int], dust: tuple[int, int, int]) -> tuple[int, int, int]:
    """Rescale a palette color's channels by the dust tint (gold -> tint)."""
    return (
        min(255, int(base[0] * dust[0] / _GOLD[0])),
        min(255, int(base[1] * dust[1] / _GOLD[1])),
        min(255, int(base[2] * dust[2] / _GOLD[2])),
    )


class Fairy:
    """Pixie-dust flight + line-open reveal (forward: flies left->right).

    Flight (t < _CUTOVER): outgoing draws normally; a white-hot head crosses
    the panel scattering stateless gold sparks behind it and settling a thin
    gold line at its path. Open (t >= _CUTOVER): outgoing cuts out; incoming
    draws in full, everything outside the widening gap (path +/- d) is
    blacked out, and the two edges are thin gold lines with twinkling
    sparks. Knobs: ``seed`` (pins path + spark field), ``color`` (dust
    tint). Direction is NOT a knob — use fairy.reverse / fairy.alternating."""

    min_frames = 24
    _direction = 1  # +1: left->right; -1: right->left (FairyReverse)

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
        self.dust_color: tuple[int, int, int] = (
            (color[0], color[1], color[2]) if color is not None else _GOLD
        )
        self._rng = random.Random(seed) if seed is not None else random.Random()
        self._path: list[int] = []  # empty == needs (re)plan
        self._plan_key: tuple[int, int, int] | None = None
        self._dims: tuple[int, int] = (0, 0)
        self._scale = 1
        self._thickness = 1
        self._d_need = 0.0
        self._spark_seed = 0
        self._last_t = 1.0

    # --- planning -----------------------------------------------------------

    def _ensure_plan(self, canvas):
        # `real` is re-derived on EVERY call and never cached on self
        # (constraint #1: frame.swap() hands back a different buffer).
        scale = canvas.scale if is_scaled(canvas) else 1
        real = unwrap_to_real(canvas) if is_scaled(canvas) else canvas
        key = (real.width, real.height, scale)
        if not self._path or self._plan_key != key:
            self._path = plan_path(real.width, real.height, scale, self._rng)
            self._plan_key = key
            self._dims = (real.width, real.height)
            self._scale = scale
            self._thickness = max(1, scale // 2)
            h = real.height
            self._d_need = (
                max(max(py, h - py) for py in self._path) + self._thickness + 1
            )
            self._spark_seed = self._rng.randrange(1 << 30)
        return real

    # --- flight phase -------------------------------------------------------

    def _head_x(self, s: float, w: int) -> float:
        return s * (w - 1) if self._direction > 0 else (1.0 - s) * (w - 1)

    def _paint_flight(self, real, t):
        w, h = self._dims
        path = self._path
        thk = self._thickness
        scale = self._scale
        set_pixel = real.SetPixel
        dust = self.dust_color
        line_col = tuple(int(c * 0.45) for c in dust)
        s = min(1.0, t / _CUTOVER)
        head = self._head_x(s, w)
        trail_len = max(4, int(_TRAIL_FRAC * w))
        spread = _SPARK_SPREAD_LOGICAL * scale
        qt = round(t * 997)
        for x in range(w):
            behind = (head - x) * self._direction
            if behind < 0:
                continue  # ahead of the fairy
            # settled line under everything already flown over
            y0 = path[x] - (thk - 1) // 2
            for y in range(y0, y0 + thk):
                if 0 <= y < h:
                    set_pixel(x, y, *line_col)
            if behind > trail_len:
                continue  # dust has faded to just the line
            # stateless sparks: presence, offset, base brightness from _mix
            age = 1.0 - behind / trail_len
            for k in range(_SPARKS_PER_COL):
                rr = _mix(self._spark_seed, x, k)
                if rr % 3 == 0:
                    continue  # this (column, k) slot never sparks
                dy = (rr >> 4) % (2 * spread + 1) - spread
                tw = ((_mix(rr, qt) >> 3) & 0xFF) / 255.0
                b = age * (0.35 + 0.65 * tw)
                base = (_CREAM, _GOLD, _AMBER)[(rr >> 2) % 3]
                col = _tinted(base, dust)
                col = tuple(int(c * b) for c in col)
                sy = path[x] + dy
                if not (0 <= sy < h):
                    continue
                set_pixel(x, sy, *col)
                if b > 0.75 and scale > 1:  # bright sparks -> 4-point star
                    for ox, oy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        nx2, ny2 = x + ox, sy + oy
                        if 0 <= nx2 < w and 0 <= ny2 < h:
                            set_pixel(nx2, ny2, *col)
        # white-hot head + gold halo
        hx = int(round(head))
        r_h = max(1, scale // 2)
        halo = _tinted(_GOLD, dust)
        for ox in range(-r_h - 1, r_h + 2):
            for oy in range(-r_h - 1, r_h + 2):
                x2, y2 = hx + ox, (path[hx] if 0 <= hx < w else h // 2) + oy
                if not (0 <= x2 < w and 0 <= y2 < h):
                    continue
                if abs(ox) <= r_h and abs(oy) <= r_h:
                    set_pixel(x2, y2, *_HEAD_COLOR)
                else:
                    set_pixel(x2, y2, *halo)

    # --- open phase (gap/blackout core duplicated from lightning.py --------
    # on purpose: rule of three, see spec Code shape) ------------------------

    def _gap_d(self, t: float) -> float:
        p = (t - _CUTOVER) / (SNAP_THRESHOLD - _CUTOVER)
        p = min(1.0, max(0.0, p / _OPEN_END))
        ease = p * p * (3.0 - 2.0 * p)
        return ease * self._d_need

    def _paint_open(self, real, t):
        w, h = self._dims
        path = self._path
        thk = self._thickness
        d = self._gap_d(t)
        set_pixel = real.SetPixel
        dust = self.dust_color
        edge_col = _tinted(_GOLD, dust)
        qt = round(t * 997)
        for x in range(w):
            lo = path[x] - d  # gap: lo < y < hi
            hi = path[x] + d
            top_black_end = min(h, max(0, math.ceil(lo)))  # [0, end) black
            bot_black_start = max(0, math.floor(hi) + 1)  # [start, h) black
            for y in range(0, top_black_end):
                set_pixel(x, y, 0, 0, 0)
            for y in range(bot_black_start, h):
                set_pixel(x, y, 0, 0, 0)
            # gold edges over the innermost black rows, with twinkle sparkle
            sparkle = (_mix(self._spark_seed, x, 7, qt) & 0xFF) > 200
            col = _CREAM if sparkle else edge_col
            for y in range(max(0, top_black_end - thk), top_black_end):
                set_pixel(x, y, *col)
            for y in range(bot_black_start, min(h, bot_black_start + thk)):
                set_pixel(x, y, *col)

    # --- driver -------------------------------------------------------------

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
            self._path = []  # re-fire from fresh entropy (empty == replan)
            self._plan_key = None
            self._rng = random.Random()
        self._last_t = t

        real = self._ensure_plan(canvas)

        if t < _CUTOVER:
            outgoing.draw(canvas, cursor_pos=kwargs.get("outgoing_scroll_pos", 0))
            self._paint_flight(real, t)
        else:
            snap_reset(canvas, kwargs.get("incoming_bg_color"))
            incoming.draw(canvas, cursor_pos=0)
            self._paint_open(real, t)
        return canvas


class FairyReverse(Fairy):
    """Fairy flying right->left."""

    _direction = -1


class FairyAlternating:
    """Cycles fairy.forward -> fairy.reverse per firing (pacman convention)."""

    def __init__(self, color: Any = None, seed: Any = None) -> None:
        self._transitions: list[Any] = [
            Fairy(color=color, seed=seed),
            FairyReverse(color=color, seed=seed),
        ]
        self._index: int = -1
        self._last_t: float = 1.0

    @property
    def min_frames(self) -> int:
        next_idx = (self._index + 1) % len(self._transitions)
        return getattr(self._transitions[next_idx], "min_frames", 24)

    def frame_at(self, t, canvas, outgoing, incoming, **kwargs):
        if t < self._last_t:
            self._index = (self._index + 1) % len(self._transitions)
        self._last_t = t
        return self._transitions[self._index].frame_at(
            t, canvas, outgoing, incoming, **kwargs
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --extra dev pytest tests/test_flair_fairy_transition.py tests/test_flair_fairy_plan.py -q`
Expected: all pass (6 plan + 28 transition; FullReveal is 16 parametrized cases). If `TestDirections` thresholds prove flaky for some seed, adjust the probe t (0.15) — not the assertion direction.

- [ ] **Step 5: Commit**

```bash
git add plugins/flair/src/led_ticker_flair/flair/fairy.py plugins/flair/tests/test_flair_fairy_transition.py
git commit -m "feat(fairy): Fairy/FairyReverse/FairyAlternating flight-and-open transition"
```

---

### Task 3: Registration + perf-uniformity tripwires + gates

**Files:**
- Modify: `plugins/flair/src/led_ticker_flair/flair/__init__.py` (`register`)
- Test: `plugins/flair/tests/test_flair_fairy_transition.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `plugins/flair/tests/test_flair_fairy_transition.py`:

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
    def test_all_three_fairy_variants_registered(self) -> None:
        api = _RecordingAPI()
        flair_pkg.register(api)
        assert api.transitions["fairy.forward"] is Fairy
        assert api.transitions["fairy.reverse"] is FairyReverse
        assert api.transitions["fairy.alternating"] is FairyAlternating


class TestPerfUniformity:
    """Committed CI-safe perf gate (lightning convention): count WORK per
    frame, not time — a deferred-backlog bug fails the bound
    deterministically."""

    def test_per_frame_paint_volume_bounded(self) -> None:
        canvas = _StubCanvas(width=160, height=16)
        o = _make_widget(draw_pixel=False)
        i = _make_widget(draw_pixel=False)
        p = Fairy(seed=4)
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
            f"frame at t={worst_t} painted {worst} px (> 1.5x panel {panel})"
        )

    def test_alternating_refire_frames_equally_bounded(self) -> None:
        canvas = _StubCanvas(width=160, height=16)
        o = _make_widget(draw_pixel=False)
        i = _make_widget(draw_pixel=False)
        p = FairyAlternating()  # seedless, flips per firing
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

- [ ] **Step 2: Run to verify the registration test fails**

Run: `uv run --extra dev pytest tests/test_flair_fairy_transition.py -q -k "Registration or PerfUniformity"`
Expected: `test_all_three_fairy_variants_registered` FAILS (`KeyError: 'fairy.forward'`); perf tests may already pass (tripwires).

- [ ] **Step 3: Register**

In `plugins/flair/src/led_ticker_flair/flair/__init__.py` inside `register(api)`, add the import (alphabetical) and registrations:

```python
    from led_ticker_flair.flair.fairy import (  # noqa: PLC0415
        Fairy,
        FairyAlternating,
        FairyReverse,
    )
```

and after the existing `api.transition(...)` lines:

```python
    api.transition("fairy.forward")(Fairy)
    api.transition("fairy.reverse")(FairyReverse)
    api.transition("fairy.alternating")(FairyAlternating)
```

- [ ] **Step 4: Full suite + lint gates**

Run: `uv run --extra dev pytest tests/ -q` — all pass.
Run: `uv run --extra dev ruff check src/ tests/ && uv run --extra dev ruff format --check src/ tests/ && PYRIGHT_PYTHON_FORCE_VERSION=latest uv run --extra dev pyright src/` — clean.

- [ ] **Step 5: End-to-end type resolution check (the two-dot question, settled empirically)**

Run from the CORE repo (`/Users/james/projects/github/jamesawesome/led-ticker`):

```bash
uv pip install -q -e /Users/james/projects/github/jamesawesome/led-ticker-plugins-flight/plugins/flair
uv run --no-sync python -c "
from led_ticker._plugin_loader import load_plugins
load_plugins()
from led_ticker.transitions import get_transition_class
for n in ('flair.fairy.forward', 'flair.fairy.reverse', 'flair.fairy.alternating'):
    print(n, '->', get_transition_class(n).__name__)
"
```

Expected: the three classes print. (If `load_plugins` has a different public entry name, use the same import the CLI's startup uses — grep `load_plugins` in core.)

- [ ] **Step 6: Commit**

```bash
git add plugins/flair/src/led_ticker_flair/flair/__init__.py plugins/flair/tests/test_flair_fairy_transition.py
git commit -m "feat(fairy): register flair.fairy.{forward,reverse,alternating} + perf tripwires"
```

---

### Task 4: Benchmarks + visual gate (HARD STOP for James)

**Files:** scratch only under `$CLAUDE_JOB_DIR/tmp/`.

- [ ] **Step 1: Frame-time sweep (fresh + refire)**

Write `$CLAUDE_JOB_DIR/tmp/fairy_frametime.py` — identical harness to the lightning sweep (`Stub` canvas class with `SetPixel/Clear/Fill` no-ops, mock widget, 0.02 t-steps on `ScaledCanvas(Stub(256, 64), scale=4, content_height=16)`), sweeping `FairyAlternating()` for TWO firings (so both directions measure) and printing avg/worst per firing; assert `worst <= 5 * avg` for both. Run with `uv run --extra dev python` from `plugins/flair/`.
Expected: ms-class avg, no cutover outlier. Record numbers for the PR body.

- [ ] **Step 2: Fresh-process construction + first-frame check**

Run from `plugins/flair/` (same one-liner shape as lightning's Task 4 Step 2, substituting `Fairy(seed=7)`): construction < 10ms, first frame < 10ms. Record.

- [ ] **Step 3: Render visual-gate GIFs**

From the CORE repo (editable install from Task 3 Step 5 still present; always `uv run --no-sync`): write `$CLAUDE_JOB_DIR/tmp/fairy-gate-bigsign.toml` modeled exactly on the lightning gate config (rows 64 / cols 256 / chain_length 1 / default_scale 4 / brightness 70, `[transitions] duration = 2.5`, two slideshow sections hold_time 2 with "BEFORE" amber / "AFTER" green Inter-Bold 44 messages) with `transition = {type = "flair.fairy.alternating", seed = 3}` on both sections, and `$CLAUDE_JOB_DIR/tmp/fairy-gate-smallsign.toml` (rows 16 / cols 32 / chain_length 5 / scale 1, BDF default font) the same way. Render both at `--duration 14` (long enough for two firings = both directions of alternating). Then extract a contact sheet (PIL, sampled frames) and CHECK IT YOURSELF before sending: head + dust visible over outgoing, line settles, gap opens with sparkling edges, both directions appear.

- [ ] **Step 4: HARD STOP — send GIFs to James**

Send both GIFs + the benchmark numbers. Tuning surface to name explicitly: spark density, twinkle rate, trail length, halo size, edge-sparkle frequency. Do NOT proceed to Task 5 until approved; iterate constants + re-render as directed (each iteration re-runs the fairy test files).

---

### Task 5 (post-gate): Smoke config, README, PR

**Files:**
- Create: `plugins/flair/examples/config.fairy-smoke.bigsign.toml`
- Modify: `plugins/flair/README.md`

- [ ] **Step 1: Smoke config**

Create `plugins/flair/examples/config.fairy-smoke.bigsign.toml` following `config.lightning-smoke.bigsign.toml`'s exact conventions (header block: `# requires-plugins: led-ticker-flair`, flair >= 0.12.0 prereqs, preflight validate note, WHAT TO LOOK FOR list stating the reveal-against-black design decision). Sections (mode = "slideshow", hold_time = 1.5, two Inter-Bold 44 message widgets each, `[display]` block copied from the lightning smoke config):

1. FORWARD — `transition = "flair.fairy.forward"`: dust trails LEFT of the head, line settles, opens.
2. REVERSE — `transition = "flair.fairy.reverse"`.
3. ALTERNATING — `transition = "flair.fairy.alternating"`: direction flips every firing — watch two cycles.
4. SEEDED — `transition = {type = "flair.fairy.forward", seed = 99}`: identical path + spark field every firing.
5. TINTED — `transition = {type = "flair.fairy.forward", color = [180, 120, 255]}`: violet dust, head stays white.
6. BG HOLD — section `bg_color = [40, 10, 60]`: gap interior purple from the first sliver, clean snap.
7. PERF FEEL — smooth flight AND open; first firing after boot as smooth as later ones.

Validate from the core repo: `uv run --no-sync led-ticker validate <path>` → no errors.

- [ ] **Step 2: README entry + demo GIF**

Copy the approved bigsign gate GIF to `plugins/flair/docs/transition-fairy.gif`. Add a `## Fairy transition` section to `plugins/flair/README.md` after the Lightning section, matching its format: one-paragraph description (flight → line → open; reveal against black note), the GIF embed, `Requires led-ticker-core >= 4.18.0`, Config examples (all three variants + seed + color inline-table forms), Knobs table (`seed`, `color`; direction = variants, not a knob), Notes (two-phase design, stateless sparks/no warm-up, per-frame paint bounded by the `TestPerfUniformity` tripwires).

- [ ] **Step 3: Full suite + lint + commit + push**

Run the full suite + three lint gates; then:

```bash
git add plugins/flair/examples/config.fairy-smoke.bigsign.toml plugins/flair/README.md plugins/flair/docs/transition-fairy.gif
git commit -m "docs(fairy): bigsign smoke config + README entry + demo GIF"
git push -u origin flair-fairy
```

- [ ] **Step 4: Open the PR**

`gh pr create` — body: what/why (Tinkerbell brief), design decisions (near-straight path, gold dust, three sprite-convention variants, cutover 0.5, duplicated open core with rule-of-three note), benchmark table (both firings + fresh-process), tests summary, gate outcome, and:

```
## Test on the sign
config/requirements-plugins.txt:
  led-ticker-flair @ git+https://github.com/JamesAwesome/led-ticker-plugins.git@flair-fairy#subdirectory=plugins/flair
then: docker compose down -v && docker compose up -d
Copy plugins/flair/examples/config.fairy-smoke.bigsign.toml to config/config.toml and make restart.
```

Watch CI (`gh pr checks --watch --interval 30`). Do NOT merge — James's word first; release then = `cut_release.py flair minor` → flair-v0.12.0.
