# flair.laser Transition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `flair.laser.{top,bottom,left,right,alternating,random}` — a transition where a content-coloured beam reaches in from one panel edge, erases the outgoing content pixel by pixel in a back-and-forth raster, then writes the incoming content the same way.

**Architecture:** One self-contained module `laser.py` in the flair plugin. A plugin-local readable raster (`_Raster`) snapshots each widget once per firing at physical resolution; a pure planning function turns a raster into an ordered list of lit pixels (boustrophedon, origin edge first); `Laser.frame_at` maps `t` to a visited-pixel count, paints unvisited outgoing pixels (erase phase) or visited incoming pixels (write phase) on `unwrap_to_real(canvas)`, and draws a one-real-pixel beam from the origin edge to the head pixel in the head's colour. No core change.

**Tech Stack:** Python 3.14 rules (no `from __future__ import annotations`), `led_ticker.plugin` public surface only (`Canvas`, `ScaledCanvas`, `is_scaled`, `unwrap_to_real`, `snap_reset`, `SNAP_THRESHOLD`), Pillow (already a core dep) for `SetImage` decode, pytest, ruff, pyright.

**Spec:** `docs/superpowers/specs/2026-10-28-flair-laser-transition-design.md`

## Global Constraints

- Core floor stays `led-ticker-core>=4.31`; no new runtime deps; no core PR.
- Imports from `led_ticker` ONLY via `led_ticker.plugin` (`tests/test_import_purity.py`). `from PIL import Image` is allowed (type-only use is fine).
- No `from __future__ import annotations`.
- `min_frames = 48` on every registered laser type. `SNAP_THRESHOLD` (0.95) ends the write phase: all incoming pixels visited at t ≥ 0.95.
- Visited count: `N = n_out + n_in`; `visited(t) = N if t >= 0.95 else int(N * t / 0.95)`. First `n_out` visits erase; the rest write.
- Lit pixel = raster slot set AND colour != `(0, 0, 0)`.
- Raster lines are PHYSICAL rows (top/bottom) or columns (left/right); first line nearest the origin edge; direction flips after every NON-EMPTY line; empty lines skipped; write phase starts at the origin edge with the parity the erase phase ended on.
- Beam: 1 real px wide, from the origin edge to the head pixel inclusive, in the head pixel's colour.
- Never cache `unwrap_to_real(canvas)` across frames (constraint #1); the `_Raster` and its `ScaledCanvas` wrapper ARE reusable across frames and firings while geometry matches.
- Variant names: `laser.top`, `laser.bottom`, `laser.left`, `laser.right`, `laser.alternating` (cycle top → right → bottom → left), `laser.random` (no back-to-back repeat).
- `beams` knob (positive int, default 3; spec **Beams** section): N independent beams over the lit CONTENT extent; per-beam constant speed; bg cut-over when the first beam writes. Added mid-execution after James's spike review (ledger Task 5 rulings).
- Lint gates from `plugins/flair/`: `uv run --extra dev ruff check src/ tests/`, `uv run --extra dev ruff format --check src/ tests/`, `PYRIGHT_PYTHON_FORCE_VERSION=latest uv run --extra dev pyright src/`.
- All `pytest`/`ruff` commands run from `/Users/james/projects/github/jamesawesome/led-ticker-plugins/plugins/flair/`.
- Rendering gifs from the core repo (`/Users/james/projects/github/jamesawesome/led-ticker`): `uv pip install -q -e /Users/james/projects/github/jamesawesome/led-ticker-plugins/plugins/flair` then `uv run --no-sync python tools/render_demo/render.py <toml> -o <gif> --duration <N>` (plain `uv run` re-syncs and uninstalls the editable plugin). Scratch files under `$CLAUDE_JOB_DIR/tmp/`.
- James wants gifs AS WE GO: Task 3 and Task 5 end at HARD STOPs for his approval. Never post to GitHub without his OK on the exact text.
- Release word after merge: `uv run python scripts/cut_release.py flair minor --notes FILE` (never precompute the version).

## Review Focus

1. A widget whose draw raises inside the snapshot (breaker guard returns `(canvas, 0)` and trips it): the raster is empty, `n == 0`, and the transition must still complete without a beam or an exception. → Task 3 `test_zero_lit_pixels_both_sides_snaps_cleanly`.
2. A `two_row` or image widget with its own band/bg fill on the bigsign: ~16k lit pixels, SetPixel per frame must stay ≤ 1.5× panel px and the phase boundary must not stall. → Task 4 `test_full_panel_fill_within_paint_bound`.
3. `t` arriving non-monotonic within a firing (easing never does this, but `ease_in_out` makes t move slowly near 0): a frame at t=0.0 after t=0.02 must NOT be read as a refire. → Task 3 `test_equal_t_is_not_a_refire` (same t twice keeps snapshots).
4. Scaled wrapper with a letterbox band (scale 2 on a 64-row panel, content_height 16): the beam reaches the REAL panel edge, not the band edge. → Task 3 `test_beam_reaches_real_edge_through_letterbox_band`.
5. `SetImage` with an RGBA image whose transparent pixels must read as unlit, and an offset that pushes part of the image off-raster (clipped, no exception). → Task 2 `test_setimage_alpha_zero_is_unlit_and_clips`.

---

### Task 1: `_Raster` — readable canvas stub with `SetImage`

**Files:**
- Create: `plugins/flair/src/led_ticker_flair/flair/laser.py`
- Test: `plugins/flair/tests/test_flair_laser_plan.py`

**Interfaces:**
- Produces: `class _Raster` with `width: int`, `height: int`, `SetPixel(x, y, r, g, b) -> None`, `SubFill(x, y, w, h, r, g, b) -> None`, `Clear() -> None`, `Fill(r, g, b) -> None`, `SetImage(image, offset_x=0, offset_y=0) -> None`, `get(x, y) -> tuple[int, int, int] | None`. Out-of-bounds writes ignored. `Clear()` resets every slot to `None`; `Fill` sets every slot.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_flair_laser_plan.py
from PIL import Image
from led_ticker_flair.flair.laser import _Raster

def test_raster_setpixel_get_and_oob_ignored():
    r = _Raster(4, 2)
    r.SetPixel(1, 1, 10, 20, 30)
    r.SetPixel(9, 9, 1, 1, 1)
    assert r.get(1, 1) == (10, 20, 30)
    assert r.get(0, 0) is None
    assert r.get(9, 9) is None

def test_raster_subfill_clips_and_clear_resets():
    r = _Raster(4, 2)
    r.SubFill(2, 0, 10, 10, 5, 5, 5)
    assert r.get(3, 1) == (5, 5, 5) and r.get(1, 1) is None
    r.Clear()
    assert all(r.get(x, y) is None for x in range(4) for y in range(2))

def test_raster_fill_sets_every_slot():
    r = _Raster(3, 3)
    r.Fill(7, 8, 9)
    assert all(r.get(x, y) == (7, 8, 9) for x in range(3) for y in range(3))

def test_setimage_alpha_zero_is_unlit_and_clips():
    img = Image.new("RGBA", (3, 1), (0, 0, 0, 0))
    img.putpixel((0, 0), (200, 100, 50, 255))
    img.putpixel((1, 0), (9, 9, 9, 0))      # transparent -> black
    r = _Raster(3, 1)
    r.SetImage(img, 1, 0)                     # x=0 of img lands at x=1; img x=2 clipped
    assert r.get(1, 0) == (200, 100, 50)
    assert r.get(2, 0) == (0, 0, 0)
    assert r.get(0, 0) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --extra dev pytest tests/test_flair_laser_plan.py -q`
Expected: FAIL with `ModuleNotFoundError: led_ticker_flair.flair.laser`

- [ ] **Step 3: Implement `_Raster` in `laser.py`**

Flat `list[tuple[int,int,int] | None]` of `width*height`; `SetImage` mirrors core's `HeadlessCanvas.SetImage` (walk `image.load()`, alpha 0 → `(0,0,0)`, write via `SetPixel` so clipping is inherited). Module docstring names the spec path.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --extra dev pytest tests/test_flair_laser_plan.py -q`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add plugins/flair/src/led_ticker_flair/flair/laser.py plugins/flair/tests/test_flair_laser_plan.py
git commit -m "feat(flair): laser — readable _Raster snapshot surface with SetImage"
```

---

### Task 2: `raster_order` — lit-pixel plan per origin

**Files:**
- Modify: `plugins/flair/src/led_ticker_flair/flair/laser.py`
- Test: `plugins/flair/tests/test_flair_laser_plan.py`

**Interfaces:**
- Consumes: `_Raster` (Task 1).
- Produces:
  - `Pixel = tuple[int, int, tuple[int, int, int]]` (x, y, colour).
  - `_ORIGINS = ("top", "bottom", "left", "right")`.
  - `raster_order(raster: _Raster, origin: str, forward_first: bool = True) -> tuple[list[Pixel], bool]` — lit pixels in visit order, and the parity (`forward` flag) the NEXT phase should start with.
  - `_is_lit(px: tuple[int,int,int] | None) -> bool`.

- [ ] **Step 1: Write the failing tests**

```python
from led_ticker_flair.flair.laser import raster_order

def _grid(rows):  # rows: list[str], '#' lit red, '.' unlit, 'k' explicit black
    r = _Raster(len(rows[0]), len(rows))
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch == "#": r.SetPixel(x, y, 255, 0, 0)
            if ch == "k": r.SetPixel(x, y, 0, 0, 0)
    return r

def test_top_origin_rasters_rows_boustrophedon_skipping_empty():
    px, parity = raster_order(_grid(["#.#", "...", ".##"]), "top")
    assert [(x, y) for x, y, _ in px] == [(0, 0), (2, 0), (2, 2), (1, 2)]
    assert parity is True        # row 0 forward, row 2 backward -> next is forward

def test_bottom_origin_starts_at_last_row():
    px, _ = raster_order(_grid(["#..", "..#"]), "bottom")
    assert [(x, y) for x, y, _ in px] == [(2, 1), (0, 0)]

def test_left_origin_rasters_columns():
    px, _ = raster_order(_grid(["#.", "##"]), "left")
    assert [(x, y) for x, y, _ in px] == [(0, 0), (0, 1), (1, 1)]

def test_right_origin_starts_at_last_column():
    px, _ = raster_order(_grid(["#.", "##"]), "right")
    assert [(x, y) for x, y, _ in px] == [(1, 1), (0, 1), (0, 0)]

def test_black_and_unset_are_unlit():
    px, _ = raster_order(_grid(["k#."]), "top")
    assert [(x, y) for x, y, _ in px] == [(1, 0)]

def test_forward_first_false_reverses_first_line():
    px, parity = raster_order(_grid(["##"]), "top", forward_first=False)
    assert [(x, y) for x, y, _ in px] == [(1, 0), (0, 0)]
    assert parity is True

def test_empty_raster_returns_no_pixels_and_keeps_parity():
    assert raster_order(_Raster(2, 2), "left", forward_first=False) == ([], False)

def test_unknown_origin_raises():
    import pytest
    with pytest.raises(ValueError, match="origin"):
        raster_order(_Raster(1, 1), "diagonal")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --extra dev pytest tests/test_flair_laser_plan.py -q`
Expected: FAIL with `ImportError: cannot import name 'raster_order'`

- [ ] **Step 3: Implement `raster_order` and `_is_lit`**

Lines iterate `range(h)` / `range(h-1, -1, -1)` / `range(w)` / `range(w-1, -1, -1)` for top / bottom / left / right; within a line collect lit slots ascending, reverse when `not forward`; flip `forward` only when the line contributed ≥ 1 pixel.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --extra dev pytest tests/test_flair_laser_plan.py -q`
Expected: 12 passed

- [ ] **Step 5: Lint + commit**

Run: `uv run --extra dev ruff check src/ tests/ && uv run --extra dev ruff format --check src/ tests/`

```bash
git add plugins/flair/src/led_ticker_flair/flair/laser.py plugins/flair/tests/test_flair_laser_plan.py
git commit -m "feat(flair): laser — raster_order boustrophedon lit-pixel plan per origin"
```

---

### Task 3: `Laser.frame_at` — snapshot, two phases, beam, snap (ends at a GIF HARD STOP)

**Files:**
- Modify: `plugins/flair/src/led_ticker_flair/flair/laser.py`
- Test: `plugins/flair/tests/test_flair_laser_transition.py`

**Interfaces:**
- Consumes: `_Raster`, `raster_order`, `Pixel`.
- Produces:
  - `class Laser` with class attrs `min_frames = 48`, `scale_switch_at = 1.0`, `_origin = "top"`; `__init__(self) -> None` (no knobs; accept and ignore `**kwargs` is NOT done — `_build_trans_obj` passes only declared kwargs).
  - `frame_at(self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any) -> Canvas`.
  - Per-firing state: `_out: list[Pixel] | None`, `_in: list[Pixel] | None`, `_last_t: float = 1.0`; geometry-keyed `_raster: _Raster | None`, `_raster_key: tuple | None`.
  - Helpers: `_snapshot(self, canvas, widget, cursor_pos: int) -> _Raster` (clears + draws through `ScaledCanvas(raster, scale=canvas.scale, content_height=canvas.content_height)` when `is_scaled(canvas)`); `_visited(self, t: float) -> int`; `_draw_beam(self, real, rw: int, rh: int, head: Pixel) -> None`.

Test fixtures: copy `_StubCanvas` and `_make_widget` from `tests/test_flair_fairy_transition.py` (per-file duplication is the repo convention); give `_StubCanvas` a `SetImage(image, offset_x=0, offset_y=0)` that walks the PIL pixels into `SetPixel` (alpha 0 → black) like core's `HeadlessCanvas`, so the snap frame's live `incoming.draw` works for image widgets. Add `_text_widget(pixels: list[tuple[int,int,tuple]])` — a mock whose `draw` SetPixels the given list onto whatever canvas it is handed (works for both `_StubCanvas` and `_Raster`), and `_image_widget(pil_image)` whose draw calls `unwrap_to_real(canvas).SetImage(img, 0, 0)`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_flair_laser_transition.py
from unittest import mock
import pytest
from PIL import Image
from led_ticker.plugin import ScaledCanvas
from led_ticker_flair.flair.laser import Laser

OUT = [(0, 0, (255, 0, 0)), (1, 0, (255, 0, 0)), (2, 0, (255, 0, 0))]   # n_out = 3
INC = [(5, 1, (0, 255, 0)), (6, 1, (0, 0, 255))]                         # n_in = 2

def test_t0_paints_outgoing_snapshot_only_no_beam():
    c = _StubCanvas(8, 2); p = Laser()
    p.frame_at(0.0, c, _text_widget(OUT), _text_widget(INC))
    assert c._pixels == {(x, y): col for x, y, col in OUT}

def test_erase_frame_hides_visited_and_draws_beam_in_head_colour():
    # N=5; t such that visited == 2 -> int(5*t/0.95) == 2 -> t = 0.4
    c = _StubCanvas(8, 2); p = Laser()
    p.frame_at(0.0, c, _text_widget(OUT), _text_widget(INC)); c.Clear()
    p.frame_at(0.4, c, _text_widget(OUT), _text_widget(INC))
    assert (2, 0) in c._pixels and (0, 0) not in c._pixels     # unvisited painted, visited gone
    assert c._pixels[(1, 0)] == (255, 0, 0)                     # beam over head (top origin: edge is row 0)

def test_write_frame_paints_visited_incoming_over_snap_reset(monkeypatch):
    # visited == int(5*0.77/0.95) == 4 -> 1 incoming written (0.76 sits on a float boundary; avoid it)
    calls = []
    monkeypatch.setattr("led_ticker_flair.flair.laser.snap_reset", lambda cv, bg: calls.append(bg))
    c = _StubCanvas(8, 2); p = Laser()
    p.frame_at(0.0, c, _text_widget(OUT), _text_widget(INC)); c.Clear()
    p.frame_at(0.77, c, _text_widget(OUT), _text_widget(INC), incoming_bg_color=(1, 2, 3))
    assert calls == [(1, 2, 3)]
    assert c._pixels[(5, 1)] == (0, 255, 0) and (6, 1) not in c._pixels
    assert c._pixels[(5, 0)] == (0, 255, 0)                     # beam from top edge to head

def test_outgoing_not_drawn_live_after_snapshot():
    c = _StubCanvas(8, 2); p = Laser(); o = _text_widget(OUT)
    for t in (0.0, 0.2, 0.4): p.frame_at(t, c, o, _text_widget(INC))
    assert o.draw.call_count == 1

def test_snap_draws_incoming_over_bg(monkeypatch):
    calls = []
    monkeypatch.setattr("led_ticker_flair.flair.laser.snap_reset", lambda cv, bg: calls.append(bg))
    c = _StubCanvas(8, 2); p = Laser(); i = _text_widget(INC)
    p.frame_at(0.96, c, _text_widget(OUT), i, incoming_bg_color=(9, 9, 9))
    assert calls[-1] == (9, 9, 9) and i.draw.call_count >= 1
    assert c._pixels[(5, 1)] == (0, 255, 0) and c._pixels[(6, 1)] == (0, 0, 255)

def test_all_incoming_visited_at_0_95():
    c = _StubCanvas(8, 2); p = Laser()
    p.frame_at(0.0, c, _text_widget(OUT), _text_widget(INC))
    assert p._visited(0.95) == 5 and p._visited(0.949) == 4

def test_empty_outgoing_starts_writing_immediately():
    c = _StubCanvas(8, 2); p = Laser()
    p.frame_at(0.0, c, _make_widget(draw_pixel=False), _text_widget(INC)); c.Clear()
    p.frame_at(0.5, c, _make_widget(draw_pixel=False), _text_widget(INC))   # visited = int(2*0.5/0.95) = 1
    assert c._pixels[(5, 1)] == (0, 255, 0)

def test_zero_lit_pixels_both_sides_snaps_cleanly():
    c = _StubCanvas(8, 2); p = Laser()
    for t in (0.0, 0.5, 0.96):
        p.frame_at(t, c, _make_widget(draw_pixel=False), _make_widget(draw_pixel=False))

def test_refire_resnapshots_changed_incoming():
    c = _StubCanvas(8, 2); p = Laser()
    p.frame_at(0.0, c, _text_widget(OUT), _text_widget(INC)); p.frame_at(0.96, c, _text_widget(OUT), _text_widget(INC))
    new = [(7, 1, (9, 9, 200))]
    p.frame_at(0.0, c, _text_widget(INC), _text_widget(new)); c.Clear()
    p.frame_at(0.96, c, _text_widget(INC), _text_widget(new))
    assert c._pixels[(7, 1)] == (9, 9, 200)

def test_equal_t_is_not_a_refire():
    c = _StubCanvas(8, 2); p = Laser()
    p.frame_at(0.3, c, _text_widget(OUT), _text_widget(INC)); out_ref = p._out
    p.frame_at(0.3, c, _text_widget(OUT), _text_widget(INC))
    assert p._out is out_ref

def test_image_widget_snapshots_through_setimage():
    img = Image.new("RGB", (8, 2), (0, 0, 0)); img.putpixel((3, 1), (10, 20, 30)); img.putpixel((5, 1), (1, 2, 3))
    c = _StubCanvas(8, 2); p = Laser()
    p.frame_at(0.0, c, _make_widget(draw_pixel=False), _image_widget(img)); c.Clear()
    p.frame_at(0.96, c, _make_widget(draw_pixel=False), _image_widget(img))   # snap path (live draw via SetImage)
    assert c._pixels[(5, 1)] == (1, 2, 3)
    p.frame_at(0.0, c, _make_widget(draw_pixel=False), _image_widget(img)); c.Clear()
    p.frame_at(0.949, c, _make_widget(draw_pixel=False), _image_widget(img))  # N=2 -> visited 1 -> (3,1) only
    assert c._pixels[(3, 1)] == (10, 20, 30) and (5, 1) not in c._pixels

def test_scaled_canvas_beam_is_one_real_pixel_wide():
    real = _StubCanvas(256, 64); sc = ScaledCanvas(real, scale=4, content_height=8)   # 32-row band, y_offset_real = 16
    p = Laser(); o = _make_widget(draw_pixel=False); i = _text_widget([(0, 0, (0, 200, 0))])  # logical (0,0) = real 4x4 at rows 16..19
    p.frame_at(0.0, sc, o, i); real.Clear()
    p.frame_at(0.3, sc, o, i)   # visited = int(16*0.3/0.95) = 5 real px written, beam on the 5th
    assert sc.y_offset_real == 16
    beam_cols = {x for (x, y) in real._pixels if y < 16}
    assert len(beam_cols) == 1 and (next(iter(beam_cols)), 0) in real._pixels

def test_beam_reaches_real_edge_through_letterbox_band():
    real = _StubCanvas(256, 64); sc = ScaledCanvas(real, scale=2, content_height=16)   # 32-row band centred
    p = Laser(); i = _text_widget([(0, 0, (0, 200, 0))])
    p.frame_at(0.0, sc, _make_widget(draw_pixel=False), i); real.Clear()
    p.frame_at(0.3, sc, _make_widget(draw_pixel=False), i)
    assert (0, 0) in real._pixels                      # top origin: beam starts at REAL row 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --extra dev pytest tests/test_flair_laser_transition.py -q`
Expected: FAIL with `ImportError: cannot import name 'Laser'`

- [ ] **Step 3: Implement `Laser`**

`frame_at` order: refire detect (`t < self._last_t` → drop `_out/_in`), set `_last_t`; `real = unwrap_to_real(canvas)` when scaled else `canvas`; snapshot both sides lazily (`_out = raster_order(snap(outgoing, outgoing_scroll_pos), origin)`, `_in = raster_order(snap(incoming, 0), origin, forward_first=parity_from_out)`); if `t >= SNAP_THRESHOLD`: `snap_reset(canvas, kwargs.get("incoming_bg_color"))`, `incoming.draw(canvas, cursor_pos=0)`, return. Else `v = _visited(t)`; if `v <= n_out`: paint `_out[v:]` via `real.SetPixel`, head = `_out[v-1]` if `v > 0`; else `snap_reset(...)`, paint `_in[:v-n_out]`, head = `_in[v-n_out-1]`; draw beam if head. Beam spans: top `y in range(0, hy+1)` at `hx`; bottom `range(hy, rh)`; left `x in range(0, hx+1)` at `hy`; right `range(hx, rw)`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --extra dev pytest tests/test_flair_laser_transition.py -q`
Expected: 14 passed

- [ ] **Step 5: Lint + commit**

Run: `uv run --extra dev ruff check src/ tests/ && uv run --extra dev ruff format --check src/ tests/ && PYRIGHT_PYTHON_FORCE_VERSION=latest uv run --extra dev pyright src/`

```bash
git add plugins/flair/src/led_ticker_flair/flair/laser.py plugins/flair/tests/test_flair_laser_transition.py
git commit -m "feat(flair): laser — two-phase erase/write frame_at with content-coloured beam"
```

- [ ] **Step 6: Temporary registration + first-look GIF (HARD STOP)**

Register `api.transition("laser.top")(Laser)` in `flair/__init__.py` (Task 4 completes the set). Write `$CLAUDE_JOB_DIR/tmp/laser-first-look.toml`: smallsign display (`rows = 16`, `cols = 32`, `chain_length = 5`), `[transitions] duration = 3.0`, two slideshow sections with `hold_time = 2.0`, `transition = "flair.laser.top"`, one `message` each (`"LASER"` in `[255, 80, 40]`, `"WRITE"` in `[80, 200, 255]`). From the core repo: `make plan-gif CONFIG=$CLAUDE_JOB_DIR/tmp/laser-first-look.toml` for the duration, then the editable-install + `render.py ... -o $CLAUDE_JOB_DIR/tmp/laser-first-look.gif --duration <N>` recipe from Global Constraints. Hand James the gif path and STOP. Expected tuning from his feedback: `min_frames`, beam colour during erase, beam width on scale > 1.

---

### Task 4: Variants, alternating/random, registration, perf tripwires

**Files:**
- Modify: `plugins/flair/src/led_ticker_flair/flair/laser.py`
- Modify: `plugins/flair/src/led_ticker_flair/flair/__init__.py`
- Test: `plugins/flair/tests/test_flair_laser_transition.py`

**Interfaces:**
- Produces: `LaserBottom(Laser)` (`_origin = "bottom"`), `LaserLeft`, `LaserRight`; `LaserAlternating` (`_transitions = [Laser(), LaserRight(), LaserBottom(), LaserLeft()]`, `_index = -1`, `_last_t = 1.0`, `min_frames` property forwarding the next variant, `frame_at` advancing `_index` on `t < _last_t`); `LaserRandom` (same shape, `_rng = random.Random()` instance attr, picks a variant ≠ the previous on each refire). Registered config types: `flair.laser.top/bottom/left/right/alternating/random`.

- [ ] **Step 1: Write the failing tests**

```python
from led_ticker_flair import flair as flair_pkg
from led_ticker_flair.flair.laser import LaserAlternating, LaserBottom, LaserLeft, LaserRandom, LaserRight

def test_registration_six_types_distinct_instances():
    api = mock.Mock(); reg = {}
    api.transition.side_effect = lambda name: (lambda cls: reg.__setitem__(name, cls) or cls)
    api.animation.side_effect = lambda name: (lambda cls: cls); api.widget.side_effect = lambda name: (lambda cls: cls)
    flair_pkg.register(api)
    names = {"laser.top", "laser.bottom", "laser.left", "laser.right", "laser.alternating", "laser.random"}
    assert names <= set(reg)
    assert reg["laser.top"]() is not reg["laser.top"]()

def test_origins_per_variant():
    assert (LaserBottom._origin, LaserLeft._origin, LaserRight._origin) == ("bottom", "left", "right")

def test_alternating_cycles_top_right_bottom_left():
    c = _StubCanvas(8, 2); p = LaserAlternating(); seen = []
    for _ in range(5):
        p.frame_at(0.0, c, _text_widget(OUT), _text_widget(INC)); seen.append(p._transitions[p._index]._origin)
        p.frame_at(0.96, c, _text_widget(OUT), _text_widget(INC))
    assert seen == ["top", "right", "bottom", "left", "top"]

def test_random_never_repeats_back_to_back():
    c = _StubCanvas(8, 2); p = LaserRandom(); p._rng.seed(1); seen = []
    for _ in range(30):
        p.frame_at(0.0, c, _text_widget(OUT), _text_widget(INC)); seen.append(p._transitions[p._index]._origin)
        p.frame_at(0.96, c, _text_widget(OUT), _text_widget(INC))
    assert all(a != b for a, b in zip(seen, seen[1:])) and len(set(seen)) >= 3

def test_min_frames_48_on_every_type():
    assert all(getattr(cls, "min_frames", None) == 48 for cls in (Laser, LaserBottom, LaserLeft, LaserRight))
    assert LaserAlternating().min_frames == 48 and LaserRandom().min_frames == 48

class TestPerfUniformity:
    def test_per_frame_paint_volume_bounded(self):   # copy fairy's loop; widgets = _text_widget(OUT)/_text_widget(INC); panel = 160*16
        ...
    def test_alternating_refire_frames_equally_bounded(self):   # copy fairy's shape with LaserAlternating()
        ...
    def test_full_panel_fill_within_paint_bound(self):
        real = _StubCanvas(256, 64); sc = ScaledCanvas(real, scale=4, content_height=16)
        full = _make_widget(draw_pixel=False, fill=(7, 7, 7)); p = Laser()
        t = 0.02
        while t < 1.0:
            before = len(real.calls); p.frame_at(round(t, 3), sc, full, full)
            assert len(real.calls) - before <= int(1.5 * 256 * 64); t += 0.02
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --extra dev pytest tests/test_flair_laser_transition.py -q`
Expected: FAIL with `ImportError: cannot import name 'LaserAlternating'`

- [ ] **Step 3: Implement the variants and register all six**

In `flair/__init__.py` add the five remaining `api.transition("laser.<v>")(...)` lines beside the Task 3 `laser.top` line; update the module docstring's catalogue sentence.

- [ ] **Step 4: Run the whole flair suite + lint**

Run: `uv run --extra dev pytest tests/ -q` — all pass (includes `test_import_purity`, `test_packaging`, `test_smoke`).
Run: `uv run --extra dev ruff check src/ tests/ && uv run --extra dev ruff format --check src/ tests/ && PYRIGHT_PYTHON_FORCE_VERSION=latest uv run --extra dev pyright src/` — clean.

- [ ] **Step 5: End-to-end type resolution from the core repo**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker
uv pip install -q -e /Users/james/projects/github/jamesawesome/led-ticker-plugins/plugins/flair
uv run --no-sync python -c "
from led_ticker._plugin_loader import load_plugins
load_plugins()
from led_ticker.transitions import get_transition_class
for v in ('top','bottom','left','right','alternating','random'):
    print(v, '->', get_transition_class(f'flair.laser.{v}').__name__)
"
```
Expected: six class names print.

- [ ] **Step 6: Commit**

```bash
git add plugins/flair/src/led_ticker_flair/flair/laser.py plugins/flair/src/led_ticker_flair/flair/__init__.py plugins/flair/tests/test_flair_laser_transition.py
git commit -m "feat(flair): register flair.laser.{top,bottom,left,right,alternating,random} + perf tripwires"
```

---

### Task 5: Benchmarks + full visual gate (HARD STOP for James)

**Files:** scratch only under `$CLAUDE_JOB_DIR/tmp/`.

- [ ] **Step 1: Frame-time sweep (fresh + refire, text + full-panel image)**

Write `$CLAUDE_JOB_DIR/tmp/laser_frametime.py` on the fairy harness shape: no-op `Stub` canvas (256×64) under `ScaledCanvas(scale=4, content_height=16)`, 0.02 t-steps, `LaserAlternating()` for two firings; case A a mock text widget (~600 lit px), case B `fill=(7,7,7)` both sides. Print avg/worst ms per firing per case; assert `worst <= 5 * avg`. Run with `uv run --extra dev python` from `plugins/flair/`. Keep the numbers for the PR body.

- [ ] **Step 2: Fresh-process construction + first frame**

`uv run --extra dev python -c "import time; t=time.perf_counter(); from led_ticker_flair.flair.laser import Laser; p=Laser(); print('construct ms', (time.perf_counter()-t)*1e3)"` then time one `frame_at(0.02, ...)` on the bigsign stub. Expected: construct ~0 ms, first frame ms-class.

- [ ] **Step 3: Gate GIFs**

Two configs, both `[transitions] duration = 3.0`, `hold_time = 2.0`, `message` widgets with `Inter-Bold` on the bigsign (`font_size = 44`) and the default font on the smallsign:
- `$CLAUDE_JOB_DIR/tmp/laser-gate-smallsign.toml` — `rows = 16`, `cols = 32`, `chain_length = 5`; sections: top, bottom, left, right (one each, two widgets per section so the inter-widget firing shows erase + write), alternating (two widgets), one section with `bg_color = [40, 0, 60]` following a section with `bg_color = [0, 40, 40]`.
- `$CLAUDE_JOB_DIR/tmp/laser-gate-bigsign.toml` — `rows = 64`, `cols = 256`, `chain_length = 1`, `default_scale = 4`, `brightness = 70`; same sections plus one `clock` widget section (drift probe) and one `image` section pointing at a bundled asset (e.g. a pokeball sprite from `src/led_ticker_flair/pokeball/sprites/`) to show the full-panel case.
Durations from `make plan-gif CONFIG=...` in the core repo; render with the editable-install recipe to `$CLAUDE_JOB_DIR/tmp/laser-smallsign.gif` and `$CLAUDE_JOB_DIR/tmp/laser-bigsign.gif`. Hand James both paths plus the benchmark numbers and STOP until he approves (expected tuning surface per spec: `min_frames`, recommended duration, beam width on bigsign, erase-beam colour). Fold any tuning back through Tasks 3–4's tests before continuing.

---

### Task 6: Smoke config, README, CLAUDE.md, pyproject description

**Files:**
- Create: `plugins/flair/examples/config.laser-smoke.bigsign.toml`
- Create: `plugins/flair/docs/transition-laser.gif` (the approved bigsign gate gif, or a trimmed re-render)
- Modify: `plugins/flair/README.md` (new `## Laser transition` section after `## Fairy transition`)
- Modify: `plugins/flair/CLAUDE.md` (new `## \`flair.laser\` transition invariants` section; add `laser` to the namespace sentence at the top)
- Modify: `plugins/flair/pyproject.toml:4` (append `flair.laser` to the description)

- [ ] **Step 1: Smoke config**

Copy the header shape of `config.fairy-smoke.bigsign.toml` (prereqs block uses "flair >= the release that ships laser"; never write a number). Sections, each `mode = "slideshow"`, `hold_time = 1.5`, two `message` widgets named for the check: 1 TOP, 2 BOTTOM, 3 LEFT, 4 RIGHT, 5 ALTERNATING (watch two cycles), 6 RANDOM, 7 BG HOLD (`bg_color = [0, 40, 40]` section followed by `bg_color = [40, 0, 60]` section: erased pixels must show teal, written pixels sit on purple from the first write frame, no black flash at the snap), 8 EMPTY ENTRY (first section after a dark/boot: write phase only), 9 CLOCK DRIFT (a `clock` widget as outgoing: no stray pixels at the phase boundary), 10 FULL PANEL (an `image` widget with `bg_color`), 11 PERF FEEL. Preflight line: `led-ticker validate config/config.toml -> expect: No issues found.`

- [ ] **Step 2: Validate the smoke config from the core repo**

Run: `cd /Users/james/projects/github/jamesawesome/led-ticker && uv run --no-sync led-ticker validate /Users/james/projects/github/jamesawesome/led-ticker-plugins/plugins/flair/examples/config.laser-smoke.bigsign.toml`
Expected: `No issues found.`

- [ ] **Step 3: README section**

Mirror the fairy section: one-paragraph description (beam reaches in from an edge, erases the old content pixel by pixel in that content's colours, then writes the new content the same way; works on every widget type), the gif embed, "Requires led-ticker-core >= 4.31", a `### Config` block showing `transition = "flair.laser.top"`, the alternating form, and `[transitions] duration = 3.0` with the note that `min_frames` floors it at 2.4 s. A knobs table with one row: `beams` — positive int, default `3` — number of independent beams, each writing an equal slice of the content (`beams = 1` for the classic single raster). Direction lives in the six types. A `### Notes` list: section bg is never lasered (engine paints it); widget-level fills (image `bg_color`, two_row bands) are; cross-scale pop lands on the snap frame like the other flair text effects.

- [ ] **Step 4: CLAUDE.md invariants**

Bullets (one each, bold lead, tripwire named): snapshot-only erase (no live outgoing draw after the snapshot — drift rationale; `test_outgoing_not_drawn_live_after_snapshot`); lit = set and not black, section bg never in the raster (`test_black_and_unset_are_unlit`); constant pixel speed with `visited(t)` formula and the 0.95 completion (`test_all_incoming_visited_at_0_95`); physical-resolution raster + 1-px beam, `unwrap_to_real` every call, `_Raster` reusable (`test_scaled_canvas_beam_is_one_real_pixel_wide`); `_Raster.SetImage` exists because image widgets paint via `SetImage` and a missing method TRIPS the breaker (`test_image_widget_snapshots_through_setimage`); snap idiom + `scale_switch_at = 1.0`; perf bound (`TestPerfUniformity`).

- [ ] **Step 5: Run suite + lint, commit**

Run: `uv run --extra dev pytest tests/ -q` and the three lint gates — clean.

```bash
git add plugins/flair/examples/config.laser-smoke.bigsign.toml plugins/flair/docs/transition-laser.gif plugins/flair/README.md plugins/flair/CLAUDE.md plugins/flair/pyproject.toml
git commit -m "docs(flair): laser smoke config, README entry, CLAUDE.md invariants"
```

---

### Task 7: Draft PR (James approves the text first)

- [ ] **Step 1: Branch review**

Run from `plugins/flair/`: `uv run --extra dev pytest tests/ -q` and the three lint gates one final time. From the repo root: `git log --oneline main..HEAD` — the Task 1–6 commits only.

- [ ] **Step 2: Draft the PR body and show it to James**

Use the `open-pr` skill (draft PR, succinct body). Body sections: what it does (one paragraph + the gif), "Test on the sign" (branch-ref install line + `docker compose down -v` note, pointing at the smoke config), benchmark numbers from Task 5, and `Closes` the tracking issue if James files one (per memory: review findings go in the PR body, PRs say Closes not Refs). Do NOT open the PR until James OKs the exact text.

- [ ] **Step 3: Open the draft PR, watch CI**

Per the `open-pr` skill. Release after merge word: `uv run python scripts/cut_release.py flair minor --notes <file>`.

---

### Task 8: Docs-site entry (core repo, after the flair release)

**Files (core repo `/Users/james/projects/github/jamesawesome/led-ticker`):**
- Modify: `docs/site/src/content/docs/transitions/sprite.mdx` (frontmatter description + new `### \`flair.laser\`` subsection after `flair.fairy`, line ~391 onward)
- Create: `docs/site/demos-pinned/transition-flair-laser.toml` (copy `transition-flair-fairy.toml`; `transition = "flair.laser.alternating"`, `[transitions] duration = 3.0`, `hold_time = 2.5`, texts `"LASER"` / `"WRITE"`; `# requires-plugins: led-ticker-flair (>= <released version>; render locally with the plugin installed)`)
- Create: `docs/site/public/demos-pinned/transition-flair-laser.gif`

- [ ] **Step 1: Plan + render the pinned demo**

`make plan-gif CONFIG=docs/site/demos-pinned/transition-flair-laser.toml`; add `# render-duration: <N>` to the TOML; render with the editable-install recipe to the public path.

- [ ] **Step 2: Write the mdx subsection**

Heading `### \`flair.laser\` (flair >= <released version>, core >= 4.31)`; paragraph; `<DemoGif src="/demos-pinned/transition-flair-laser.gif" caption="\`flair.laser\` — a content-coloured beam erases the old message pixel by pixel, then writes the new one" />`; the install note sentence copied from the fairy entry; a `<TomlExample>` with the alternating form and `duration = 3.0`; the two Notes from the README. Follow `docs/DOCS-STYLE.md`.

- [ ] **Step 3: Docs lint + commit on a core branch**

Run: `make docs-lint` (core repo). Commit `docs: flair.laser transition catalogue entry + pinned demo`, open a draft PR via `open-pr` after James OKs the text.
