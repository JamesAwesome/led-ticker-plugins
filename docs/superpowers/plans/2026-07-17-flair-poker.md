# flair.poker Transition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The `flair.poker` card-suit ripple transition per `docs/superpowers/specs/2026-07-17-flair-poker-transition-design.md` — rainbow suit glyphs pattern in, then emit suit-shaped rainbow ripple pulses that wash the incoming widget in against black.

**Architecture:** stickers/fireworks template: a pure math/plan module (`poker.py` — suit mask functions, ring pixel-lists, glyph grid plan, pacing) plus a `Poker` transition class registered as `flair.poker`. Suit shapes are pure `inside(suit, dx, dy, r)` masks; ring pixel-lists are pre-rasterized once per firing; the reveal is a monotone accumulated mask; per-frame paint is plain SetPixel.

**Tech Stack:** Python 3.14, pytest. Working copy: `/Users/james/projects/github/jamesawesome/led-ticker-plugins-flight`, branch `flair-poker` (spec + prototype already committed there). Run `git branch --show-current` first; abort if not `flair-poker`.

## Global Constraints

- Core imports ONLY via `led_ticker.plugin` (AST-enforced by the package's import-purity test). Sufficient set: `SNAP_THRESHOLD`, `snap_reset`, `unwrap_to_real`, `is_scaled`. NO new core surface (poker needs none — unlike stickers, do not import `emoji_slugs`).
- No `from __future__ import annotations`. PEP-758 bare multi-exception `except` is the project convention.
- The reference shape math is the committed prototype `docs/superpowers/prototypes/2026-07-17-flair-poker-proto.py` — port its `in_heart`/`in_diamond`/`in_club`/`in_spade` verbatim (they were visually gated). Constants from the spec: `GRID = 32`, `GLYPH_R = 7`, `RING_W = 3.5`, `PULSES = 2.5`, `max_r = 1.2 × cell diagonal`, stagger ∈ [0, 0.25], cutover at t = 0.45.
- **Clubs are NOT radially monotone** — the reveal mask must ACCUMULATE ring pixel-lists (union), never assume `ring = interior delta`. The ring-union coverage test (Task 1) is the guard; clubs are the adversarial case.
- Suit names in config/tests are the plural words: `hearts`, `diamonds`, `clubs`, `spades`. `fire`-style unknowns fail at construction naming the four.
- Tests: `uv run --extra dev pytest plugins/flair/tests/ -q` from the monorepo root. Lint: `uv run --extra dev ruff check plugins/flair/ && uv run --extra dev ruff format --check plugins/flair/`. Pyright: `uv run --extra dev pyright plugins/flair/src`.

---

### Task 1: Pure suit math — masks, rings, ring-union coverage

**Files:**
- Create: `plugins/flair/src/led_ticker_flair/flair/poker.py`
- Test: `plugins/flair/tests/test_flair_poker_shapes.py`

**Interfaces:**
- Produces (consumed by Tasks 2–3): `SUITS = ("hearts", "diamonds", "clubs", "spades")`; `inside(suit, dx, dy, r) -> bool`; `ring_pixels(suit, r, w=RING_W) -> set[tuple[int,int]]` (offsets from glyph center where the mask is inside r but not r−w); `interior_pixels(suit, r) -> set` (inside r); constants `GRID, GLYPH_R, RING_W, PULSES`.

- [ ] **Step 1: Write the failing tests**

```python
"""Pure suit-shape math for flair.poker (no canvas)."""

import math

from led_ticker_flair.flair.poker import (
    RING_W,
    SUITS,
    inside,
    interior_pixels,
    ring_pixels,
)


class TestInside:
    def test_center_inside_all_suits(self):
        for s in SUITS:
            assert inside(s, 0, 0, 10), s

    def test_far_corner_outside_all_suits(self):
        for s in SUITS:
            assert not inside(s, 100, 100, 10), s

    def test_zero_radius_empty(self):
        for s in SUITS:
            assert not inside(s, 0, 0, 0), s

    def test_diamond_is_l1_ball(self):
        assert inside("diamonds", 6, 3, 10)      # 9 <= 10
        assert not inside("diamonds", 7, 5, 10)  # 12 > 10

    def test_club_and_spade_have_a_stem_below_center(self):
        # stem is a thin vertical column just below center (y down)
        for s in ("clubs", "spades"):
            assert inside(s, 0, 8, 20), s
            assert not inside(s, 9, 8, 20), s  # too far sideways for the stem


class TestRings:
    def test_ring_is_interior_shell(self):
        interior = interior_pixels("hearts", 16)
        shell = ring_pixels("hearts", 16)
        assert shell <= interior
        inner = interior_pixels("hearts", 16 - RING_W)
        assert shell.isdisjoint(inner)
        assert shell == interior - inner

    def test_ring_nonempty_for_reasonable_radius(self):
        for s in SUITS:
            assert ring_pixels(s, 14), s


class TestRingUnionCoverage:
    """The property the reveal mask actually relies on (NOT interior
    monotonicity — clubs violate that): the union of integer-radius rings
    up to R covers interior(R). Clubs are the adversarial case."""

    def test_union_of_rings_covers_interior(self):
        for s in SUITS:
            R = 22
            union = set()
            for r in range(1, R + 1):
                union |= ring_pixels(s, r)
            missing = interior_pixels(s, R) - union
            assert not missing, f"{s}: {len(missing)} interior px uncovered by rings"
```

- [ ] **Step 2: Run to verify failure** — `uv run --extra dev pytest plugins/flair/tests/test_flair_poker_shapes.py -q` → FAIL (module missing).

- [ ] **Step 3: Implement the shape math**

`plugins/flair/src/led_ticker_flair/flair/poker.py` (module docstring: flair.poker suit-ripple transition, pure-math half; cite the spec path). Port the prototype's shape functions verbatim, then add `interior_pixels`/`ring_pixels` (bbox scan over `[-r-1, r+1]²`):

```python
import math

SUITS = ("hearts", "diamonds", "clubs", "spades")

GRID = 32
GLYPH_R = 7.0
RING_W = 3.5
PULSES = 2.5


def _in_heart(x, y, r):
    if r <= 0:
        return False
    nx, ny = x / r, -y / r
    v = (nx * nx + ny * ny - 1) ** 3 - nx * nx * ny * ny * ny
    return v <= 0


def _in_diamond(x, y, r):
    return r > 0 and abs(x) + abs(y) <= r


def _in_club(x, y, r):
    if r <= 0:
        return False
    lr = 0.45 * r
    for ang in (90, 210, 330):
        a = math.radians(ang)
        cx, cy = 0.5 * r * math.cos(a), -0.5 * r * math.sin(a)
        if (x - cx) ** 2 + (y - cy) ** 2 <= lr * lr:
            return True
    return abs(x) <= 0.16 * r and 0 <= y <= r


def _in_spade(x, y, r):
    if r <= 0:
        return False
    if _in_heart(x, -y * 0.95, r * 0.92):
        return True
    return abs(x) <= 0.16 * r and 0 <= y <= r


_MASKS = {
    "hearts": _in_heart,
    "diamonds": _in_diamond,
    "clubs": _in_club,
    "spades": _in_spade,
}


def inside(suit, dx, dy, r):
    return _MASKS[suit](dx, dy, r)


def interior_pixels(suit, r):
    m = _MASKS[suit]
    lim = int(math.ceil(r)) + 1
    return {
        (x, y)
        for y in range(-lim, lim + 1)
        for x in range(-lim, lim + 1)
        if m(x, y, r)
    }


def ring_pixels(suit, r, w=RING_W):
    return interior_pixels(suit, r) - interior_pixels(suit, r - w)
```

- [ ] **Step 4: Run to green.** If `test_union_of_rings_covers_interior` fails for clubs, the integer-radius step leaves a gap — the fix is to step rings by `<= RING_W` (they already overlap at step 1 here) or widen `w`; do NOT weaken the test. (Expected to pass as written: unit radius steps with w=3.5 overlap heavily.)

- [ ] **Step 5: Commit** — `git add plugins/flair/src/led_ticker_flair/flair/poker.py plugins/flair/tests/test_flair_poker_shapes.py && git commit -m "feat(flair): poker suit-shape math — masks, rings, ring-union coverage"`

---

### Task 2: Plan + pacing — glyph grid, pulse timeline, per-run ring cache

**Files:**
- Modify: `plugins/flair/src/led_ticker_flair/flair/poker.py` (append)
- Test: `plugins/flair/tests/test_flair_poker_plan.py`

**Interfaces:**
- Produces: `Glyph` (frozen dataclass: `suit, cx, cy, hue, stagger`); `plan_glyphs(panel_w, panel_h, suits, rng) -> list[Glyph]`; `max_radius(cell_w, cell_h) -> float`; `pulse_radius(t, stagger) -> tuple[float, int] | None` (returns `(radius, wave_index)` for the current pulse, or None before the glyph's stagger start / after the transition); `RingCache` (per-run cache: `.get(suit, r_int, hue_deg) -> list[(x, y, (r,g,b))]`, quantizing radius to int and hue to whole degrees).

- [ ] **Step 1: Write the failing tests**

```python
import math
import random

from led_ticker_flair.flair.poker import (
    Glyph,
    RingCache,
    max_radius,
    plan_glyphs,
    pulse_radius,
)

BIG = (256, 64)
SMALL = (160, 16)


class TestPlan:
    def test_deterministic_per_seed(self):
        a = plan_glyphs(*BIG, ["hearts", "diamonds"], random.Random(4))
        b = plan_glyphs(*BIG, ["hearts", "diamonds"], random.Random(4))
        assert a == b

    def test_suits_cycle_through_pool_only(self):
        g = plan_glyphs(*BIG, ["diamonds"], random.Random(1))
        assert {x.suit for x in g} == {"diamonds"}
        g2 = plan_glyphs(*BIG, ["hearts", "spades"], random.Random(1))
        assert {x.suit for x in g2} <= {"hearts", "spades"}

    def test_stagger_in_bounds(self):
        for g in plan_glyphs(*BIG, ["clubs"], random.Random(2)):
            assert 0.0 <= g.stagger <= 0.25

    def test_grid_counts_reasonable(self):
        assert 12 <= len(plan_glyphs(*BIG, ["hearts"], random.Random(0))) <= 24
        assert 3 <= len(plan_glyphs(*SMALL, ["hearts"], random.Random(0))) <= 12


class TestPulseTimeline:
    def test_none_before_stagger_start(self):
        assert pulse_radius(0.0, 0.2) is None

    def test_expands_then_repeats(self):
        # within a wave the radius grows; wave index increments across waves
        r1, w1 = pulse_radius(0.35, 0.0)
        r2, w2 = pulse_radius(0.45, 0.0)
        assert r2 > r1 or w2 > w1

    def test_final_wave_reached_late(self):
        _, w = pulse_radius(0.99, 0.0)
        assert w >= 1  # multiple waves have passed by the end


class TestRingCache:
    def test_quantizes_and_caches(self, monkeypatch):
        import led_ticker_flair.flair.poker as m

        calls = []
        real = m.ring_pixels
        monkeypatch.setattr(
            m, "ring_pixels", lambda *a, **k: calls.append(a) or real(*a, **k)
        )
        cache = RingCache()
        cache.get("hearts", 12, 40.0)
        cache.get("hearts", 12, 40.4)  # same int r, same whole-deg hue
        assert len(calls) == 1
        assert cache.get("hearts", 12, 40.0)  # non-empty pixel list
```

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement** (append to `poker.py`; import `colorsys`, `random` not needed here — rng is passed in):

```python
import colorsys
from dataclasses import dataclass

_STAGGER_MAX = 0.25
_INTRO_END = 0.25  # pulses begin after this fraction (+ per-glyph stagger)
_MAX_R_FACTOR = 1.2


@dataclass(frozen=True)
class Glyph:
    suit: str
    cx: int
    cy: int
    hue: float
    stagger: float


def max_radius(cell_w, cell_h):
    return _MAX_R_FACTOR * math.hypot(cell_w, cell_h)


def plan_glyphs(panel_w, panel_h, suits, rng):
    cols = max(1, math.ceil(panel_w / GRID))
    rows = max(1, math.ceil(panel_h / GRID))
    out = []
    for i in range(cols * rows):
        gx, gy = i % cols, i // cols
        out.append(
            Glyph(
                suit=suits[i % len(suits)],
                cx=round(gx * GRID + GRID / 2 + rng.uniform(-3, 3)),
                cy=round(gy * GRID + GRID / 2 + rng.uniform(-2, 2)),
                hue=rng.random(),
                stagger=rng.uniform(0.0, _STAGGER_MAX),
            )
        )
    return out


def pulse_radius(t, stagger):
    """(_radius_, wave_index) for the pulse active at global t, or None
    before this glyph's pulses begin. Radius is a FRACTION of max_r
    (0..1); the caller scales by its own max_radius."""
    start = _INTRO_END + stagger
    if t < start:
        return None
    p = (t - start) / (1.0 - start)  # 0..1 across the pulse window
    scaled = p * PULSES
    wave = int(scaled)
    phase = scaled - wave  # 0..1 within the current wave
    return phase, wave


class RingCache:
    def __init__(self):
        self._cache = {}

    def get(self, suit, r_int, hue_deg):
        key = (suit, int(r_int), round(hue_deg))
        hit = self._cache.get(key)
        if hit is None:
            rr, gg, bb = colorsys.hsv_to_rgb((round(hue_deg) % 360) / 360.0, 1.0, 1.0)
            color = (int(rr * 255), int(gg * 255), int(bb * 255))
            hit = [(x, y, color) for (x, y) in ring_pixels(suit, int(r_int))]
            self._cache[key] = hit
        return hit
```

(Note: `pulse_radius` returns `(phase, wave)` — `phase` is a 0..1 fraction; Task 3 multiplies by `max_r`. Adjust the Step-1 test's `r1<r2` reading accordingly: within a wave `phase` grows, so `r` grows; the test asserts `r2 > r1 OR w2 > w1` to tolerate a wave boundary between the two sample points.)

- [ ] **Step 4: Run to green.**
- [ ] **Step 5: Commit** — `git commit -m "feat(flair): poker plan + pulse timeline + per-run ring cache"` with both files.

---

### Task 3: The `Poker` transition class + registration

**Files:**
- Modify: `plugins/flair/src/led_ticker_flair/flair/poker.py` (append the class)
- Modify: `plugins/flair/src/led_ticker_flair/flair/__init__.py` (import + `api.transition("poker")(Poker)`)
- Test: `plugins/flair/tests/test_flair_poker_transition.py`

**Interfaces:**
- Consumes: Task 1/2 names; `led_ticker.plugin.{SNAP_THRESHOLD, snap_reset, unwrap_to_real, is_scaled}`.
- Produces: `Poker(suits=None, seed=None)` registered as `transition = "flair.poker"`.

- [ ] **Step 1: Write the failing tests** — reuse the stickers transition test's stub idioms (`plugins/flair/tests/test_flair_poker_transition.py`; copy the `_StubCanvas` + `_make_widget` fixtures from `test_flair_stickers_transition.py` — per-file duplication is this repo's convention). Required cases, each real:

```python
class TestKnobValidation:
    def test_unknown_suit_raises_naming_options(self):
        with pytest.raises(ValueError, match="hearts.*diamonds.*clubs.*spades|suits"):
            Poker(suits=["wands"])

    def test_empty_or_nonlist_rejected(self):
        for bad in ([], "hearts", [1], [""]):
            with pytest.raises(ValueError):
                Poker(suits=bad)

    def test_valid_suits_and_default(self):
        Poker()                       # all four
        Poker(suits=["diamonds"])
        Poker(suits=["hearts", "spades"])


class TestEndpoints:
    def test_t_zero_draws_outgoing_only(self): ...   # outgoing.draw called; no ring/glyph pixels
    def test_snap_draws_incoming_on_bg(self): ...    # t>=SNAP: snap_reset(bg) + incoming.draw
    def test_full_reveal_before_snap(self): ...      # at t just below SNAP, on a stub real canvas
                                                     # (both geometries), EVERY panel pixel is either
                                                     # incoming-content or a ring — none left as the
                                                     # black complement. seed= for determinism.
    def test_no_outgoing_paint_after_cutover(self): ... # t=0.6: outgoing.draw NOT called

class TestDeterminismAndRefire:
    def test_same_seed_same_frames(self): ...        # two instances seed=5: identical t=0.3 pixels
    def test_refire_replans(self): ...               # t back to 0.1 after 1.0 -> new plan

class TestPerf:
    def test_no_ring_rasterization_after_first_frame(self, monkeypatch): ...
        # spy poker.ring_pixels; frame_at at t=0.5 then t=0.6: all ring_pixels
        # calls happen by the end of the first call (cache warm), zero on the second
```

For `test_full_reveal_before_snap`, model it on stickers' `test_full_cover_at_half`: both widgets are no-ops that paint nothing, so any non-black pixel came from the transition; assert `missing == []` where missing = panel pixels still unpainted at t = SNAP − epsilon.

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement the class** (append to `poker.py`; fireworks/stickers are the structural template — `min_frames`, lazy plan keyed on `(w,h,scale)`, `_last_t` re-fire, entropy reseed when `seed is None`):

```python
import random
from typing import Any

from led_ticker.plugin import SNAP_THRESHOLD, is_scaled, snap_reset, unwrap_to_real

_CUTOVER = 0.45


class Poker:
    """Card-suit ripple transition: rainbow suit glyphs pattern in, then
    emit suit-shaped rainbow ripple pulses that wash the incoming widget in
    against black. `suits=[...]` restricts the pool (default all four)."""

    min_frames = 24

    def __init__(self, suits: Any = None, seed: int | None = None) -> None:
        if suits is not None:
            if (
                not isinstance(suits, list)
                or not suits
                or not all(isinstance(s, str) and s for s in suits)
            ):
                raise ValueError(
                    f"suits must be a non-empty list of suit names; got {suits!r}"
                )
            unknown = sorted(set(suits) - set(SUITS))
            if unknown:
                raise ValueError(
                    f"unknown suit(s) {unknown!r}; valid: {list(SUITS)!r}"
                )
        self.suits = list(suits) if suits else list(SUITS)
        self.seed = seed
        self._rng = random.Random(seed) if seed is not None else random.Random()
        self._plan = None
        self._plan_key = None
        self._rings = RingCache()
        self._revealed = None  # bytearray(w*h) per firing
        self._dims = None
        self._max_r = None
        self._last_t = 1.0

    def _ensure_plan(self, canvas):
        scale = canvas.scale if is_scaled(canvas) else 1
        real = unwrap_to_real(canvas) if is_scaled(canvas) else canvas
        key = (real.width, real.height, scale)
        if self._plan is None or self._plan_key != key:
            self._plan = plan_glyphs(real.width, real.height, self.suits, self._rng)
            self._plan_key = key
            self._dims = (real.width, real.height)
            self._max_r = max_radius(GRID, GRID)
            self._revealed = bytearray(real.width * real.height)
        return self._plan, real

    def _reveal_and_rings(self, real, t):
        """Accumulate the final wave's ring into the reveal mask, and return
        the list of (x, y, color) ring pixels to paint this frame."""
        w, h = self._dims
        ring_px = []
        for g in self._plan:
            pr = pulse_radius(t, g.stagger)
            if pr is None:
                continue
            phase, wave = pr
            r = phase * self._max_r
            hue_deg = (g.hue * 360 + phase * 0.7 * 360)
            for (dx, dy, col) in self._rings.get(g.suit, round(r), hue_deg):
                x, y = g.cx + dx, g.cy + dy
                if 0 <= x < w and 0 <= y < h:
                    ring_px.append((x, y, col))
                    # the FINAL wave's interior is the permanent reveal
                    if wave >= int(PULSES) - 0 and t >= _CUTOVER:
                        self._revealed[y * w + x] = 1
        return ring_px

    def frame_at(self, t, canvas, outgoing, incoming, **kwargs):
        if t <= 0.0:
            outgoing.draw(canvas, cursor_pos=kwargs.get("outgoing_scroll_pos", 0))
            return canvas
        if t >= SNAP_THRESHOLD:
            snap_reset(canvas, kwargs.get("incoming_bg_color"))
            incoming.draw(canvas, cursor_pos=0)
            self._last_t = 1.0
            return canvas
        if t < self._last_t and self.seed is None:
            self._plan = None
            self._rng = random.Random()
        self._last_t = t

        plan, real = self._ensure_plan(canvas)
        w, h = self._dims

        if t < _CUTOVER:
            outgoing.draw(canvas, cursor_pos=kwargs.get("outgoing_scroll_pos", 0))
            ring_px = self._reveal_and_rings(real, t)
            # glyph intro: paint resting glyphs (their own hue) before pulses
            self._paint_glyphs(real, t)
            for x, y, col in ring_px:
                real.SetPixel(x, y, *col)
        else:
            snap_reset(canvas, kwargs.get("incoming_bg_color"))
            incoming.draw(canvas, cursor_pos=0)
            ring_px = self._reveal_and_rings(real, t)
            # black the not-yet-revealed complement
            for y in range(h):
                base = y * w
                for x in range(w):
                    if not self._revealed[base + x]:
                        real.SetPixel(x, y, 0, 0, 0)
            for x, y, col in ring_px:
                real.SetPixel(x, y, *col)
        return canvas

    def _paint_glyphs(self, real, t):
        w, h = self._dims
        scale_in = min(1.0, t / 0.2)
        gr = GLYPH_R * scale_in
        if gr <= 0:
            return
        for g in self._plan:
            hue_deg = g.hue * 360 + t * 0.5 * 360
            for (dx, dy, col) in self._rings.get(
                g.suit, round(gr) + 1, hue_deg
            ):  # a filled small glyph: use interior, see note
                pass
```

**Implementation notes for the implementer (resolve these during Task 3):**
- The `_paint_glyphs` sketch above is incomplete on purpose — the resting glyph is a FILLED small suit, not a ring. Add an `interior_list(suit, r, hue_deg)` helper on `RingCache` (or a sibling cache) that returns `interior_pixels`-based `(x,y,color)` lists, pre-warmed like rings. Keep it plan-time-cached (perf tripwire covers it).
- **Pre-warm ALL ring/interior lists in `_ensure_plan`** (every glyph × every integer radius 0..ceil(max_r) it can reach, and each glyph's intro interior) so `test_no_ring_rasterization_after_first_frame` holds — mirror stickers' pre-warm loop. Hue is continuous, but the cache quantizes hue to whole degrees, so pre-warm at the hue each (glyph, radius) will actually request — compute the same `hue_deg` formula used in `_reveal_and_rings`/`_paint_glyphs`.
- The reveal-accumulation condition (`wave >= int(PULSES) ...`) is a sketch — the REQUIREMENT is: by t = SNAP−epsilon every panel pixel is revealed (Task 3's `test_full_reveal_before_snap`). Simplest correct rule: accumulate EVERY ring pixel into `_revealed` once t ≥ `_CUTOVER` (not just the final wave) — rings sweep the whole cell-diagonal-×1.2 area across the pulses, so the union covers the panel by construction. Use whichever passes the full-reveal test; do not weaken the test.
- `frame_at` must recompute `unwrap_to_real(canvas)` every call (canvas identity changes per swap — the stickers stale-canvas lesson). `_ensure_plan` already returns `real` fresh each call; never cache the real canvas on `self`.
- Register in `__init__.py`: `from led_ticker_flair.flair.poker import Poker` + `api.transition("poker")(Poker)` next to the stickers line. No core-floor bump (poker imports no new core surface; the existing `>=4.18` floor from stickers stands).

- [ ] **Step 4: Run the full flair suite + lint + pyright to green.**
- [ ] **Step 5: Commit** — `git commit -m "feat(flair): flair.poker suit-ripple transition"` with all touched files.

---

### Task 4: Docs, smoke example, GIF gate, PR

**Files:**
- Modify: `plugins/flair/README.md` (a `flair.poker` transitions entry — config forms, suits list, seed, the black-backdrop note)
- Modify: `plugins/flair/CLAUDE.md` (one invariant paragraph: plan-time ring pre-rasterization; reveal is an ACCUMULATED mask because clubs aren't radially monotone; full-reveal pinned by the seed sweep + transition test; `frame_at` recomputes real canvas every call)
- Create: `plugins/flair/examples/config.poker-smoke.bigsign.toml`

- [ ] **Step 1: README + CLAUDE.md entries** — README shows `transition = "flair.poker"`, `{type="flair.poker", suits=["diamonds"]}`, `{... suits=["clubs"]}`, the `seed` knob, and a one-line note that the second half reveals the incoming widget against black (not the old content). Real suit names only.

- [ ] **Step 2: Smoke example** — `plugins/flair/examples/config.poker-smoke.bigsign.toml`, in the stickers-smoke shape (bigsign display block, `# requires-plugins: led-ticker-flair`, WHAT-TO-LOOK-FOR header). Sections: all-suits pattern+ripple, diamonds-only, clubs-only, hearts+spades seeded, a bg_color incoming to check the snap. Validate it: `uv run led-ticker validate <path>` → No issues found (needs the branch flair installed in a core checkout).

- [ ] **Step 3: GIF gate (render-path change — mandatory before PR).** In a core-repo checkout with this branch's flair installed (`uv pip install --no-cache --reinstall <monorepo>/plugins/flair`), render via `tools/render_demo/render.py` on throwaway bigsign-flat TOMLs (`rows=64 cols=256 chain_length=1 default_scale=4`): (a) all-suits between two message widgets, (b) diamonds-only, (c) smallsign geometry all-suits. Check against `docs/visual-validation.md`: suit glyphs read, ripples are suit-shaped, incoming fully revealed before snap, no stray pixels, clean incoming after snap, AND the approved black-backdrop second half looks right. Attach the GIFs to the session for James.

- [ ] **Step 4: Full checks** — flair suite, ruff check + format, pyright, import-purity.

- [ ] **Step 5: Push + PR.** `git push -u origin flair-poker`; `gh pr create` (body via file): what/choreography summary, spec path, the black-backdrop caveat as a called-out design note, GIF-gate results, AND the standing **"Test on the sign"** section:

```
## Test on the sign

In `config/requirements-plugins.txt`:

    led-ticker-flair @ git+https://github.com/JamesAwesome/led-ticker-plugins.git@flair-poker#subdirectory=plugins/flair

then `docker compose down -v && docker compose up -d` (the `-v` refresh is required so reconcile reinstalls the branch build).
```

Watch CI to green. Do NOT merge — user go-ahead required.

---

## After merge

- `flair-v0.10.0` via `cut_release.py flair minor`.
- Docs-site transitions entry + catalog `provides` line for flair.poker — batch with the still-pending flair.stickers docs-site entry (both tracked in `project_flair_stickers_transition` follow-ups).
