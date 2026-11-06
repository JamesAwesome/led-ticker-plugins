# flair.accordion Transition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `flair.accordion.sweep` and `flair.accordion.stretch`, two transitions where content bunches into an occluding card-fan deck that slides off, and the incoming deck fans out while it slides in.

**Architecture:**
- Each widget is snapshotted once per firing into a readable raster, using laser's `_Raster` lifted into a shared module.
- The snapshot is split into cards along blank real columns, per row band and inside any border ring.
- Pure position functions map phase progress to card positions.
- A per-band column-owner compositor paints only the topmost card in each column.

**Tech Stack:** Python 3.14, led-ticker plugin API (`led_ticker.plugin` only), pytest, uv workspace.

**Spec:** `docs/superpowers/specs/2026-11-03-flair-accordion-transition-design.md`. Read it first; this plan argues from it.

**Worktree:** `/Users/james/projects/github/jamesawesome/led-ticker-plugins-accordion`, branch `feat/flair-accordion`. Before ANY git op, verify `pwd` and `git branch --show-current`. Never work in the primary `led-ticker-plugins` checkout.

## Global Constraints

- Imports only from `led_ticker.plugin` (plus stdlib/PIL). `tests/test_import_purity.py` enforces this.
- No `from __future__ import annotations`.
- No new core seams, and no core floor bump.
- Type strings: `flair.accordion.sweep`, `flair.accordion.stretch`. Registered as `api.transition("accordion.sweep")` and `api.transition("accordion.stretch")`.
- Knob `direction`: `"left"` (default) or `"right"`. Any other value raises `ValueError` at construction.
- `min_frames = 30`.
- Keep the runner's default `scale_switch_at` (do NOT set it).
- Peek `P = 2 × scale` real px.
- `P_eff = min(P, (slot_{n−1} − slot_0) / (n − 1))` per deck, with `P_eff = P` for `n ≤ 1`.
- Timeline:
  - outgoing phase `[0, 0.475)` with `k = t/0.475`
  - beat `[0.475, 0.5)` paints nothing
  - incoming phase `[0.5, 0.95)` with `k = (t−0.5)/0.45`
  - `t ≥ SNAP_THRESHOLD`: `snap_reset(canvas, kwargs.get("incoming_bg_color"))`, then a live `incoming.draw(canvas, cursor_pos=0)`.
- No internal easing: `k` is linear in the `t` received.
- Lit means set and not `(0, 0, 0)`.
- Outgoing snapshot uses `cursor_pos=kwargs.get("outgoing_scroll_pos", 0)`. The outgoing widget is never drawn live after its snapshot.
- Incoming snapshot is lazy, taken on the first frame with `t ≥ 0.5`, from the canvas passed THAT call.
- Refire is `t < self._last_t`; equal `t` is not a refire. Re-derive `real` every call and never cache it.
- Perf: per-frame SetPixel ≤ 1.5 × panel px.
- Run tests from the worktree root: `uv run pytest plugins/flair/tests/<file> -v`. Lint: `make lint` (ruff + pyright).

## Review Focus

1. **Outgoing scrolled partly off-panel** (`slot_0 < 0`, or the last card is clipped at `W`): t≈0 must equal the snapshot pixel for pixel, with no SetPixel out of bounds. This is pinned in Task 4 (`test_t0_matches_snapshot_clipped_content`).
2. **Both widgets blank**: no crash, and zero SetPixels except at the snap. Pinned in Task 5 (`test_both_empty_paints_nothing`).
3. **Dithered or sparse image yielding ≥ 100 one-column cards on the bigsign**: `P_eff` shrinks and per-frame paint stays within bound. Pinned in Task 6 (`test_many_tiny_cards_bounded`).
4. **Canvas geometry changes between firings** (hot-reload smallsign→bigsign dims): rasters re-allocate and cards come out at the new dims. Pinned in Task 5 (`test_geometry_change_reallocates`).
5. **`direction="right"` with border + two-row combined**: the ring stays static, both decks mirror, and no card crosses the band boundary. Pinned in Task 5 (`test_right_border_two_row_combined`).

---

### Task 1: Lift `_Raster` into a shared private module

**Files:**
- Create: `plugins/flair/src/led_ticker_flair/flair/_raster.py`
- Modify: `plugins/flair/src/led_ticker_flair/flair/laser.py` (remove `_Raster`, `_is_lit`, `_BLACK`, `Pixel`; import them from `_raster`)
- Test: existing `plugins/flair/tests/test_flair_laser_*.py`

**Interfaces:**
- Produces:
  - `_raster.Raster` (renamed from `_Raster`, same methods: `SetPixel`, `SubFill`, `Clear`, `Fill`, `SetImage`, `get`, plus `width`/`height`)
  - `_raster.is_lit(px) -> bool`
  - `_raster.Pixel = tuple[int, int, tuple[int, int, int]]`
  - `_raster.snapshot_into(raster: Raster, canvas: Any, widget: Any, cursor_pos: int) -> None`: clears the raster, then draws `widget` through `ScaledCanvas(raster, scale=canvas.scale, content_height=canvas.content_height)` when `is_scaled(canvas)`, else directly. This is extracted from `Laser._snapshot`'s draw half.
- Keep the alias `_Raster = Raster` and `_is_lit = is_lit` in `laser.py` if its tests import those names.

- [ ] **Step 1:** Move the code. `Laser._snapshot` keeps its raster cache and calls `snapshot_into`.
- [ ] **Step 2:** Run `uv run pytest plugins/flair/tests/test_flair_laser_plan.py plugins/flair/tests/test_flair_laser_transition.py -q`. Expected: all pass, unchanged count.
- [ ] **Step 3:** Commit: `refactor(flair): lift laser raster into shared _raster module`.

---

### Task 2: Card segmentation, bands, border ring, adaptive peek

**Files:**
- Create: `plugins/flair/src/led_ticker_flair/flair/accordion_cards.py`
- Test: `plugins/flair/tests/test_flair_accordion_plan.py`

**Interfaces:**
- Consumes: `Raster`, `is_lit`, `Pixel` (Task 1).
- Produces:

```python
@dataclass(frozen=True)
class Card:
    slot: int                                   # natural left column, real px (mirrored space if mirror)
    width: int
    pixels: tuple[tuple[int, int, tuple[int, int, int]], ...]  # (dx, y_real, rgb)

@dataclass(frozen=True)
class Deck:
    cards: tuple[Card, ...]                     # natural left-to-right order
    peek: float                                 # P_eff

def segment_cards(raster: Raster, rows: range, cols: range, *, mirror: bool) -> list[Card]
def effective_peek(cards: Sequence[Card], peek: int) -> float
def ring_depth(widget: Any, raster: Raster) -> int
def ring_pixels(raster: Raster, depth: int) -> list[Pixel]
def band_rows(widget: Any, canvas: Any, real_h: int, depth: int) -> list[range]
def build_decks(raster: Raster, widget: Any, canvas: Any, *, mirror: bool) -> tuple[list[Deck], list[Pixel]]
```

Semantics:
- `segment_cards`:
  - Scans `cols` only, examining only `rows`. A card is a maximal run of columns with ≥1 lit pixel in `rows`.
  - When `mirror=True`, column `c` is read as `W−1−c` (`W = raster.width`), so slots and `dx` live in mirrored space.
- `ring_depth`:
  - `0` if `getattr(widget, "border", None) is None`.
  - Else `border.thickness` if it is an `int`.
  - Else (LightbulbBorder, unknown shapes) measure from the raster: the count of leading top rows, capped at `raster.height // 4`, in which ≥ 50% of columns are lit.
- `ring_pixels`: lit pixels whose x or y lies within `depth` of any edge, in real coords.
- `band_rows`:
  - Two-row means `getattr(widget, "bottom_text", "")` is truthy.
  - For two-row: `top_h, _ = resolve_band_heights(content_h, getattr(widget, "top_row_height", None))`, where `content_h = canvas.content_height if is_scaled(canvas) else real_h`. The boundary row is `y_off + top_h * scale`, with `y_off = canvas.y_offset_real` when scaled, else 0.
  - Returns `[range(depth, boundary), range(boundary, real_h − depth)]` for two-row, else `[range(depth, real_h − depth)]`.
- `build_decks`:
  - Computes `depth` and the ring.
  - Builds one `Deck` per band, with `cols = range(depth, W − depth)`.
  - Uses `peek = effective_peek(cards, 2 * scale)`.
  - Returns `(decks, ring)`.

- [ ] **Step 1: Write failing tests** in `test_flair_accordion_plan.py`, building rasters directly with `Raster.SetPixel`:
  - `test_blank_columns_split_cards`: lit columns {2,3}, {6}, {9,10,11} → slots `[2, 6, 9]`, widths `[2, 1, 3]`.
  - `test_touching_glyphs_merge`: lit columns 2–7 contiguous → one card, slot 2, width 6.
  - `test_full_width_image_is_one_card`: every column lit → 1 card, slot 0, width `W`.
  - `test_black_and_unset_unlit`: a column of only `(0,0,0)` is a gap.
  - `test_empty_raster_no_cards`: `[]`.
  - `test_mirror_reverses_slots`: lit {0,1} on a W=10 raster with `mirror=True` → slot 8, width 2.
  - `test_effective_peek_caps_to_avg_spacing`: slots `[0, 3, 6]`, peek 8 → `3.0`. One card → `8`.
  - `test_ring_depth_from_thickness`: border mock with `thickness=2` → 2. `border=None` → 0.
  - `test_ring_depth_measured_without_thickness`: border object without `thickness`, raster with the top 3 rows fully lit → 3.
  - `test_bordered_inset_splits`: 1-px ring lit around a 20×8 raster, plus inset columns {5}, {9} → 2 cards. Ring pixels = the perimeter count.
  - `test_two_row_bands_split_at_boundary`: widget with `bottom_text="x"`, `top_row_height=None`, scale-1 16-high canvas → bands `[range(0,8), range(8,16)]`. A column lit only in rows 2 and 12 yields one card in EACH deck.
  - `test_two_row_bands_scaled`: `ScaledCanvas(Raster(256,64), scale=4, content_height=16)` → boundary 32.
- [ ] **Step 2:** Run `uv run pytest plugins/flair/tests/test_flair_accordion_plan.py -v`. Expected: FAIL (module missing).
- [ ] **Step 3:** Implement `accordion_cards.py`. `segment_cards` is a single pass over columns, collecting per-column lit pixels.
- [ ] **Step 4:** Re-run. Expected: PASS.
- [ ] **Step 5:** Commit: `feat(flair): accordion card segmentation, bands, border ring`.

---

### Task 3: Motion functions

**Files:**
- Create: `plugins/flair/src/led_ticker_flair/flair/accordion_motion.py`
- Test: `plugins/flair/tests/test_flair_accordion_plan.py` (append)

**Interfaces:**
- Consumes: `Deck`, `Card` (Task 2).
- Produces (all return one float x position per card, in the deck's own coordinate space; `k ∈ [0, 1]`; `W` = panel real width):

```python
def sweep_out(deck: Deck, W: int, k: float) -> list[float]
def sweep_in(deck: Deck, W: int, k: float) -> list[float]
def stretch_out(deck: Deck, W: int, k: float) -> list[float]
def stretch_in(deck: Deck, W: int, k: float) -> list[float]
```

Formulas (spec "Motion math"), with `P = deck.peek`, `s_i = slot_i` and `w_i = width_i`:
- `sweep_out`:
  - `g = lerp(g0, g1, k)`, `pos_i = min(s_i, g + i·P)`
  - `g0 = max(W − (n−1)·P, max_i(s_i − i·P))`
  - `g1 = −max_i(i·P + w_i) − 1`
- `sweep_in`:
  - `h = lerp(W, h1, k)`, `pos_i = max(s_i, h + i·P)`
  - `h1 = min_i(s_i − i·P)`
- `stretch_out`:
  - `a = lerp(s_0, a1, k)`, `s = 1 − k`, `pos_i = a + lerp(i·P, s_i − s_0, s)`
  - `a1 = −max_i(i·P + w_i) − 1`
- `stretch_in`:
  - `a = lerp(W, s_0, k)`, `s = k`, same `pos_i`.
- Empty deck → `[]`.

- [ ] **Step 1: Write failing tests** (decks built from literal `Card`s):
  - `test_out_k0_is_slots` (both motions): positions == slots.
  - `test_out_k1_offscreen` (both): `pos_i + w_i ≤ 0` for all i.
  - `test_in_k0_offscreen` (both): `pos_i ≥ W` for all i.
  - `test_in_k1_is_slots` (both): positions == slots. Include a dense deck (slots `[0,2,4,6]`, P=8 → P_eff=2).
  - `test_continuity`: for both motions and both phases, sampling k in steps of 0.01, `|Δpos_i| ≤ (|Δ anchor| + P) + 1e-9` for each step. This bounds the per-step move by anchor travel, so a jump fails.
  - `test_sweep_in_lands_right_to_left`: slots `[0,10,20]`, P=2. The first k at which each card reaches its slot is strictly decreasing in i.
  - `test_t0_matches_snapshot_clipped_content`: slots `[-3, 150]`, widths `[6, 8]`, W=160 → `sweep_out(k=0)` and `stretch_out(k=0)` equal the slots.
  - `test_stacked_never_wider_than_fanned`: dense deck → stacked width `(n−1)·P_eff + w_last ≤ s_last + w_last − s_0`.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement `accordion_motion.py`.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Commit: `feat(flair): accordion sweep/stretch motion functions`.

---

### Task 4: Occluding compositor

**Files:**
- Create: `plugins/flair/src/led_ticker_flair/flair/accordion_compose.py`
- Test: `plugins/flair/tests/test_flair_accordion_plan.py` (append)

**Interfaces:**
- Consumes: `Deck` (Task 2) and the positions lists (Task 3).
- Produces:

```python
def compose(deck: Deck, positions: Sequence[float], W: int, set_px: Callable[[int, int, int, int, int], None], *, mirror: bool) -> None
```

Algorithm:
- Round each position (`round()`).
- Fill a length-`W` owner array, iterating cards in index order so a higher index overwrites lower ones, over `[x_i, x_i + w_i) ∩ [0, W)`.
- Then, for each card, paint each pixel `(dx, y, rgb)` at `x = x_i + dx` only if `0 ≤ x < W` and `owner[x] == i`.
- Under `mirror`, the painted column is `W − 1 − x`.
- Never paint anything else. Bg shows through.

- [ ] **Step 1: Write failing tests** (with a recording `set_px`):
  - `test_top_card_occludes`: two 4-wide fully lit cards, red at x=0 and blue at x=2 → columns 0–1 red, 2–5 blue, nothing in column 2 from red.
  - `test_unlit_top_cells_paint_nothing`: the top card covers columns but has no pixel at (col, y) → no call for (col, y), even though the buried card has one there.
  - `test_offscreen_clipped`: position −2 → no x < 0 or x ≥ W calls.
  - `test_mirror_maps_columns`: W=10, card at mirrored x 0 → painted at column 9.
  - `test_t0_matches_snapshot_clipped_content`: segment a raster with content clipped at both edges, then compose at `sweep_out(k=0)`. The painted set equals the raster's lit set inside the deck rows/cols.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Commit: `feat(flair): accordion column-owner occluding compositor`.

---

### Task 5: Transition classes and registration

**Files:**
- Create: `plugins/flair/src/led_ticker_flair/flair/accordion.py`
- Modify: `plugins/flair/src/led_ticker_flair/flair/__init__.py` (import + two `api.transition(...)` lines after the laser block)
- Test: `plugins/flair/tests/test_flair_accordion_transition.py`. Copy `_StubCanvas`, `_text_widget`, `_image_widget` from `test_flair_laser_transition.py`; per-file duplication is this repo's convention.

**Interfaces:**
- Consumes: Tasks 1–4.
- Produces:
  - `class _Accordion`:
    - `min_frames = 30`
    - `__init__(self, direction: Any = "left")`
    - `frame_at(self, t, canvas, outgoing, incoming, **kwargs) -> Canvas`
    - abstract `_out(deck, W, k)` / `_in(deck, W, k)`
  - `AccordionSweep(_Accordion)` binds `sweep_out`/`sweep_in`.
  - `AccordionStretch(_Accordion)` binds `stretch_out`/`stretch_in`.

`frame_at` flow:
1. Refire check.
2. If `t ≥ SNAP_THRESHOLD`: snap.
3. Ensure the outgoing snapshot and decks, taken once per firing.
4. If `t < 0.475`: compose each outgoing deck at `_out(k)`, then paint the outgoing ring.
5. If `0.475 ≤ t < 0.5`: nothing.
6. Else (`0.5 ≤ t < SNAP_THRESHOLD`): ensure the incoming snapshot and decks (lazily, from this call's canvas), compose at `_in(k)`, then paint the incoming ring.

Painting rules:
- All painting goes to `real = unwrap_to_real(canvas) if is_scaled(canvas) else canvas`, re-derived each call.
- `mirror = direction == "right"`.
- Raster cache key `(real.width, real.height, scale, content_height)`. Re-allocate on change.

- [ ] **Step 1: Write failing tests:**
  - `test_bad_direction_raises`: `AccordionSweep(direction="up")` → `ValueError`.
  - `test_registration_two_types_distinct_instances`: mirror laser's `test_registration_six_types_distinct_instances` for `accordion.sweep` / `accordion.stretch`.
  - `test_t0_shows_outgoing_only` (both classes): painted set == outgoing pixels.
  - `test_beat_paints_nothing`: `t=0.48` → no SetPixel calls.
  - `test_incoming_not_drawn_before_half`: frames at t < 0.5 → `incoming.draw.call_count == 0`. The first `t ≥ 0.5` → 1.
  - `test_outgoing_not_drawn_live_after_snapshot`: across 20 frames, `outgoing.draw.call_count == 1`.
  - `test_snap_resets_and_draws_live`: `t=0.96` with `incoming_bg_color=(1,2,3)` → `snap_reset` patched and called with `(canvas, (1,2,3))`, plus a live incoming draw.
  - `test_end_of_incoming_phase_equals_slots`: `t=0.9499` → painted set == incoming lit set (no snap jump).
  - `test_refire_resnapshots`: run to 0.96, then `t=0.1` with a changed outgoing → the new pixels are painted. Equal `t` twice is not a refire.
  - `test_scaled_peek_is_8_real_px`: `ScaledCanvas(_StubCanvas(256,64), scale=4, content_height=16)` → the decks' peek is `8` for well-spaced cards.
  - `test_cross_scale_incoming_snapshot_uses_new_wrapper`: pass a scale-2 wrapper before 0.5 and a scale-4 wrapper at 0.5 → the incoming raster key has scale 4.
  - `test_image_widget_one_card_slides`: full-panel `SetImage` widget → one deck of one card; it is off-panel at t=0.47.
  - `test_border_ring_static_and_on_top`: widget with `border` (mock with `thickness=1`) painting a ring plus 2 inset glyphs → at t=0.3 every ring pixel is painted at its snapshot colour AFTER card pixels (call order), and the glyphs have moved.
  - `test_two_row_decks_in_sync`: two-row widget (`bottom_text="b"`) → at outgoing k=1 both decks are off-panel. No painted pixel of a top-band card has y ≥ boundary.
  - `test_direction_right_mirrors_left`: a symmetric fixture → right's painted set at t equals left's with `x → W−1−x`.
  - `test_both_empty_paints_nothing` (Review Focus 2).
  - `test_geometry_change_reallocates` (Review Focus 4): fire on 160×16, then on a 256×64 scaled canvas → no exception, and cards are found at 256-wide dims.
  - `test_right_border_two_row_combined` (Review Focus 5).
- [ ] **Step 2:** Run `uv run pytest plugins/flair/tests/test_flair_accordion_transition.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement `accordion.py`, and register in `flair/__init__.py`.
- [ ] **Step 4:** Run the file, then `uv run pytest plugins/flair -q` and `make lint`. Expected: all PASS, lint clean (pyright included).
- [ ] **Step 5:** Commit: `feat(flair): flair.accordion.sweep / .stretch transitions`.

---

### Task 6: Perf tripwires and perf sweep

**Files:**
- Test: `plugins/flair/tests/test_flair_accordion_transition.py` (append `class TestPerfUniformity`)

**Interfaces:**
- Consumes: Task 5 classes.

- [ ] **Step 1: Write tests** (laser's `TestPerfUniformity` shape: count calls per frame, stepping t by 0.02 to 1.0):
  - `test_per_frame_paint_volume_bounded`: both classes on 160×16 text → worst ≤ `int(1.5 * 160*16)`.
  - `test_refire_frames_equally_bounded`: a second firing has the same bound.
  - `test_full_panel_image_bounded_bigsign`: 256×64 scale 4, full-panel image → ≤ `1.5 * 256*64`.
  - `test_many_tiny_cards_bounded` (Review Focus 3): a 256×64 raster with every other column lit (128 one-column cards) → bound holds, and `deck.peek < 8`.
- [ ] **Step 2:** Run. Expected: PASS. If it FAILS, fix the compositor, never the bound.
- [ ] **Step 3: Timing sweep.** Write a throwaway script (scratchpad, not committed) timing every frame at bigsign dims, with a fresh instance and a refire, for text and for a full-panel image. Record avg / worst / the t=0.5 lazy-snapshot frame. Gate: worst ≤ 5 × avg, with no phase-boundary outlier. Also record fresh-process construction time and first-ever-frame time. Save the numbers for the PR body.
- [ ] **Step 4:** Commit: `test(flair): accordion perf uniformity tripwires`.

---

### Task 7: Smoke config, docs in plugin, visual gate (HARD STOP)

**Files:**
- Create: `plugins/flair/examples/config.accordion-smoke.bigsign.toml`. Use the trimmed `config.laser-smoke.bigsign.toml` shape. Sections:
  - sweep left
  - sweep right
  - stretch left
  - stretch right
  - bg_color (different outgoing and incoming bgs)
  - cross-scale
  - image
  - empty-outgoing entry
  - bordered (rainbow + lightbulb)
  - two_row
  - Every section uses `easing = "ease_in_out"` and `duration = 2.0`.
- Modify: `plugins/flair/README.md`. Add an entry after `flair.laser`: types table, `direction` knob, the background-effect degradation note, and a recommended `duration`/`easing`.
- Modify: `plugins/flair/CLAUDE.md`. Add a `flair.accordion` invariants section: column-owner occlusion (no bg-colour knowledge, no core seam), the continuity rule and its endpoint anchors, lazy incoming snapshot + default `scale_switch_at`, border ring static on top, per-band decks. Name the tripwires.
- Create: `plugins/flair/docs/transition-accordion.gif`.

- [ ] **Step 1:** Write the smoke config. Validate it with core's `led-ticker validate`, run via `uv run --project ../led-ticker-plugins` from the core repo.
- [ ] **Step 2:** Render bigsign and smallsign GIFs of every section using the `making-a-gif` skill. Bigsign renders need a rows=64/cols=256/chain=1 copy of the config, because render-demo ignores `pixel_mapper_config`. Write them to the scratchpad.
- [ ] **Step 3: HARD STOP.** Show James the GIFs, plus the tuning surface: peek width, phase split, `min_frames`/`duration`, and whether to keep the beat. Apply only his requested changes. Re-render until he approves.
- [ ] **Step 4:** Commit the approved demo GIF, README, CLAUDE.md and smoke config: `docs(flair): accordion README, invariants, smoke config, demo gif`.

---

### Task 8: Core docs-site entry (separate PR in core repo, after the visual gate)

**Files (core repo, its own worktree and branch `docs/flair-accordion`):**
- Create: `docs/site/demos-pinned/transition-flair-accordion.toml`, and render it to `docs/site/public/demos-pinned/transition-flair-accordion.gif`.
- Modify: `docs/site/.../transitions/sprite.mdx`. Add an entry in "Text-effect transitions" after laser, following `docs/DOCS-STYLE.md`. The TOML snippet must match the demo TOML verbatim (docs demo/snippet parity).

- [ ] **Step 1:** Write the demo TOML and render it.
- [ ] **Step 2:** Write the mdx entry, then run the docs drift and lint tests (`make test` subset touching docs).
- [ ] **Step 3:** Commit. PRs for both repos are opened only with James's approval (`gh pr create` needs his go-ahead). The release (`cut_release.py flair minor`) happens only after his merge word.
