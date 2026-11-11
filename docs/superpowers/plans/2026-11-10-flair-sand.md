# flair.sand Transition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `transition = "flair.sand"`. The outgoing content crumbles
into grains that fall off the bottom of the panel, and the incoming content
pours in from the top, grain by grain, and stacks into place.

**Architecture:**

- **Snapshots.** Both widgets are snapshotted into plugin-local readable
  rasters with the existing `_snapshot.SnapshotCache`. The outgoing widget
  is snapshotted on the first frame of a firing. The incoming widget is
  snapshotted lazily on the first frame with `t >= 0.5`, after the
  runner's scale switch.
- **Pure-math module.** `_sand.py` turns each snapshot into per-grain
  constants once per firing, and answers "where is grain i at phase p".
- **Transition module.** `sand.py` is the `frame_at` driver.

**Tech Stack:** Python 3.14, the `led_ticker.plugin` public surface only,
pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-11-10-flair-sand-transition-design.md`

## Global Constraints

### Dependencies and API

- No new core API. Import only from `led_ticker.plugin`. No new
  dependencies (numpy included).
- No `from __future__ import annotations` (PEP 649 rule).

### Rendering

- Grain = one real LED. Grains are drawn per real pixel, never per 4×4
  logical block.
- Release time, drift and pour start are random per grain.
- `is_lit` pixels only. Unset and pure-black snapshot pixels never become
  grains.
- `real` is re-derived on every `frame_at` call and never cached
  (constraint #1).
- The transition never clears the canvas. The runner does that.

### Timeline

- Crumble runs over `t ∈ [0, 0.5)`.
- Pour runs over `t ∈ [0.5, SNAP_THRESHOLD)`.
- At `t >= SNAP_THRESHOLD`: `snap_reset(canvas, incoming_bg_color)`, then
  `incoming.draw(canvas, cursor_pos=0)`.

### Class attributes

- `scale_switch_at = 0.5`.
- `min_frames = 30`.

### Seed

- `seed: int | None = None`. The only knob. It is validated exactly like
  `flair.snow`: an int, not a bool, or None.
- When `seed` is None, a fresh seed is drawn per firing.

### Firing

- A new firing starts when `t == 0.0` or when `t < last_t`. A new firing
  re-snapshots.

### Performance

- A fully lit 256×64 frame, timed with `SetPixel` stubbed to a no-op, must
  take less than 15 ms in both phases.
- If it doesn't, report to the controller. Never reduce the grain count.

## Review Focus

1. **Scrolled outgoing text.** `outgoing_scroll_pos` must reach the
   outgoing snapshot, so text crumbles from where it stopped.
   (`test_scroll_pos_forwarded`, Task 2)
2. **An empty widget on either side** (a blank widget, or all-black
   gif frames). There are no grains, nothing crashes, and the empty side
   simply shows nothing. (`test_empty_outgoing_and_incoming`, Task 2)
3. **Cross-scale sections.** When the incoming section has a different
   scale, the incoming snapshot is taken from the re-wrapped canvas at
   `t >= 0.5`, so grains land at the incoming native geometry.
   (`test_incoming_snapshot_taken_lazily_after_switch`, Task 2)
4. **The smallsign, 160×16.** Every grain falls fully off the panel
   within the crumble, and every pour grain lands before the snap, with
   tiny `h`. (`test_physics_holds_on_small_panel`, Task 1)
5. **A short configured duration** (the engine default is 0.5 s, about
   10 frames). Frames are sampled sparsely. Any `t` must still produce a
   valid frame with no exceptions, and the snap must be exact.
   (`test_sparse_frames`, Task 2)

---

### Task 1: Grain math (`_sand.py`)

**Files:**
- Create: `plugins/flair/src/led_ticker_flair/flair/_sand.py`
- Test: `plugins/flair/tests/test_flair_sand_plan.py`

**Interfaces:**
- Consumes: `Raster` and `is_lit` from `._raster`.
- Produces:
  - `CrumbleGrain = tuple[int, int, int, int, int, float, float]`, meaning
    `(x0, y0, r, g, b, release, vx)`.
  - `PourGrain = tuple[int, int, int, int, int, float, int]`, meaning
    `(x, y, r, g, b, start, dist)`.
  - `crumble_grains(raster: Raster, rng: random.Random) -> list[CrumbleGrain]`
  - `pour_grains(raster: Raster, rng: random.Random) -> list[PourGrain]`
  - `crumble_pos(grain: CrumbleGrain, p: float, w: int, h: int) -> tuple[int, int] | None`
    returns the current position of a grain, or None if it is off-panel.
    `p` is crumble progress in `[0, 1)`.
  - `pour_pos(grain: PourGrain, q: float, h: int) -> int | None` returns
    the current y of a grain, or None if the grain hasn't started or is
    above the panel. `q` is pour progress in `[0, 1)`.
  - Constants: `RELEASE_MAX = 0.35`, `POUR_ROW_SPAN = 0.55`,
    `POUR_JITTER = 0.25`, `POUR_FALL_MAX = 0.45` (was 0.65 in the first draft;
    0.45 matches the approved mockup), `DRIFT_FRAC = 0.02`,
    `CRUMBLE_CLEAR = 0.85`.

**Algorithm (pinned by the spec; not determined by the signatures):**

**Crumble.**

- Each grain gets a release time `release ~ U(0, RELEASE_MAX)` and a drift
  `vx ~ U(-1, 1) · DRIFT_FRAC · w / (1 - RELEASE_MAX)`.
- Before release (`dt = p - release < 0`), the grain sits at `(x0, y0)`.
- After release:
  - `x = x0 + vx·dt`
  - `y = y0 + 0.5·G·dt²`
  - `G = 2.1·h / (CRUMBLE_CLEAR - RELEASE_MAX)²`, which carries a 5%
    margin, so the last-released top-row grain has left the panel by
    `p = CRUMBLE_CLEAR`. (The runner never samples `p = 1`: at 30 frames
    the last crumble frame is about 0.93, or 0.87 under `ease_in_out`.)
- Round x and y. Return None if either is outside the panel.

**Pour.**

- Drop height is `H0 = max(1, round(h / 16))`, so 4 on a 64-tall panel and
  1 on a 16-tall panel. Each grain's fall distance is `dist = y + H0`.
- Start time: `start = (y_hi-y)/span · POUR_ROW_SPAN + U(0, POUR_JITTER)`,
  where `y_hi` and `span` are the content's own lowest lit row and row
  span, so letterboxed content doesn't wait on empty panel rows.
- Gravity: `Gp = 2·(h + H0) / POUR_FALL_MAX²`.
- Fall time: `T = sqrt(2·dist / Gp)`.
- Clamp the start so every grain lands in time:
  `start = min(start, 1 - T - 1e-6)`.
- Position:
  - If `q < start`, return None.
  - Otherwise `yy = (y - dist) + 0.5·Gp·(q - start)²`, capped at `y`.
  - Round, and return None if the result is less than 0.
- Grains move straight down only; x never changes.

**Grain lists.** Both lists come from a row-major scan of
`raster.get(x, y)`, keeping only pixels where `is_lit` is true. Draw the
random values in scan order from the `rng` passed in, so a given seed
always gives the same grains.

- [ ] **Step 1: Write failing tests** in `test_flair_sand_plan.py`, using a
  local `Raster` filled by `SetPixel`:
  - `test_grains_only_from_lit_pixels`: a 4×3 raster with two coloured
    pixels and one black pixel → `len(crumble_grains(...)) == 2`, the
    grains carry those exact rgb values, and the same holds for
    `pour_grains`.
  - `test_crumble_before_release_is_in_place`: a grain with
    `release=0.3` → `crumble_pos(g, 0.2, 256, 64) == (x0, y0)`.
  - `test_crumble_all_off_panel_by_end`: a fully lit 256×64 raster with
    `Random(1)` → every grain gives `crumble_pos(g, 0.999, 256, 64) is
    None`.
  - `test_crumble_only_moves_down_and_drift_bounded`: for every grain and
    every p in `(0.1, 0.5, 0.9)`, a non-None result has `y >= y0` and
    `abs(x - x0) <= ceil(0.02*256) + 1`.
  - `test_pour_straight_drop`: for every grain and every q in
    `[0.0, 0.1, …, 0.9]`, a non-None result has `y_now <= y` (same
    column by construction).
  - `test_pour_all_landed_before_end`: on a fully lit raster,
    `pour_pos(g, 0.9999, h) == g[1]` for every grain.
  - `test_pour_bottom_rows_lead`: on a fully lit 256×64 raster, the
    landed fraction of the bottom 8 rows at `q=0.5` is greater than that
    of the top 8 rows.
  - `test_physics_holds_on_small_panel`: repeat the two "by end"
    assertions on a fully lit 160×16 raster.
  - `test_same_seed_same_grains`: `crumble_grains(r, Random(7))` called
    twice gives equal lists.
- [ ] **Step 2: Run the tests and confirm they fail.**
  Run: `uv run pytest plugins/flair/tests/test_flair_sand_plan.py -q`
  Expected: FAIL, because `_sand` does not exist yet.
- [ ] **Step 3: Implement `_sand.py`** per the interfaces and algorithm
  above. Give it a module docstring that says, in one breath, what the
  crumble and the pour each do.
- [ ] **Step 4: Run the tests and confirm they pass.**
  Run: `uv run pytest plugins/flair/tests/test_flair_sand_plan.py -q`
  Expected: PASS.
- [ ] **Step 5: Commit.**
  `git commit -m "feat(flair): sand grain math"` (plus the Co-Authored-By
  trailer).

### Task 2: `flair.sand` transition + registration

**Files:**
- Create: `plugins/flair/src/led_ticker_flair/flair/sand.py`
- Modify: `plugins/flair/src/led_ticker_flair/flair/__init__.py`. Import
  `Sand` alongside `Snow`, add `api.transition("sand")(Sand)`, and mention
  `flair.sand` in the module docstring.
- Modify: `plugins/flair/tests/test_smoke.py`. Assert that `"sand"` is in
  `api.transitions`.
- Test: `plugins/flair/tests/test_flair_sand_transition.py`

**Interfaces:**
- Consumes: everything Task 1 produces; `SnapshotCache` from `._snapshot`;
  and `SNAP_THRESHOLD`, `Canvas`, `is_scaled`, `snap_reset` and
  `unwrap_to_real` from `led_ticker.plugin`.
- Produces:
  - `class Sand` with `__init__(self, seed: int | None = None) -> None`.
  - `frame_at(self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any) -> Canvas`.
  - Class attributes `min_frames = 30` and `scale_switch_at = 0.5`.

**Behaviour:**

- **New firing** (`t == 0.0` or `t < last_t`):
  - Drop both grain lists.
  - If `seed` is None, re-roll `self._seed` from
    `random.SystemRandom().getrandbits(62)`.
  - The RNG for a firing is `random.Random(self._seed)`. Outgoing grains
    are drawn first, then incoming grains, from that same RNG.
- **Crumble frames** (`t < 0.5`):
  - On the first crumble frame, snapshot the outgoing widget into slot 0,
    passing `kwargs.get("outgoing_scroll_pos", 0)`, and build the crumble
    grains.
  - Paint each grain at `crumble_pos(g, t / 0.5, w, h)` with `SetPixel` on
    the real canvas.
- **Pour frames** (`0.5 <= t < SNAP_THRESHOLD`):
  - On the first pour frame, snapshot the incoming widget into slot 1 from
    *this* frame's canvas and build the pour grains.
  - Paint each grain at `(x, pour_pos(g, (t - 0.5) / (SNAP_THRESHOLD -
    0.5), h))`.
  - If a firing's first frame is already a pour frame, nothing crumbles.
- **Snap** (`t >= SNAP_THRESHOLD`): follow the Global Constraints. Do not
  use the grain lists at all.

- [ ] **Step 1: Write failing tests.** Reuse the `_StubCanvas`,
  `_fill_widget` and `_empty_widget` helpers, copied from
  `test_flair_snow_transition.py`. Write:
  - `test_t0_shows_only_outgoing`: a RED 16×16 outgoing widget →
    `frame_at(0.0)` paints exactly the 256 RED pixels at their source
    positions.
  - `test_snap_shows_only_incoming`: at `t=0.96`, the pixels equal the
    pixels of a direct `incoming.draw`, and `snap_reset` receives
    `incoming_bg_color` (monkeypatch, as snow's
    `test_bordered_incoming_no_flash` does).
  - `test_crumble_frames_only_outgoing_colors_and_falling`: at
    `t=0.25`, every painted colour is RED, and at least one RED pixel is
    lit in a row where the source had none. Use a 16×8 RED block on a
    16×16 canvas.
  - `test_crumble_empty_by_phase_end`: at `t=0.499`, nothing is painted.
  - `test_pour_only_incoming_colors_and_straight_drop`: at
    `t ∈ {0.55, 0.7, 0.85}`, every painted pixel is GREEN, and every
    painted (x, y) has a target pixel at (x, y') with `y' >= y` in the
    same column. Use a GREEN block in the bottom half of the canvas.
  - `test_pour_complete_before_snap`: at `t=0.9499`, the painted set
    equals the incoming lit set.
  - `test_explicit_seed_reproducible` and
    `test_unseeded_instance_differs_per_firing`: compare full firings
    (frames at 0.0, 0.25 and 0.7), following snow's `_firing` pattern.
  - `test_t0_always_refires` and `test_refire_resnapshots`: follow
    snow's equivalents.
  - `test_scroll_pos_forwarded`: `outgoing.draw` is called with
    `cursor_pos=7` when `frame_at(0.0, ..., outgoing_scroll_pos=7)`.
  - `test_empty_outgoing_and_incoming`: with `_empty_widget` on both
    sides, `t ∈ {0, 0.25, 0.6, 0.9}` paint nothing and raise nothing.
  - `test_incoming_snapshot_taken_lazily_after_switch`: `incoming.draw`
    is not called during `t < 0.5` frames, and is called once on the
    first `t >= 0.5` frame.
  - `test_scaled_physical_resolution`: on a
    `ScaledCanvas(_StubCanvas(64, 16), scale=4, content_height=4)` with a
    1×1 logical RED widget (one 4×4 real block), `t=0.25` must not paint a
    translated copy of that 4×4 block. Grains in one block move
    independently. Use `seed=3`, so the test is deterministic.
  - `test_sparse_frames`: frames at `t` in
    `[0.0, 0.11, 0.33, 0.51, 0.77, 0.96, 1.0]` run with no exception, and
    the 1.0 frame equals the incoming widget.
  - `test_bad_seed`: `Sand(seed=True)` and `Sand(seed="x")` raise
    `ValueError`.
  - `test_attrs`: `min_frames == 30` and `scale_switch_at == 0.5`.
  - `test_perf_bigsign`: fully lit 256×64 RED and GREEN widgets, with
    `SetPixel` stubbed to a no-op. Prime with frames at `0.0` and `0.5`.
    Then the worst of 5 frames at `t=0.3` and the worst of 5 at
    `t=0.75` must each be under `0.015` s.
- [ ] **Step 2: Run the tests and confirm they fail.**
  Run: `uv run pytest plugins/flair/tests/test_flair_sand_transition.py plugins/flair/tests/test_smoke.py -q`
  Expected: FAIL, because there is no `sand` module yet.
- [ ] **Step 3: Implement `sand.py`** per the Behaviour section. Its module
  docstring follows the "design in one breath" style of `blinds.py` and
  `snow.py`, and links the spec. Then register it in `__init__.py`.
- [ ] **Step 4: Run the tests and confirm they pass.** If the perf test
  fails, first hoist attribute lookups and inline the `_sand` position
  math into the per-frame loop. If it still fails, report
  DONE_WITH_CONCERNS with the timings. Do not cut grains.
  Run: `uv run pytest plugins/flair -q`
  Expected: PASS, whole package.
- [ ] **Step 5: Run lint and types, then commit.**
  Run: `uv run ruff check plugins/flair && uv run ruff format --check plugins/flair && uv run pyright plugins/flair/src`
  Expected: clean.
  Then: `git commit -m "feat(flair): flair.sand transition"` (plus the
  trailer).

### Task 3: README, example, release notes, visual check

**Files:**
- Modify: `plugins/flair/README.md`. Add a "## Sand transition" section
  directly after "## Snow transition", in the same shape: a one-paragraph
  description, a line saying it "Requires **led-ticker-core >= 4.32**", and
  a Config block plus a knobs table.
- Modify: any README index or transition list that names `flair.snow` as a
  transition, so that it also lists `flair.sand`. Find them with
  `grep -n "flair.snow" plugins/flair/README.md`.
- Create: `plugins/flair/examples/sand.toml`, only if the package ships
  per-transition example configs that `tests/test_examples_validate.py`
  picks up. Check that directory first. If it does not exist, skip this
  file.

The Config block in the README is exactly:

```toml
[[playlist.section.widget]]
type = "message"
text = "SAND"
transition = {type = "flair.sand", duration = 3}
```

The knobs table has one row:

| Knob | Default | Meaning |
| --- | --- | --- |
| `seed` | none | An int makes the crumble and pour identical on every run; unset gives a fresh pattern each time. |

The section must include this note: "The engine's default transition
`duration` is 0.5 s, which is too fast to read as sand; use about
`duration = 3`."

- [ ] **Step 1: Edit the README** as above.
- [ ] **Step 2: Render the transition and look at it.**
  - Write a bigsign demo config (rows=64, cols=256, chain=1, no
    `pixel_mapper_config`, `default_scale = 4`) with two messages:
    rainbow "TWINKLE" and gold "SAND". Put
    `transition = {type = "flair.sand", duration = 3}` on the section.
  - Render it from the core checkout:
    `cd ../led-ticker && PYTHONPATH=. uv run --no-sync --project ../led-ticker-plugins-wt-sand python tools/render_demo/render.py <toml> -o <scratchpad>/sand-bigsign.gif --duration 12`
  - Repeat at 160×16 scale 1, writing `sand-smallsign.gif`.
  - Read frames from the middle of each phase and confirm: the outgoing
    word crumbles unevenly and leaves through the bottom, the new letters
    build from the bottom up, and there are no 4×4 blocks on the bigsign.
- [ ] **Step 3: Write the release notes** to
  `<scratchpad>/notes-flair-sand.md`. They need a `## New: flair.sand`
  heading, two sentences, and the README config block. Nothing is
  committed for this step; the notes feed `cut_release.py` later.
- [ ] **Step 4: Commit the README** (and the example, if it was created).
  `git commit -m "docs(flair): flair.sand README"` (plus the trailer).
