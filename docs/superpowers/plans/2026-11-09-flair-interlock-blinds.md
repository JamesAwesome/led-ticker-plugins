# flair.interlock + flair.blinds Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `flair.interlock.*` (4 types) and `flair.blinds.*` (6 types) up to the visual gate: implemented, tested, smoke configs written, and bigsign + smallsign GIFs rendered for James. STOP before any PR.

**Architecture:** Both are snapshot transitions in the laser/accordion mould. Each widget is drawn once per firing into a plugin-local `Raster`, the lit pixels are pre-grouped (by strand+parity for interlock, by slat+depth for blinds), and every frame replays them with a pure function of `t` at physical resolution. Interlock keeps the runner's default `scale_switch_at` (0.5) with a lazy incoming snapshot (accordion). Blinds uses `scale_switch_at = 1.0` with both snapshots up front (laser).

**Tech Stack:** Python 3.14, `led_ticker.plugin` public surface only, pytest, uv workspace (`led-ticker-plugins`).

**Spec:** `docs/superpowers/specs/2026-11-09-flair-interlock-blinds-transitions-design.md`. Read it before starting; this plan argues from it.

**Worktree:** `/Users/james/projects/github/jamesawesome/led-ticker-plugins-interlock-blinds`, branch `spec/flair-interlock-blinds`. Before ANY git op, run `pwd && git branch --show-current` and confirm both. All paths below are relative to that root. Never touch the primary `led-ticker-plugins` checkout.

## Global Constraints

- Import only from `led_ticker.plugin` (plus stdlib / PIL). Enforced by `plugins/flair/tests/test_import_purity.py`.
- No `from __future__ import annotations`.
- No new core seams; core floor unchanged.
- Leave `laser.py`, `accordion*.py` and `_raster.py` untouched.
- All painting is `real.SetPixel` / `real.SubFill` on `unwrap_to_real(canvas)` (or `canvas` when unscaled), re-derived EVERY `frame_at` call, never cached.
- Snap idiom at `t >= SNAP_THRESHOLD` (0.95): `snap_reset(canvas, kwargs.get("incoming_bg_color"))` then `incoming.draw(canvas, cursor_pos=0)`, then return.
- Refire rule (both): `if t == 0.0 or t < self._last_t:` drop plans; then `self._last_t = t`. Equal non-zero `t` is not a refire.
- Snapshot-only: neither widget is drawn live after its snapshot, except the snap draw.
- Outgoing snapshot uses `cursor_pos=kwargs.get("outgoing_scroll_pos", 0)`; incoming uses `0`.
- Lit = `_raster.is_lit` (set and not pure black).
- `interlock.min_frames = 24`; `blinds.min_frames = 16`.
- Knob validation raises `ValueError` for bool / non-int / `< 1` (laser `_coerce_beams` shape).
- Tests: `uv run pytest plugins/flair/tests/<file> -v`. Full gate: `make test`, `make lint`, `make format-check`, `make typecheck` (pyright is pre-push only, so run it explicitly).

## Review Focus

1. **Letterboxed content** (`content_height × scale < panel_h`, e.g. a 128×64 panel at scale 2 / content 16 → `y_offset_real = 16`). Strands must anchor at `y_offset_real`, and letterbox rows must clamp into the first/last strand rather than getting a stray parity. Pinned by `test_strands_anchor_at_y_offset_real_and_clamp_letterbox` (Task 2).
2. **Cross-scale interlock.** The incoming section is at a different scale, and the runner re-wraps the canvas at t ≥ 0.5. The incoming snapshot must come from that frame's canvas. Pinned by `test_incoming_snapshot_is_lazy_from_rewrapped_canvas` (Task 3).
3. **A firing cancelled right after t = 0**, followed by a new firing whose t = 0 must not replay the stale plan. Pinned by `test_t0_always_starts_a_new_firing` (Tasks 3 and 5).
4. **Edge-hugging content** (text flush left or flush right). Content-sized travel must still fully clear and fully enter. Pinned by `test_clear_distance_edge_hugging` (Task 2).
5. **Slat counts that don't divide the panel**, or exceed it (e.g. `slats = 3` on 16 rows, `slats = 100` at scale 4). Boundaries must snap to `scale`, remainder goes to the last slat, and the count clamps to ≥ 1 logical px per slat. Pinned by `test_slat_bounds_remainder_and_clamp` (Task 4).

---

## File map

| File | Responsibility |
|---|---|
| Create `plugins/flair/src/led_ticker_flair/flair/_variants.py` | `Cycling` / `RandomNoRepeat` delegate bases for `.alternating` / `.random` |
| Create `plugins/flair/src/led_ticker_flair/flair/_snapshot.py` | `SnapshotCache` (geometry-keyed Raster reuse + `Geometry` of the live canvas) |
| Create `plugins/flair/src/led_ticker_flair/flair/interlock.py` | interlock pure math + `Interlock*` classes |
| Create `plugins/flair/src/led_ticker_flair/flair/blinds.py` | blinds pure math + `Blinds*` classes |
| Modify `plugins/flair/src/led_ticker_flair/flair/__init__.py` | imports + 10 registrations + module docstring |
| Create `plugins/flair/tests/test_flair_variants.py`, `test_flair_interlock_plan.py`, `test_flair_interlock_transition.py`, `test_flair_blinds_plan.py`, `test_flair_blinds_transition.py` | tests (copy the stub canvas/widget helpers from `test_flair_laser_transition.py`, per the repo's duplication convention) |
| Modify `plugins/flair/CLAUDE.md`, `plugins/flair/README.md` | invariants + user docs |
| Create `plugins/flair/examples/config.interlock-smoke.bigsign.toml`, `config.blinds-smoke.bigsign.toml` | smoke configs |

---

### Task 1: Shared variant + snapshot helpers

**Files:**
- Create: `plugins/flair/src/led_ticker_flair/flair/_variants.py`, `plugins/flair/src/led_ticker_flair/flair/_snapshot.py`
- Test: `plugins/flair/tests/test_flair_variants.py`

**Interfaces:**
- Produces:
  - `class Cycling` with `__init__(self, transitions: list[Any])`, attrs `_transitions`, `_index` (starts `-1`), `_last_t` (starts `1.0`); property `min_frames -> int` (from `_transitions[0]`); `frame_at(t, canvas, outgoing, incoming, **kwargs)` that applies the refire rule to advance `_index = (_index + 1) % n`, then delegates.
  - `class RandomNoRepeat(Cycling)`: same, but `_next_index` picks uniformly from indices `!= _index` using `self._rng = random.Random()`.
  - Both expose `_next_index(self) -> int`, the override point.
  - `@dataclass(frozen=True) class Geometry: width: int; height: int; scale: int; y_offset_real: int; content_h_real: int` (real px), and `def geometry_of(canvas) -> Geometry`. Unscaled canvas: scale 1, y_off 0, content_h = height. Scaled canvas: `canvas.scale`, `canvas.y_offset_real`, `canvas.content_height * canvas.scale`, with dims from `unwrap_to_real(canvas)`.
  - `class SnapshotCache` with `take(self, canvas, widget, cursor_pos: int, slot: int) -> Raster`. Keeps two slots, re-allocates `Raster(real.width, real.height)` only when the `Geometry` changes, then calls `snapshot_into`.

- [ ] **Step 1: Write failing tests** in `test_flair_variants.py`:
  - `test_cycling_advances_on_t0_and_on_t_decrease`: wrap 3 recording fakes. Frames t = 0.0, 0.5, 0.0, 0.3, 0.1 yield delegated indices `[0, 0, 1, 1, 2]`.
  - `test_cycling_equal_nonzero_t_is_not_refire`: t = 0.4, 0.4 gives the same index.
  - `test_random_no_repeat_seeded`: 4 fakes, `_rng.seed(1)`, 30 firings, no back-to-back equal and `len(set) >= 3`.
  - `test_min_frames_forwarded`: `Cycling([obj with min_frames=24])`, so `min_frames == 24`.
  - `test_geometry_unscaled_and_scaled`: `_StubCanvas(160, 16)` gives `Geometry(160, 16, 1, 0, 16)`. `ScaledCanvas(_StubCanvas(128, 64), scale=2, content_height=16)` gives `Geometry(128, 64, 2, 16, 32)`.
  - `test_snapshot_cache_reuses_raster_until_geometry_changes`: two `take` calls on the same canvas and slot return the same `Raster` object; a different-size canvas returns a new one.
- [ ] **Step 2:** Run `uv run pytest plugins/flair/tests/test_flair_variants.py -v`. Expect an ImportError.
- [ ] **Step 3:** Implement both modules to the interfaces above.
- [ ] **Step 4:** Re-run the tests. Expect PASS.
- [ ] **Step 5:** Commit: `feat(flair): shared variant + snapshot helpers for interlock/blinds`.

---

### Task 2: Interlock pure math

**Files:**
- Create: `plugins/flair/src/led_ticker_flair/flair/interlock.py` (math section only)
- Test: `plugins/flair/tests/test_flair_interlock_plan.py`

**Interfaces:**
- Consumes: `Raster`, `Pixel`, `is_lit` (`_raster.py`); `Geometry` (Task 1).
- Produces:
  - `AXES = ("horizontal", "vertical")`
  - `def strand_index(coord: int, anchor: int, strand_px: int, n_strands: int) -> int`: `(coord - anchor) // strand_px`, clamped to `[0, n_strands - 1]`.
  - `def clear_distance(lo: int, hi: int, size: int, toward_positive: bool) -> int`: `size - lo` if `toward_positive` else `hi + 1`. Here `[lo, hi]` is the inclusive lit extent along the travel axis.
  - `def split_offset(t: float, d: int) -> int`: `round(d * min(t / 0.5, 1.0))`.
  - `def mesh_offset(t: float, d: int) -> int`: `round(d * (1 - clamp01((t - 0.5) / (SNAP_THRESHOLD - 0.5))))`.
  - `@dataclass(frozen=True) class InterlockPlan: axis: str; even: list[Pixel]; odd: list[Pixel]; lo: int; hi: int; size: int`. `size` is the real extent along the travel axis (W for horizontal, H for vertical). `lo`/`hi` are `-1` when there's no lit content.
  - `def build_plan(raster: Raster, axis: str, geo: Geometry, strand: int) -> InterlockPlan`:
    - Horizontal strands are row bands: `strand_px = strand * geo.scale`, `anchor = geo.y_offset_real`, `n = ceil(geo.content_h_real / strand_px)`, and the strand is indexed by y. Travel is along x.
    - Vertical strands are column bands: `anchor = 0`, `n = ceil(geo.width / strand_px)`, and the strand is indexed by x. Travel is along y.
    - Parity is `strand_index % 2`.

- [ ] **Step 1: Write failing tests** in `test_flair_interlock_plan.py`:
  - `test_strand_index_scale1_one_row_strands`: anchor 0, px 1, n 16, so rows 0..15 map to 0..15.
  - `test_strand_index_bigsign_four_real_rows`: px 4, anchor 0, n 16, so rows 0-3 map to 0 and row 4 maps to 1.
  - `test_strands_anchor_at_y_offset_real_and_clamp_letterbox`: geo `(128, 64, 2, 16, 32)`, strand 1 (px 2, n 16). Row 16 maps to strand 0, row 18 to 1, row 0 (letterbox above) to 0, row 63 (letterbox below) to 15.
  - `test_clear_distance_centred`: `lo=60, hi=99, size=160` gives `toward_positive=True` → 100 and `False` → 100.
  - `test_clear_distance_edge_hugging`: `lo=0, hi=39, size=160` gives 160 / 40. `lo=120, hi=159` gives 40 / 160.
  - `test_split_offset_endpoints`: `split_offset(0.0, 100) == 0`, `split_offset(0.5, 100) == 100`, `split_offset(0.25, 100) == 50`.
  - `test_mesh_offset_endpoints`: `mesh_offset(0.5, 100) == 100`, `mesh_offset(0.95, 100) == 0`, `mesh_offset(0.725, 100) == 50`.
  - `test_build_plan_splits_parity_and_extent`: a 10×4 raster lit at (2,0), (3,1), (7,2), (2,3) with horizontal axis, scale-1 geo, strand 1. `even` holds the y∈{0,2} pixels, `odd` the y∈{1,3} pixels, `lo == 2`, `hi == 7`, `size == 10`.
  - `test_build_plan_vertical_uses_columns_and_y_extent`: the same raster on the vertical axis gives parity by x, with `lo`/`hi` from y.
  - `test_build_plan_empty`: an all-unlit raster gives empty lists and `lo == hi == -1`.
- [ ] **Step 2:** Run the tests. Expect an ImportError.
- [ ] **Step 3:** Implement to the interfaces.
- [ ] **Step 4:** Run the tests. Expect PASS.
- [ ] **Step 5:** Commit: `feat(flair): interlock strand/travel math`.

---

### Task 3: Interlock transition, variants, registration

**Files:**
- Modify: `plugins/flair/src/led_ticker_flair/flair/interlock.py` (add classes), `plugins/flair/src/led_ticker_flair/flair/__init__.py`
- Test: `plugins/flair/tests/test_flair_interlock_transition.py`

**Interfaces:**
- Consumes: Task 1 (`Cycling`, `RandomNoRepeat`, `SnapshotCache`, `geometry_of`) and Task 2.
- Produces:
  - `class Interlock` with class attrs `min_frames = 24`, `_axis = "horizontal"`, `_even_positive = True`. It does NOT set `scale_switch_at`. `__init__(self, strand: Any = 1)` stores `self.strand`. Attrs `_out_plan`, `_in_plan`, `_last_t = 1.0`, `_cache = SnapshotCache()`.
  - `class InterlockFlipped(Interlock)` (`_even_positive = False`), `class InterlockVertical(Interlock)` (`_axis = "vertical"`), `class InterlockVerticalFlipped(InterlockVertical)` (`_even_positive = False`).
  - `class InterlockAlternating(Cycling)`: `__init__(self, strand=1)` wraps `[Interlock(strand), InterlockVertical(strand)]`.
  - `class InterlockRandom(RandomNoRepeat)`: wraps all four classes.
  - Registered names: `interlock.horizontal` → `Interlock`, `interlock.vertical` → `InterlockVertical`, `interlock.alternating`, `interlock.random`.

`frame_at` algorithm (the spec pins the motion; this is the order):

```
refire rule → snap idiom if t >= 0.95
if _out_plan is None: _out_plan = build_plan(cache.take(canvas, outgoing, pos, 0), axis, geometry_of(canvas), strand)
real = unwrap_to_real(canvas) if is_scaled(canvas) else canvas
if t < 0.5:  plan, phase = _out_plan, "split"
else:        if _in_plan is None: _in_plan = build_plan(cache.take(canvas, incoming, 0, 1), ...)   # lazy, this frame's canvas
             plan, phase = _in_plan, "mesh"
for parity, pixels in ((0, plan.even), (1, plan.odd)):
    sign = +1 if (parity == 0) == _even_positive else -1          # direction of travel, same in both phases (conveyor)
    if phase == "split": shift = sign * split_offset(t, clear_distance(lo, hi, size, toward_positive=sign > 0))
    else:                shift = -sign * mesh_offset(t, clear_distance(lo, hi, size, toward_positive=sign < 0))
    paint each pixel shifted along the travel axis; skip off-panel
```

- [ ] **Step 1: Write failing tests** in `test_flair_interlock_transition.py`. Copy `_StubCanvas`, `_make_widget`, `_text_widget` and `_image_widget` from the laser test.
  - `test_t0_paints_outgoing_unshifted`.
  - `test_split_moves_even_right_odd_left`: on a 20×2 canvas with a pixel at (5,0) and one at (5,1), at t = 0.25 row 0's pixel is at x > 5 and row 1's at x < 5.
  - `test_flipped_reverses_parity_directions`.
  - `test_mesh_conveyor_even_enters_from_left`: incoming pixel at (5,0). Shortly after 0.5 it is at x < 5, and it reaches x == 5 by t = 0.949.
  - `test_only_t_half_is_empty_for_centred_content`: content centred on 160×16. Frames at t = 0.48 and 0.52 each paint ≥ 1 lit pixel; t = 0.5 paints none.
  - `test_vertical_moves_along_y`.
  - `test_snap_draws_incoming_over_bg` (monkeypatch `snap_reset` as in laser).
  - `test_outgoing_not_drawn_live_after_snapshot`: `outgoing.draw.call_count == 1` after frames 0.0 through 0.45.
  - `test_incoming_snapshot_is_lazy_from_rewrapped_canvas`: `incoming.draw` is not called at t < 0.5. At t = 0.5 pass a NEW `ScaledCanvas(real, scale=2, content_height=16)` where earlier frames used scale 4; the incoming draw receives a wrapper with `scale == 2`.
  - `test_t0_always_starts_a_new_firing`: call at t = 0.0, then t = 0.0 again with a different outgoing widget; the second plan reflects the new widget.
  - `test_equal_t_is_not_a_refire`.
  - `test_image_widget_snapshots_through_setimage`.
  - `test_strand_validation` (parametrize `0, -1, True, 1.5, "2"`), plus `test_multi_variants_forward_strand`.
  - `test_registration_four_types_distinct_instances` (laser's registration test shape, with `api.background` also stubbed).
  - `test_alternating_cycles_horizontal_vertical` and `test_random_never_repeats_back_to_back` (seeded, ≥ 3 distinct of the 4).
  - `test_min_frames_24_on_every_type`.
  - `TestPerfUniformity`: per-frame SetPixel count ≤ 1.5 × panel px on 160×16 text, on a 256×64 scale-4 full fill, and on an alternating refire (laser's three tests).
  - `TestRealCoreWidgets`: `TickerMessage(text="INTERLOCK")` at scale 1 and through a scale-4 `ScaledCanvas`. The lit pixel set at t = 0.949 is at most 2 strands' worth off the snap frame's set; in practice `mesh_offset(0.949)` is 0 or 1 px, so assert each painted colour ⊆ the snap palette and ≥ 90% position overlap.
- [ ] **Step 2:** Run the tests. Expect FAIL.
- [ ] **Step 3:** Implement the classes. Add the registrations and imports to `flair/__init__.py` after the accordion block, and update its docstring to mention `flair.interlock.<axis>`.
- [ ] **Step 4:** Run the interlock tests plus `test_import_purity.py` and `test_smoke.py`. Expect PASS.
- [ ] **Step 5:** Commit: `feat(flair): flair.interlock transition (horizontal/vertical/alternating/random)`.

---

### Task 4: Blinds pure math

**Files:**
- Create: `plugins/flair/src/led_ticker_flair/flair/blinds.py` (math section only)
- Test: `plugins/flair/tests/test_flair_blinds_plan.py`

**Interfaces:**
- Produces:
  - `DIRECTIONS = ("down", "up", "right", "left")`
  - `DEFAULT_SLATS = {"horizontal": 4, "vertical": 8}`
  - `def orientation(direction: str) -> str`: down/up map to `"horizontal"`, left/right to `"vertical"`.
  - `def slat_bounds(size: int, slats: int, scale: int) -> list[tuple[int, int]]` returns half-open `[lo, hi)` real-px bounds covering `[0, size)`:
    1. `slats = min(slats, size // scale)`, which ensures ≥ 1 logical px each (minimum 1).
    2. `base = (size // scale // slats) * scale`.
    3. Each slat is `base` wide and the last one absorbs the remainder.
  - `def revealed(p: float, lo: int, hi: int) -> int`: `round(p * (hi - lo))`.
  - `@dataclass(frozen=True) class BlindsPlan: bounds: list[tuple[int, int]]; out_px: list[tuple[int, int, int, int, int, int, int]]; in_px: ...`. Each entry is `(x, y, r, g, b, slat, depth)`, where `depth` is the distance from the slat's leading edge: `y - lo` for down, `hi - 1 - y` for up, `x - lo` for right, `hi - 1 - x` for left.
  - `def build_plan(out_r: Raster, in_r: Raster, direction: str, slats: int, geo: Geometry) -> BlindsPlan`. Slats run along y for horizontal orientation (`size = geo.height`) and along x for vertical (`size = geo.width`).
  - A pixel is revealed iff `depth < revealed(p, *bounds[slat])`.

- [ ] **Step 1: Write failing tests** in `test_flair_blinds_plan.py`:
  - `test_slat_bounds_smallsign_defaults`: `slat_bounds(16, 4, 1)` gives `[(0,4),(4,8),(8,12),(12,16)]`, and `slat_bounds(160, 8, 1)` gives eight 20-px slats.
  - `test_slat_bounds_bigsign_snap_to_scale`: `slat_bounds(64, 4, 4)` gives 16-px slats, and `slat_bounds(256, 8, 4)` gives 32-px slats.
  - `test_slat_bounds_remainder_and_clamp`: `slat_bounds(16, 3, 1)` gives `[(0,5),(5,10),(10,16)]`; `slat_bounds(64, 3, 4)` gives `[(0,20),(20,40),(40,64)]` (multiples of 4); `slat_bounds(64, 100, 4)` gives 16 slats of 4.
  - `test_revealed_endpoints`: `revealed(0, 0, 16) == 0` and `revealed(1, 0, 16) == 16`.
  - `test_depth_per_direction`: on a 4-row slat `(4, 8)`, a pixel at y = 5 has depth 1 for down and 2 for up; the same check on x for right/left.
  - `test_build_plan_only_lit_pixels`: unlit and black pixels are excluded from both lists.
  - `test_orientation_mapping`.
- [ ] **Step 2:** Run the tests. Expect FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the tests. Expect PASS.
- [ ] **Step 5:** Commit: `feat(flair): blinds slat math`.

---

### Task 5: Blinds transition, variants, registration

**Files:**
- Modify: `plugins/flair/src/led_ticker_flair/flair/blinds.py`, `plugins/flair/src/led_ticker_flair/flair/__init__.py`
- Test: `plugins/flair/tests/test_flair_blinds_transition.py`

**Interfaces:**
- Produces:
  - `class Blinds` with `min_frames = 16`, `scale_switch_at = 1.0`, `_direction = "down"`, and `__init__(self, slats: Any = None)`. `None` means `DEFAULT_SLATS[orientation(self._direction)]`; anything else is validated.
  - `BlindsUp` / `BlindsRight` / `BlindsLeft` subclasses.
  - `BlindsAlternating(Cycling)` over `[Blinds, BlindsRight, BlindsUp, BlindsLeft]` (down → right → up → left), forwarding `slats`.
  - `BlindsRandom(RandomNoRepeat)` over the same four.
  - Registered names: `blinds.down` / `.up` / `.right` / `.left` / `.alternating` / `.random`.

`frame_at` order:
1. Apply the refire rule, then the snap idiom.
2. Build the plan from both snapshots on the first frame.
3. `p = min(t, 0.95) / 0.95`.
4. Per slat, `SubFill` its revealed band with `incoming_bg_color` (or `(0, 0, 0)` when `None`). The band covers the full other axis.
5. SetPixel the revealed `in_px`.
6. SetPixel the unrevealed `out_px`.

- [ ] **Step 1: Write failing tests** in `test_flair_blinds_transition.py`, using the same copied helpers:
  - `test_t0_outgoing_only_no_subfill_area`.
  - `test_mid_frame_down_reveals_top_of_each_slat`: on 4×16 with 4 slats at t = 0.475 (p = 0.5), rows 0-1 of each slat show incoming and rows 2-3 show outgoing.
  - `test_up_reveals_bottom_of_each_slat`.
  - `test_right_and_left_use_columns`.
  - `test_revealed_band_gets_incoming_bg`: SubFill is called with `incoming_bg_color=(10, 20, 30)` over the revealed rows.
  - `test_revealed_band_black_when_incoming_bg_none`.
  - `test_snap_draws_incoming_over_bg`.
  - `test_outgoing_not_drawn_live_after_snapshot`.
  - `test_t0_always_starts_a_new_firing` and `test_equal_t_is_not_a_refire`.
  - `test_image_widget_snapshots_through_setimage`.
  - `test_default_slats_by_orientation`: `Blinds()` resolves to 4 and `BlindsRight()` to 8. `BlindsAlternating()` sub-instances get 4/8/4/8; with `BlindsAlternating(slats=6)` all four get 6.
  - `test_slats_validation` (parametrize `0, -1, True, 1.5, "4"`).
  - `test_registration_six_types_distinct_instances`, `test_alternating_cycles_down_right_up_left`, `test_random_never_repeats_back_to_back`, `test_min_frames_16_on_every_type`, `test_scale_switch_at_is_1`.
  - `TestPerfUniformity`: SetPixel calls ≤ 1.5 × panel px per frame, with each SubFill counted as one call. Count via a stub whose `SubFill` appends ONE entry, for these tests only. Same three cases as laser.
  - `TestRealCoreWidgets`: `TickerMessage(text="BLINDS")` at scale 1 and scale 4. At t = 0.949 (p ≈ 1) the painted lit set equals the snap frame's lit set.
- [ ] **Step 2:** Run the tests. Expect FAIL.
- [ ] **Step 3:** Implement the classes and registration, and extend the `__init__` docstring with `flair.blinds.<direction>`.
- [ ] **Step 4:** Run the blinds tests plus `test_import_purity.py` and `test_smoke.py`. Expect PASS.
- [ ] **Step 5:** Commit: `feat(flair): flair.blinds transition (down/up/left/right/alternating/random)`.

---

### Task 6: Docs + invariants + full gate

**Files:**
- Modify: `plugins/flair/CLAUDE.md`
  - Update the namespace line 3 to add `flair.interlock.*`, `flair.blinds.*`.
  - Add two sections, `## flair.interlock transition invariants (...)` and `## flair.blinds transition invariants (...)`, in laser-section shape. One bullet per Global Constraint that applies, plus: content-sized travel with the t = 0.5 single empty frame; conveyor direction; strand anchor and clamp; lazy incoming (interlock); `scale_switch_at = 1.0` with both snapshots and the incoming bg SubFill (blinds); slat snapping; default slats per orientation. Each bullet names its tripwire test.
  - Add a `_variants.py` / `_snapshot.py` note: shared by interlock and blinds only; laser and accordion keep their own.
- Modify: `plugins/flair/README.md`. Add `## Interlock transition` and `## Blinds transition` after the laser section, each with Config / Knobs / Notes in the laser shape.
  - Omit the GIF image line for now; the GIFs land after the visual gate.
  - Recommended durations: interlock `duration = 1.5`, blinds `duration = 1.0`.

- [ ] **Step 1:** Write both doc changes.
- [ ] **Step 2:** Run `make test && make lint && make format-check && make typecheck`. Expect all green and pyright at 0 errors.
- [ ] **Step 3:** Commit: `docs(flair): interlock + blinds README and invariants`.

---

### Task 7: Smoke configs, perf sweep, visual-gate GIFs (HARD STOP)

**Files:**
- Create: `plugins/flair/examples/config.interlock-smoke.bigsign.toml` and `config.blinds-smoke.bigsign.toml`. Copy the laser smoke header/display block. Each section uses two `message` widgets (`font = "Inter-Bold"`, `font_size = 30`) and `[transitions] duration` = 1.5 for interlock or 1.0 for blinds.
  - Interlock sections: `1 HORIZONTAL`, `2 VERTICAL`, `3 ALTERNATING` (≥ 4 widgets so two firings show), `4 RANDOM`, `5 BG HOLD` (a TEAL `bg_color` section, then a PURPLE one), `6 BORDER` (a message with `border = "rainbow"`), `7 TWO ROW` (`type = "two_row"`), `8 FULL PANEL` (a `gif` widget on `assets/phoenix.gif`), `9 EMPTY ENTRY`, and `10 STRAND 2` (`transition = {type = "flair.interlock.horizontal", strand = 2}`).
  - Blinds sections: `1 DOWN`, `2 UP`, `3 RIGHT`, `4 LEFT`, `5 ALTERNATING`, `6 RANDOM`, `7 BG HOLD`, `8 BORDER`, `9 TWO ROW`, `10 FULL PANEL`, `11 SLATS 8` (horizontal with `slats = 8`).
- Scratchpad (not committed): render-geometry copies of each smoke config (`rows = 64`, `cols = 256`, `chain_length = 1`, no `pixel_mapper_config`), plus smallsign variants (`rows = 16`, `cols = 32`, `chain_length = 5`, `default_scale = 1`, BDF fonts, no `font`/`font_size`).

- [ ] **Step 1:** Write the two smoke configs. Validate each from core with `cd ../led-ticker && PYTHONPATH=. uv run --project ../led-ticker-plugins led-ticker validate --config <path>`. Expect "No issues found".
- [ ] **Step 2: Perf sweep** (scratchpad script). Run fresh and refire on 256×64 scale 4, with a text case and a full-panel-fill case, timing every `frame_at` over t ∈ [0, 1) in 0.02 steps. Record avg and worst ms per transition. Gate: worst ≤ 5 × avg, excluding only interlock's t = 0.5 lazy snapshot frame, which must stay ms-class. Save the numbers for the PR body.
- [ ] **Step 3:** Commit the smoke configs: `test(flair): interlock + blinds bigsign smoke configs`.
- [ ] **Step 4: Render GIFs.** Plan durations with `make plan-gif` (via the `making-a-gif` skill). Render from core: `cd ../led-ticker && PYTHONPATH=. uv run --project ../led-ticker-plugins python tools/render_demo/render.py <toml> -o <scratchpad>/<name>.gif --duration N`. Produce four GIFs: interlock and blinds, each on bigsign and smallsign.
- [ ] **Step 5:** Extract one or two key frames per GIF to PNG (mid-split and mid-mesh for interlock; p ≈ 0.5 for blinds) and Read them to sanity-check before showing James.
- [ ] **Step 6: HARD STOP.** Show James the GIF paths and the perf numbers. List the tuning surface from the spec: exit direction, the bigsign `strand` default, ring behaviour, `slats` defaults, `min_frames`, durations. Do not open a PR.
