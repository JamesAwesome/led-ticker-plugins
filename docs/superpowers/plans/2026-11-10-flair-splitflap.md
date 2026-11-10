# flair.splitflap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `flair.splitflap.{forward,reverse,alternating,random}` — an in-place Solari split-flap transition — to the visual gate.

**Architecture:** Snapshot both widgets once per firing through accordion's deck segmentation (extracted into a shared mixin), build a pure-data "board" (band pairs → flap pairs with pre-slotted flip sequences and hinges), and paint each frame as a pure function of `p = t / SNAP_THRESHOLD`; snap to the real incoming draw at `SNAP_THRESHOLD`.

**Tech Stack:** Python 3.14, led-ticker plugin API (`led_ticker.plugin`), pytest, uv workspace (`plugins/flair`).

**Spec:** `docs/superpowers/specs/2026-11-10-flair-splitflap-transition-design.md`

## Global Constraints

- Import only from `led_ticker.plugin` (never `led_ticker.<internal>`); no `from __future__ import annotations`.
- Core floor unchanged: led-ticker-core >= 4.32.
- `scale_switch_at = 1.0`; snap at `t >= SNAP_THRESHOLD` via `snap_reset(canvas, incoming_bg_color)` + `incoming.draw(canvas, cursor_pos=0)`.
- Paint at physical resolution on `unwrap_to_real(canvas)`; re-derive `real` every call (never cache).
- Knobs: `flips` int >= 0 default 3; `stagger` float in [0.0, 0.9] default 0.5; bool rejected for both (`ValueError`, same style as `strand`/`slats`).
- New firing rule: `t == 0.0 or t < self._last_t`.
- README recommends `duration = 3.0`; `min_frames = 36`.
- Run tests from `plugins/flair`: `uv run pytest tests/<file> -q`; pyright before push.

## Review Focus

1. Cross-band-count pairing (message ↔ two_row, gif ↔ two_row): top band pairs with the single band, extra band flips from/to blank — never an IndexError. Test: `test_band_count_mismatch_pairs_top_and_blanks_extra` (Task 2).
2. A pure-black / fully-unlit outgoing or incoming (boot, wake): no division by zero in hinge/typical width/ripple; every pair flips from blank. Test: `test_empty_outgoing_flips_from_blank` (Task 2) and `test_both_empty_paints_nothing_until_snap` (Task 4).
3. Full-panel gif (wide cards): stripped to ~cell width, so it flips as strips, not one 256-px flap. Test: `test_wide_card_split_into_strips` (Task 2).
4. Squash at tiny heights (smallsign: 4-row halves, fh rounds to 0): never paints outside the band, never divides by zero. Test: `test_flap_tiny_half_heights_stay_in_band` (Task 3).
5. Identical in/out (same widget twice): no flips, no flicker. Test: `test_identical_cells_are_static` (Task 2).

---

### Task 1: Extract the deck-snapshot mixin

**Files:**
- Create: `plugins/flair/src/led_ticker_flair/flair/_deck_snapshot.py`
- Modify: `plugins/flair/src/led_ticker_flair/flair/accordion.py` (move `_scratch`, `_border_only`, `_solo_rows`, `_plan`, `_attrs_widget`, `_copy_frame_state`, `_ROW_FIELDS`, `_DROP_FIELDS`)

**Interfaces:**
- Produces: `class DeckSnapshotMixin` with attributes `_mirror: bool`, `_rasters: list[Raster | None]` (5 slots), `_raster_key`, and methods `_scratch(slot, w, h) -> Raster`, `_border_only(canvas, widget, w, h) -> Raster | None`, `_solo_rows(canvas, widget, cursor_pos, w, h) -> tuple[Raster, Raster] | None`, `_plan(canvas, widget, cursor_pos, slot) -> Plan` — names and behaviour byte-identical to today's `_Accordion` methods. `_init_deck_snapshot(mirror: bool) -> None` sets the three attributes.
- `_Accordion(DeckSnapshotMixin)` keeps every method name tests reach (`_solo_rows`, `_raster_key`).

- [ ] **Step 1:** Move the code; `_Accordion.__init__` calls `self._init_deck_snapshot(direction == "right")`. Re-export `_attrs_widget` / `_copy_frame_state` from `accordion` if any test imports them (`grep -n "_attrs_widget\|_copy_frame_state" tests/`).
- [ ] **Step 2:** Run `uv run pytest tests/test_flair_accordion_plan.py tests/test_flair_accordion_transition.py -q`. Expected: all pass, same count as before the move.
- [ ] **Step 3:** Commit `refactor(flair): share accordion's deck snapshot as a mixin`.

### Task 2: Board data layer

**Files:**
- Create: `plugins/flair/src/led_ticker_flair/flair/splitflap_board.py`
- Test: `plugins/flair/tests/test_flair_splitflap_board.py`

**Interfaces:**
- Consumes: `Card`, `Deck`, `Plan` from `accordion_cards`.
- Produces:
  - `@dataclass(frozen=True) class FlapCell: slot: int; width: int; rows: dict[int, tuple[tuple[int, tuple[int,int,int]], ...]]` (y_real → ((dx, rgb), …)); `from_card(card) -> FlapCell`; `centred_on(centre_x: int) -> FlapCell` (same rows, new slot).
  - `@dataclass(frozen=True) class Flap: band: int; seq: tuple[FlapCell | None, ...]` (outgoing first, incoming last, intermediates between); `static: bool`; `centre_x: int`.
  - `@dataclass(frozen=True) class BandGeom: lo: int; hinge: int; hi: int` (inclusive lit-row extent; `hinge = (lo + hi + 1) // 2`; top half = rows `< hinge`).
  - `@dataclass(frozen=True) class Board: bands: tuple[BandGeom, ...]; flaps: tuple[Flap, ...]; ring_out, under_out, ring_in, under_in: tuple[Pixel, ...]`.
  - `typical_width(cards: Sequence[Card], band_h: int) -> int` — median width of cards with `width <= band_h`; none → `max(1, band_h // 2)`.
  - `split_wide(cards: Sequence[Card], cell_w: int) -> list[Card]` — a card wider than `2 * cell_w` becomes `ceil(width / cell_w)` near-equal strips (pixels partitioned by dx); others unchanged.
  - `pair_bands(out_decks, in_decks) -> list[tuple[tuple[Card, ...], tuple[Card, ...]]]` — index pairing; the shorter side padded with empty bands at the END (so the single band pairs with the top).
  - `build_board(out_plan: Plan, in_plan: Plan, flips: int, rng: random.Random) -> Board`.

- [ ] **Step 1: Write failing tests** (build `Card`s / `Plan`s by hand):
  - `test_typical_width_median_of_glyph_like_cards` — widths [5,6,7,40] band_h 10 → 6; no glyph-like → band_h // 2.
  - `test_wide_card_split_into_strips` — width 64, cell_w 8 → 8 strips, every pixel in exactly one strip, slots contiguous.
  - `test_band_count_mismatch_pairs_top_and_blanks_extra` — out 1 band (3 cards), in 2 bands (2 + 2) → band 0 has 3 flaps (one to blank), band 1 has 2 flaps whose `seq[0] is None`.
  - `test_hinge_is_middle_of_union_of_lit_rows` — out rows 10..19, in rows 14..25 → lo 10, hi 25, hinge 18.
  - `test_identical_cells_are_static` — same card both sides → `static is True`, `len(seq) == 2`.
  - `test_empty_outgoing_flips_from_blank` — out plan with no cards → every flap `seq[0] is None`, no exception.
  - `test_intermediates_from_band_pool_no_repeat_and_centred` — seeded rng, flips 3: each intermediate's rows come from a pool card of that band, none equal the pair's own cards, no two consecutive equal, each `slot + width // 2 == ` incoming centre.
  - `test_small_pool_reduces_flips` — band with 1 card per side → `len(seq) == 2`.
- [ ] **Step 2:** `uv run pytest tests/test_flair_splitflap_board.py -q` → FAIL (module missing).
- [ ] **Step 3:** Implement. Per band pair: `cell_w = typical_width(both sides' cards, hi - lo + 1)`, `split_wide` each side, pair cell i ↔ i (pad with None), pool = all split cells of the pair. `static` = both present, same slot, same pixels. Ring/under copied from the plans.
- [ ] **Step 4:** Re-run → PASS. **Step 5:** Commit `feat(flair): splitflap board data layer`.

### Task 3: Flap painter

**Files:**
- Create: `plugins/flair/src/led_ticker_flair/flair/splitflap_paint.py`
- Test: `plugins/flair/tests/test_flair_splitflap_paint.py`

**Interfaces:**
- Consumes: `FlapCell`, `BandGeom` (Task 2).
- Produces: `FLAP_SHADE = 0.7`; `paint_cell(set_px, cell: FlapCell | None, w: int, h: int) -> None`; `paint_flap(set_px, a: FlapCell | None, b: FlapCell | None, band: BandGeom, q: float, w: int, h: int, shade: float = FLAP_SHADE) -> None`.

Algorithm (spec "One flap"): `top_h = hinge - lo`, `bot_h = hi + 1 - hinge`.
- `q < 0.5`: `fh = round(top_h * (1 - 2q))`; paint b's rows `< hinge - fh`; a's rows `>= hinge`; flap rows `r in [hinge - fh, hinge)` sample a's row `lo + (r - (hinge - fh)) * top_h // fh`, RGB × shade.
- `q >= 0.5`: `fh = round(bot_h * (2q - 1))`; paint b's rows `< hinge`; a's rows `>= hinge + fh`; flap rows `r in [hinge, hinge + fh)` sample b's row `hinge + (r - hinge) * bot_h // fh`, × shade.
- `fh == 0` paints no flap rows. Every write bounds-checked to `0 <= x < w, 0 <= y < h`.

- [ ] **Step 1: Failing tests** with a recording `set_px`:
  - `test_flap_q0_shows_outgoing` / `test_flap_q1_shows_incoming_unshaded` (q→1: fh = bot_h, flap rows = b's bottom × shade — assert q=0.999 bottom is shaded b, and `paint_cell(b)` equals b exactly).
  - `test_flap_first_half_squashes_a_top_toward_hinge` — q 0.25: flap rows occupy `[hinge - top_h//2, hinge)` and their colours are a's top colours × 0.7.
  - `test_flap_second_half_unfolds_b_bottom` — q 0.75 symmetric.
  - `test_flap_from_blank_and_to_blank` — a None / b None paint only the other side's halves.
  - `test_flap_tiny_half_heights_stay_in_band` — lo 6, hi 9 (4 rows), every q in steps of 0.05: all writes inside `[lo, hi]`, no exception.
- [ ] **Step 2:** run → FAIL. **Step 3:** implement. **Step 4:** run → PASS. **Step 5:** commit `feat(flair): splitflap flap painter`.

### Task 4: Transition classes, timeline, registration

**Files:**
- Create: `plugins/flair/src/led_ticker_flair/flair/splitflap.py`
- Modify: `plugins/flair/src/led_ticker_flair/flair/__init__.py` (register 4 types; module docstring list)
- Test: `plugins/flair/tests/test_flair_splitflap_transition.py` (stub canvas/widgets copied from `test_flair_blinds_transition.py`, per repo convention)

**Interfaces:**
- Consumes: `DeckSnapshotMixin` (T1), `build_board` / `Board` (T2), `paint_cell` / `paint_flap` (T3), `Cycling` (`_variants`).
- Produces: `class SplitFlap(DeckSnapshotMixin)` (`min_frames = 36`, `scale_switch_at = 1.0`, `_order = "forward"`, `__init__(self, flips: Any = 3, stagger: Any = 0.5)`, `self._rng = random.Random()`), `SplitFlapReverse` (`_order = "reverse"`), `SplitFlapRandom` (`_order = "random"`), `SplitFlapAlternating(Cycling)` over `[SplitFlap, SplitFlapReverse]`; `flap_start(order: str, centre_x: int, x_min: int, x_max: int, stagger: float, rand: float) -> float`; registered as `splitflap.forward/.reverse/.alternating/.random`.

Timeline runs on `s = min(p / LAND, 1.0)` with `LAND = 0.9` (Ruling: the board sits fully landed for the last 10 % before the snap — a settle beat, and it makes "all landed" exact rather than a shaded last-frame flap). `f = (1 - stagger) / (flips + 1)`; start: forward `stagger * (cx - x_min) / max(x_max - x_min, 1)`, reverse `stagger - that`, random `stagger * rand` (rand drawn per flap per firing from `_rng`). Flap with `len(seq) - 1 = m` steps: `u = (p - start) / f`; `u <= 0` → `paint_cell(seq[0])`; `u >= m` → `paint_cell(seq[-1])`; else `paint_flap(seq[int(u)], seq[int(u)+1], band, u % 1)`. Static flaps always `paint_cell(seq[0])`. Paint order per frame: `under` → flaps → `ring` (outgoing's for `p < 0.5`, incoming's after).

- [ ] **Step 1: Failing tests:**
  - `test_knob_validation` — `flips=-1`, `flips=True`, `flips=1.5`, `stagger=0.95`, `stagger=True`, `stagger="x"` raise `ValueError`; `flips=0`, `stagger=0.0` ok.
  - `test_t0_paints_outgoing_exactly` / `test_snap_draws_incoming` (t = SNAP_THRESHOLD → `snap_reset` path, incoming.draw called with cursor_pos=0).
  - `test_forward_ripple_left_settles_first` — two-cell text, flips 0: at a mid t the left cell shows incoming while the right still shows outgoing; `SplitFlapReverse` the opposite.
  - `test_all_landed_before_snap` — p = 0.92 (t = 0.92 * SNAP_THRESHOLD) → canvas pixels equal the incoming snapshot exactly.
  - `test_both_empty_paints_nothing_until_snap`.
  - `test_border_ring_static` — bordered stub widget: ring pixels present unchanged at t 0.1 and 0.4.
  - `test_snapshots_once_per_firing` — draw call counts don't grow across frames; a refire (t back to 0) resnapshots.
  - `test_alternating_cycles_forward_reverse` and `test_random_order_seeded_reproducible`.
  - `test_outgoing_scroll_pos_forwarded` — outgoing drawn with `cursor_pos == kwargs["outgoing_scroll_pos"]`.
  - `test_registered_types` — the four names resolve via the plugin's `register(api)` stub (copy blinds' registration test).
  - Real-widget smoke: core `TickerMessage` → `GifPlayer` and `TwoRowMessage` → `TickerMessage` at scale 4 on `HeadlessCanvas(256, 64)` run t = 0..1 step 0.05 without exception (copy blinds' real-widget snapshot test shape).
- [ ] **Step 2:** run → FAIL. **Step 3:** implement. **Step 4:** run → PASS; then full flair suite `uv run pytest -q` and `uv run ruff check . && uv run pyright` from repo root. **Step 5:** commit `feat(flair): splitflap transition (flair.splitflap.*)`.

### Task 5: Docs + smoke configs

**Files:**
- Modify: `plugins/flair/README.md` (new `flair.splitflap` section modelled on blinds': variant table, knobs table, `duration = 3.0` recommendation, floor note "min_frames = 36, i.e. 1.8 s at 20 fps", limitations: cross-scale + bg change land at the snap, in-between characters are borrowed shuffles), `plugins/flair/CLAUDE.md` (invariants: scale_switch_at 1.0, band pairing rule, shared mixin — don't fork it).
- Create: `plugins/flair/examples/config.splitflap-smoke.bigsign.toml`, `plugins/flair/examples/config.splitflap-smoke.smallsign.toml` — sections: forward (different-length texts), reverse, alternating, random, bg-colour hold, rainbow border, two_row (and message↔two_row boundary), gif in/out (`assets/phoenix.gif`), `{flips = 0}` and `{stagger = 0.8}` knob sections, letterbox (scale 2 / content_height 16, bigsign only); `[transitions] duration = 3.0`.

- [ ] **Step 1:** Write; validate both with core's validator in the plugin venv: `uv run led-ticker validate plugins/flair/examples/config.splitflap-smoke.bigsign.toml` (from repo root) → "No issues found." (same for smallsign).
- [ ] **Step 2:** Commit `docs(flair): splitflap README, invariants, smoke configs`.

### Task 6: Visual gate

- [ ] Render bigsign (render-geometry copy: rows=64, cols=256, chain=1, no pixel_mapper_config) and smallsign GIFs into the scratchpad via `uv run --project ../led-ticker-plugins python tools/render_demo/render.py <toml> -o <gif> --duration <N>` from the core checkout; sample frames by playback time, Read them, then show James. Stop before PR.
