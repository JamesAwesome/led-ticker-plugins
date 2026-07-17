# flair.stickers Transition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The `flair.stickers` sticker-bomb transition per `docs/superpowers/specs/2026-07-17-flair-stickers-transition-design.md` — emoji stickers pop on until the panel is covered at t=0.5, then pop off revealing the incoming widget.

**Architecture:** Fireworks template: a pure plan/math module (`stickers.py` — grid plan, die-cut composition, plan-time inverse-map rotation) plus a `Stickers` transition class registered as `flair.stickers`. Stickers are rasterized ONCE per (slug, whole-degree angle) at plan time into real-pixel lists via a capture canvas; `frame_at` is plain SetPixel iteration. All core access through `led_ticker.plugin`.

**Tech Stack:** Python 3.14, pytest, attrs where the package already uses it. Working copy: `/Users/james/projects/github/jamesawesome/led-ticker-plugins-flight`, branch `flair-stickers` (spec already committed there). Run `git branch --show-current` first; abort if not `flair-stickers`.

## Global Constraints

- Imports from core ONLY via `led_ticker.plugin` (AST-enforced by the package's import-purity test). Available and sufficient: `SNAP_THRESHOLD`, `snap_reset`, `unwrap_to_real`, `is_scaled`, `ScaledCanvas`, `draw_emoji_at`, `emoji_slugs` (the new seam).
- **Core floor:** the seam ships in the core release cut from core PR "emoji_slugs() enumeration seam". At implementation time, resolve the ACTUAL released version (`gh release list --repo JamesAwesome/led-ticker | head`) and floor `plugins/flair/pyproject.toml` to it. NEVER write a guessed version number (release-order-guard rule: derive at execution time, not plan time).
- No `from __future__ import annotations`. PEP-758 bare multi-exception `except` is project convention.
- Spec constants (verbatim, single source in `stickers.py`): `GRID_OVERLAP = 0.7`, `JITTER_FRAC = 0.1`, `TILT_MAX_DEG = 10.0`, `BACKING_PAD = 1`, `OUTLINE_PAD = 2`. (Tilt/jitter tightened from the spec's ±15°/±25% during plan math: with cell = 0.7×footprint, a square rotated 10° still inscribes an axis-aligned square of 0.864×footprint, which covers cell/2 + jitter with margin; ±15° with ±25% jitter provably opens gaps. The coverage TEST is the enforcement — if it ever fails, tighten `GRID_OVERLAP`, don't loosen the test.)
- Only REAL slugs in tests/docs: `taco`, `sun`, `moon`, `star`, `heart_red`, `pride`… (`fire` does not exist and is the canonical negative case).
- Tests: `uv run --extra dev pytest plugins/flair/tests/ -q` from the monorepo root. Lint: `uv run --extra dev ruff check plugins/flair/ && uv run --extra dev ruff format --check plugins/flair/`. Pyright: `uv run --extra dev pyright plugins/flair/src`.

---

### Task 1: Pure math — grid plan, pacing, dilation, rotation

**Files:**
- Create: `plugins/flair/src/led_ticker_flair/flair/stickers.py`
- Test: `plugins/flair/tests/test_flair_stickers_plan.py`

**Interfaces:**
- Produces (consumed by Tasks 2–3): `Sticker` (frozen dataclass: `slug: str, cx: int, cy: int, angle_deg: float, arrive: int, depart: int`), `plan_stickers(panel_w, panel_h, footprint, slugs, rng) -> list[Sticker]`, `visible_count(t, n) -> int` (build phase), `departed_count(t, n) -> int` (peel phase), `dilate(mask, radius) -> set`, `rotate_pixels(pixels, angle_deg) -> dict`.

- [ ] **Step 1: Write the failing tests**

```python
"""Pure-math tests for the stickers plan module (no canvas)."""

import math
import random

from led_ticker_flair.flair.stickers import (
    GRID_OVERLAP,
    Sticker,
    departed_count,
    dilate,
    plan_stickers,
    rotate_pixels,
    visible_count,
)

BIGSIGN = (256, 64, 36)   # panel_w, panel_h, footprint (32px sprite + 2*OUTLINE_PAD)
SMALLSIGN = (160, 16, 12)  # 8px sprite + 2*OUTLINE_PAD


class TestPlan:
    def test_orders_are_independent_permutations(self):
        rng = random.Random(7)
        plan = plan_stickers(*BIGSIGN, slugs=["taco"], rng=rng)
        n = len(plan)
        assert sorted(s.arrive for s in plan) == list(range(n))
        assert sorted(s.depart for s in plan) == list(range(n))
        # not the same permutation, not reversed (peel must not be a rewind)
        assert [s.arrive for s in plan] != [s.depart for s in plan]
        assert [s.arrive for s in plan] != [n - 1 - s.depart for s in plan]

    def test_deterministic_per_seed(self):
        p1 = plan_stickers(*BIGSIGN, slugs=["taco", "sun"], rng=random.Random(3))
        p2 = plan_stickers(*BIGSIGN, slugs=["taco", "sun"], rng=random.Random(3))
        assert p1 == p2

    def test_slug_choice_restricted_to_pool(self):
        plan = plan_stickers(*BIGSIGN, slugs=["moon"], rng=random.Random(1))
        assert {s.slug for s in plan} == {"moon"}


class TestCoverage:
    def _covers(self, panel_w, panel_h, footprint, seed):
        """Union of every sticker's ROTATED inscribed backing must cover the
        panel. Model the backing as the footprint square rotated about the
        sticker center (the conservative inscribed axis-aligned square)."""
        rng = random.Random(seed)
        plan = plan_stickers(panel_w, panel_h, footprint, ["taco"], rng)
        covered = [[False] * panel_w for _ in range(panel_h)]
        for s in plan:
            a = math.radians(abs(s.angle_deg))
            half = (footprint / (math.cos(a) + math.sin(a))) / 2
            for y in range(max(0, int(s.cy - half)), min(panel_h, int(s.cy + half) + 1)):
                for x in range(max(0, int(s.cx - half)), min(panel_w, int(s.cx + half) + 1)):
                    covered[y][x] = True
        return all(all(row) for row in covered)

    def test_bigsign_covered_across_seeds(self):
        assert all(self._covers(*BIGSIGN, seed=s) for s in range(25))

    def test_smallsign_covered_across_seeds(self):
        assert all(self._covers(*SMALLSIGN, seed=s) for s in range(25))


class TestPacing:
    def test_build_reaches_all_at_half(self):
        assert visible_count(0.0, 30) == 0
        assert visible_count(0.5, 30) == 30
        assert visible_count(0.25, 30) not in (0, 30)  # actually progressive

    def test_peel_reaches_all_at_one(self):
        assert departed_count(0.5, 30) == 0
        assert departed_count(1.0, 30) == 30

    def test_monotonic(self):
        vals = [visible_count(t / 100, 30) for t in range(0, 51)]
        assert vals == sorted(vals)


class TestPixelMath:
    def test_dilate_grows_mask(self):
        m = {(5, 5)}
        assert dilate(m, 1) == {(x, y) for x in (4, 5, 6) for y in (4, 5, 6)}

    def test_rotate_zero_is_identity(self):
        px = {(0, 0): (1, 2, 3), (3, 0): (4, 5, 6)}
        assert rotate_pixels(px, 0.0) == px

    def test_rotate_preserves_colors_and_is_hole_free(self):
        # solid 10x10 block rotated 10 deg must stay a connected solid region:
        # pixel count can't shrink (inverse mapping guarantees no holes)
        px = {(x, y): (9, 9, 9) for x in range(10) for y in range(10)}
        out = rotate_pixels(px, 10.0)
        assert len(out) >= len(px)
        assert set(out.values()) == {(9, 9, 9)}
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --extra dev pytest plugins/flair/tests/test_flair_stickers_plan.py -q`
Expected: FAIL (module doesn't exist).

- [ ] **Step 3: Implement the module**

`plugins/flair/src/led_ticker_flair/flair/stickers.py` (module docstring: sticker-bomb transition, pure math half; cite the spec path):

```python
import math
from dataclasses import dataclass

GRID_OVERLAP = 0.7
JITTER_FRAC = 0.1
TILT_MAX_DEG = 10.0
BACKING_PAD = 1
OUTLINE_PAD = 2


@dataclass(frozen=True)
class Sticker:
    slug: str
    cx: int
    cy: int
    angle_deg: float
    arrive: int
    depart: int


def _smoothstep(p):
    p = min(1.0, max(0.0, p))
    return p * p * (3.0 - 2.0 * p)


def visible_count(t, n):
    """Stickers present during the build phase (t in [0, 0.5])."""
    return round(_smoothstep(t / 0.5) * n)


def departed_count(t, n):
    """Stickers already peeled during the peel phase (t in [0.5, 1])."""
    return round(_smoothstep((t - 0.5) / 0.5) * n)


def plan_stickers(panel_w, panel_h, footprint, slugs, rng):
    cell = max(1, int(footprint * GRID_OVERLAP))
    cols = math.ceil(panel_w / cell)
    rows = math.ceil(panel_h / cell)
    n = cols * rows
    arrive = list(range(n))
    rng.shuffle(arrive)
    depart = list(range(n))
    rng.shuffle(depart)
    out = []
    for i in range(n):
        gx, gy = i % cols, i // cols
        jx = rng.uniform(-JITTER_FRAC, JITTER_FRAC) * cell
        jy = rng.uniform(-JITTER_FRAC, JITTER_FRAC) * cell
        out.append(
            Sticker(
                slug=rng.choice(slugs),
                cx=round(gx * cell + cell / 2 + jx),
                cy=round(gy * cell + cell / 2 + jy),
                angle_deg=rng.uniform(-TILT_MAX_DEG, TILT_MAX_DEG),
                arrive=arrive[i],
                depart=depart[i],
            )
        )
    return out


def dilate(mask, radius):
    out = set()
    for x, y in mask:
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                out.add((x + dx, y + dy))
    return out


def rotate_pixels(pixels, angle_deg):
    """Rotate a {(x, y): (r, g, b)} pixel dict about its bbox center.

    INVERSE mapping (scan the destination, sample the source) — hole-free
    by construction. Plan-time only; per-frame paint iterates the result.
    """
    if not pixels or angle_deg == 0.0:
        return dict(pixels)
    a = math.radians(angle_deg)
    ca, sa = math.cos(a), math.sin(a)
    xs = [p[0] for p in pixels]
    ys = [p[1] for p in pixels]
    cx = (min(xs) + max(xs)) / 2.0
    cy = (min(ys) + max(ys)) / 2.0
    r = (max(xs) - min(xs)) + (max(ys) - min(ys)) + 2  # loose half-diagonal bound
    out = {}
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            sx = round(cx + dx * ca + dy * sa)
            sy = round(cy - dx * sa + dy * ca)
            c = pixels.get((sx, sy))
            if c is not None:
                out[(round(cx) + dx, round(cy) + dy)] = c
    return out
```

(Note `rotate_zero_is_identity` requires the `angle_deg == 0.0` early-out returning the same mapping.)

- [ ] **Step 4: Run to green** — `uv run --extra dev pytest plugins/flair/tests/test_flair_stickers_plan.py -q`. If a coverage seed fails, lower `GRID_OVERLAP` by 0.05 and re-run — do NOT weaken the test.

- [ ] **Step 5: Commit** — `git add plugins/flair/src/led_ticker_flair/flair/stickers.py plugins/flair/tests/test_flair_stickers_plan.py && git commit -m "feat(flair): stickers plan math — grid, pacing, dilation, rotation"`

---

### Task 2: Rasterization — capture, die-cut composition, per-run cache

**Files:**
- Modify: `plugins/flair/src/led_ticker_flair/flair/stickers.py` (append)
- Test: `plugins/flair/tests/test_flair_stickers_raster.py`

**Interfaces:**
- Produces: `capture_sprite(slug, scale, content_height) -> dict[(x,y), (r,g,b)]` (bbox-normalized to origin), `compose_sticker(sprite) -> dict` (die-cut: white rim + black fill + sprite), `StickerRaster` (per-run cache: `get(slug, angle_deg, scale, content_height) -> dict`, quantizing angle to whole degrees).

- [ ] **Step 1: Write the failing tests**

```python
"""Rasterization tests — capture via a recording stub, die-cut, cache."""

from led_ticker_flair.flair.stickers import (
    BACKING_PAD,
    OUTLINE_PAD,
    StickerRaster,
    capture_sprite,
    compose_sticker,
    dilate,
)


class TestCapture:
    def test_lowres_taco_captures_pixels_at_origin(self):
        px = capture_sprite("taco", scale=1, content_height=None)
        assert px, "sprite must capture lit pixels"
        xs = [p[0] for p in px]
        ys = [p[1] for p in px]
        assert min(xs) == 0 and min(ys) == 0, "bbox-normalized to origin"
        assert max(xs) <= 8 and max(ys) <= 8

    def test_hires_taco_is_bigger_than_lowres(self):
        low = capture_sprite("taco", scale=1, content_height=None)
        hi = capture_sprite("taco", scale=4, content_height=16)
        assert len(hi) > len(low) * 4


class TestDieCut:
    def test_compose_layers(self):
        sprite = {(2, 2): (200, 100, 0)}
        out = compose_sticker(sprite)
        assert out[(2, 2)] == (200, 100, 0)                      # sprite on top
        assert out[(1, 1)] == (0, 0, 0)                          # black fill ring
        assert out[(2 - OUTLINE_PAD, 2)] == (255, 255, 255)      # white rim
        fill = dilate({(2, 2)}, BACKING_PAD)
        rim = dilate({(2, 2)}, OUTLINE_PAD) - fill
        assert set(out) == fill | rim | {(2, 2)}


class TestRasterCache:
    def test_angle_quantization_shares_entries(self, monkeypatch):
        calls = []
        import led_ticker_flair.flair.stickers as m

        real = m.capture_sprite
        monkeypatch.setattr(
            m, "capture_sprite", lambda *a, **k: calls.append(a) or real(*a, **k)
        )
        cache = StickerRaster()
        cache.get("taco", 4.4, 1, None)
        cache.get("taco", 3.6, 1, None)  # both quantize to 4 degrees
        assert len(calls) == 1
```

- [ ] **Step 2: Run to verify failure** — same command shape; FAIL on missing names.

- [ ] **Step 3: Implement**

Append to `stickers.py`:

```python
from led_ticker.plugin import ScaledCanvas, draw_emoji_at


class _CaptureReal:
    """Recording stub real canvas: SetPixel into a dict; records EVERY call
    (a sprite may legitimately ink near-black pixels)."""

    def __init__(self, w, h):
        self.width = w
        self.height = h
        self.pixels = {}

    def SetPixel(self, x, y, r, g, b):
        self.pixels[(int(x), int(y))] = (int(r), int(g), int(b))

    def Clear(self):
        self.pixels.clear()


def _normalize(pixels):
    if not pixels:
        return {}
    minx = min(p[0] for p in pixels)
    miny = min(p[1] for p in pixels)
    return {(x - minx, y - miny): c for (x, y), c in pixels.items()}


def capture_sprite(slug, scale, content_height):
    """Rasterize a slug through the real draw path into a pixel dict.

    scale > 1 wraps the stub in the public ScaledCanvas so draw_emoji_at's
    hires dispatch fires; scale == 1 draws the 8x8 form directly. The result
    is bbox-normalized so placement math is anchor-independent.
    """
    if scale > 1:
        real = _CaptureReal(64 * scale, (content_height or 16) * scale)
        canvas = ScaledCanvas(real, scale=scale, content_height=content_height or 16)
    else:
        real = _CaptureReal(64, 16)
        canvas = real
    draw_emoji_at(canvas, slug, 4, 0)
    return _normalize(real.pixels)


def compose_sticker(sprite):
    """Die-cut: sprite ink over black fill (BACKING_PAD) + white rim
    (OUTLINE_PAD ring). Coverage comes from the fill+rim footprint."""
    mask = set(sprite)
    fill = dilate(mask, BACKING_PAD)
    rim = dilate(mask, OUTLINE_PAD) - fill
    out = {p: (0, 0, 0) for p in fill}
    out.update({p: (255, 255, 255) for p in rim})
    out.update(sprite)
    return out


class StickerRaster:
    """Per-run cache of composed, rotated stickers keyed by
    (slug, whole-degree angle, scale, content_height)."""

    def __init__(self):
        self._cache = {}

    def get(self, slug, angle_deg, scale, content_height):
        key = (slug, round(angle_deg), scale, content_height)
        hit = self._cache.get(key)
        if hit is None:
            sprite = capture_sprite(slug, scale, content_height)
            hit = rotate_pixels(compose_sticker(sprite), round(angle_deg))
            self._cache[key] = hit
        return hit
```

Adjust the Task 1 `rotate_pixels` int-degree call compatibility (round() produces int — fine, math.radians accepts it).

- [ ] **Step 4: Run to green**, then run BOTH sticker test files together.
- [ ] **Step 5: Commit** — `git commit -m "feat(flair): sticker rasterization — capture, die-cut, per-run cache"` (with the two files added).

---

### Task 3: The `Stickers` transition class + registration

**Files:**
- Modify: `plugins/flair/src/led_ticker_flair/flair/stickers.py` (append the class)
- Modify: `plugins/flair/src/led_ticker_flair/flair/__init__.py` (import + `api.transition("stickers")(Stickers)`)
- Modify: `plugins/flair/pyproject.toml` (core floor — resolve the actual seam release, see Global Constraints)
- Test: `plugins/flair/tests/test_flair_stickers_transition.py`

**Interfaces:**
- Consumes: Task 1/2 names; `led_ticker.plugin.{SNAP_THRESHOLD, snap_reset, unwrap_to_real, is_scaled, emoji_slugs}`.
- Produces: `Stickers(emoji=None, seed=None)` registered as `transition = "flair.stickers"` (table form for the knob).

- [ ] **Step 1: Write the failing tests** — mirror the package's existing fireworks-transition test file structure (`plugins/flair/tests/test_flair_fireworks*.py` shows the stub-canvas fixtures/idioms to reuse). Required cases, each a real test with pixel/behavior assertions:

```python
class TestKnobValidation:
    def test_unknown_slug_raises_at_construction_naming_it(self):
        with pytest.raises(ValueError, match="fire"):
            Stickers(emoji=["taco", "fire"])

    def test_empty_or_nonlist_rejected(self):
        for bad in ([], "taco", [1], [""]):
            with pytest.raises(ValueError):
                Stickers(emoji=bad)

    def test_known_slugs_accepted(self):
        Stickers(emoji=["taco"])
        Stickers(emoji=["sun", "moon", "heart_red"])


class TestEndpoints:
    def test_t_zero_draws_outgoing_only(self): ...   # outgoing.draw called, no sticker pixels
    def test_snap_draws_incoming_on_bg(self): ...    # t=0.96: snap_reset color + incoming.draw
    def test_full_cover_at_half(self): ...           # t=0.5 on a stub real canvas: EVERY panel
                                                     # pixel painted by sticker layers (the
                                                     # pixel-level coverage proof, both geometries)
    def test_peel_reveals_incoming(self): ...        # t=0.75: incoming.draw called AND some
                                                     # sticker pixels still present

class TestDeterminismAndRefire:
    def test_same_seed_same_frames(self): ...        # two instances seed=5: identical t=0.3 pixels
    def test_refire_replans(self): ...               # t back to 0.1 after 1.0 -> new plan (fireworks
                                                     # _last_t idiom)

class TestPerf:
    def test_no_rasterization_after_first_frame(self, monkeypatch): ...
        # spy capture_sprite; frame_at at t=0.3 then t=0.4: all capture calls
        # happen during the first call (cache warm), zero on the second
```

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement the class** (append to `stickers.py`; Fireworks is the structural template — `min_frames = 24`, lazy plan keyed on `(w, h, scale)`, `_last_t` re-fire, entropy reseed when `seed is None`):

```python
import random
from typing import Any

from led_ticker.plugin import SNAP_THRESHOLD, emoji_slugs, is_scaled, snap_reset, unwrap_to_real


class Stickers:
    """Sticker-bomb: emoji pop on over the outgoing widget until full cover
    at t=0.5, then pop off in an independent random order revealing the
    incoming widget. `emoji=[...]` restricts the slug pool (one slug = a
    themed wall); omitted = random assortment across every drawable slug."""

    min_frames = 24

    def __init__(self, emoji: Any = None, seed: int | None = None) -> None:
        if emoji is not None:
            if (
                not isinstance(emoji, list)
                or not emoji
                or not all(isinstance(s, str) and s for s in emoji)
            ):
                raise ValueError(
                    f"emoji must be a non-empty list of slug strings; got {emoji!r}"
                )
            unknown = sorted(set(emoji) - set(emoji_slugs()))
            if unknown:
                raise ValueError(
                    f"unknown emoji slug(s) {unknown!r} — not in the drawable set. "
                    "Known slugs include taco, sun, moon, star, heart, pride, …"
                )
        self.emoji = list(emoji) if emoji else None
        self.seed = seed
        self._rng = random.Random(seed) if seed is not None else random.Random()
        self._plan = None
        self._plan_key = None
        self._raster = StickerRaster()
        self._last_t = 1.0

    def _ensure_plan(self, canvas):
        scale = canvas.scale if is_scaled(canvas) else 1
        content_height = canvas.content_height if is_scaled(canvas) else None
        real = unwrap_to_real(canvas) if is_scaled(canvas) else canvas
        # Footprint from an actual capture (max bbox side + rim), not a guess.
        pool = self.emoji if self.emoji else list(emoji_slugs())
        probe = capture_sprite(pool[0], scale, content_height)
        side = 1 + max(max(p[0] for p in probe), max(p[1] for p in probe)) if probe else 8
        footprint = side + 2 * OUTLINE_PAD
        key = (real.width, real.height, scale)
        if self._plan is None or self._plan_key != key:
            self._plan = plan_stickers(real.width, real.height, footprint, pool, self._rng)
            self._plan_key = key
            self._geom = (scale, content_height, real)
        return self._plan

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
            self._plan = None  # re-fire: replan from fresh entropy
            self._rng = random.Random()
        self._last_t = t

        plan = self._ensure_plan(canvas)
        scale, content_height, real = self._geom
        n = len(plan)
        if t < 0.5:
            outgoing.draw(canvas, cursor_pos=kwargs.get("outgoing_scroll_pos", 0))
            shown = {s.arrive for s in plan if s.arrive < visible_count(t, n)}
            visible = [s for s in plan if s.arrive in shown]
        else:
            snap_reset(canvas, kwargs.get("incoming_bg_color"))
            incoming.draw(canvas, cursor_pos=0)
            gone = departed_count(t, n)
            visible = [s for s in plan if s.depart >= gone]

        for s in sorted(visible, key=lambda s: s.arrive):  # later arrivals on top
            px = self._raster.get(s.slug, s.angle_deg, scale, content_height)
            if not px:
                continue
            w = max(p[0] for p in px)
            h = max(p[1] for p in px)
            ox, oy = s.cx - w // 2, s.cy - h // 2
            for (x, y), (r, g, b) in px.items():
                tx, ty = ox + x, oy + y
                if 0 <= tx < real.width and 0 <= ty < real.height:
                    real.SetPixel(tx, ty, r, g, b)
        return canvas
```

Register in `plugins/flair/src/led_ticker_flair/flair/__init__.py`: `from led_ticker_flair.flair.stickers import Stickers` + `api.transition("stickers")(Stickers)` next to the fireworks line. Floor bump per Global Constraints.

(Implementation notes for the implementer: (a) `snap_reset(canvas, None)` clears to black — that is the desired peel background when the incoming section has no bg_color, and `t < 0.5` never calls it — the outgoing widget's own draw handles its background; (b) the pool for random mode is snapshotted per plan, so a wall is stable within one firing; (c) match the existing fireworks class for any structural question — it is the reviewed template.)

- [ ] **Step 4: Run the full flair suite to green** — `uv run --extra dev pytest plugins/flair/tests/ -q`, plus lint + pyright per Global Constraints.
- [ ] **Step 5: Commit** — `git commit -m "feat(flair): flair.stickers sticker-bomb transition"` with all touched files.

---

### Task 4: Docs, GIF validation, PR

**Files:**
- Modify: `plugins/flair/README.md` (transitions section: a `flair.stickers` entry with the three config forms from the spec — real slugs only)
- Modify: `plugins/flair/CLAUDE.md` (one invariant paragraph: plan-time rasterization — never rotate per frame; coverage test is the guarantee; knob validation via `emoji_slugs`)
- Test: none new (this task is verification + packaging)

- [ ] **Step 1: README + CLAUDE.md entries.** README shows: taco wall (`{style = "flair.stickers", emoji = ["taco"]}`), mixed set (`emoji = ["sun", "moon", "star_yellow"]`), bare random form, the `seed` knob, and the note that unknown slugs fail at `led-ticker validate` time.
- [ ] **Step 2: GIF-validate (render-path change — mandatory before PR).** In a core-repo checkout with this branch's flair installed (`uv pip install --no-cache --reinstall <monorepo>/plugins/flair`), render three previews via `tools/render_demo/render.py` on throwaway TOMLs (bigsign flat geometry `rows=64 cols=256 chain_length=1 default_scale=4`): (a) taco wall between two message widgets, (b) bare random assortment, (c) smallsign geometry (`rows=16 cols=160 … default_scale=1`) taco wall. Check against `docs/visual-validation.md`: full cover at mid-transition, pop-on/pop-off actually staggered, die-cut rims visible, no stray pixels outside the panel, incoming clean after snap. Attach the gifs to the session for the user.
- [ ] **Step 3: Full monorepo checks** — `uv run --extra dev pytest plugins/flair/tests/ -q`, ruff check + format, pyright.
- [ ] **Step 4: Push + PR.** `git push -u origin flair-stickers`; `gh pr create` (body via file). Body: what/choreography summary, spec path, core-floor note (names the actual core release), the GIF-validation results, AND the standing **"Test on the sign"** section:

```
## Test on the sign

In `config/requirements-plugins.txt`:

    led-ticker-flair @ git+https://github.com/JamesAwesome/led-ticker-plugins.git@flair-stickers#subdirectory=plugins/flair

then `docker compose down -v && docker compose up -d` (the `-v` refresh is required so reconcile reinstalls the branch build).
```

Watch CI to green. Do NOT merge — user go-ahead required.

---

## After both PRs merge (rollout order, from the spec)

1. Core seam PR merges → core release (cut_release.py, minor).
2. Flair PR (floored to that release) merges → `flair-vNext` (minor) via `cut_release.py flair minor`.
3. Separate small core-repo PR: halal-cart Taco Tuesday sections adopt `transition = {style = "flair.stickers", emoji = ["taco"]}` + docs-site flair catalog entry (the #373 pattern).
