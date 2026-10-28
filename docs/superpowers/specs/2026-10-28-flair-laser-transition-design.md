# flair.laser transition — design

**Date:** 2026-10-28
**Status:** approved (brainstorm with James)
**Inspiration:** the "laser" display-entry effect on commercial LED message
signs (Huidu / HD-class controllers list it alongside wipe, expand, shutter,
snow). A beam reaches in from one panel edge and writes the content pixel by
pixel, rastering back and forth until the whole message is on the sign.

## Why a transition, not an animation (decided)

- The `Animation` protocol only returns a text slice, a rotation, or a lens;
  it never touches pixels and only exists on `message` / `gif` / `image`.
  The laser needs the fully rendered content as pixels so each beam can take
  the colour of the pixel it lands on, and it should work on every widget
  (clock, scores, weather, two-row).
- Commercial signs treat laser as a display-entry effect. led-ticker's
  entry-effect seam is `entry_transition` / `widget_transition`.
- Pacing lands on the existing transition `duration` knob.

Accepted cost: a single-widget section with `loop_count > 1` fires the laser
once on entry, not per loop (typewriter re-types per loop).

## What it does

Six registered variants, named by **beam origin** (the panel edge the beam
reaches in from):

| type | beam | raster |
| --- | --- | --- |
| `flair.laser.top` | vertical bar from the top edge down to the head pixel | row by row, top row first |
| `flair.laser.bottom` | vertical bar from the bottom edge up | row by row, bottom row first |
| `flair.laser.left` | horizontal bar from the left edge rightward | column by column, left column first |
| `flair.laser.right` | horizontal bar from the right edge leftward | column by column, right column first |
| `flair.laser.alternating` | cycles top → right → bottom → left, one per firing | as the current variant |
| `flair.laser.random` | picks one of the four per firing | as the picked variant |

Direction is NOT a knob; it lives in the variants (sprite-family / wipe
convention).

Two phases, one continuous raster, at **physical resolution** on both
builds:

### Erase phase (first `n_out / (n_out + n_in)` of the transition)

- The outgoing widget is snapshotted once per firing into an offscreen
  readable raster (drawn at `outgoing_scroll_pos`). Its lit pixels are
  collected in raster order (see **Raster order**). `n_out` = count.
- Each frame: every lit snapshot pixel NOT yet visited by the head is
  painted via `real.SetPixel` in its snapshot colour, then the beam is
  drawn. The outgoing widget is NOT drawn live per frame (builder-check
  call): a live draw can drift from the one-shot snapshot over a ≥2.4 s
  transition (a clock's seconds, a source refresh) and leave pixels the
  head never erases, which would then vanish abruptly at the phase boundary.
  The snapshot is drawn through the same wrapper at real resolution, so
  hires glyphs are byte-identical to the panel's own render.
- Erased pixels take the OUTGOING background colour: the runner's per-frame
  `Fill(outgoing_bg)` already shows through where nothing is painted, so an
  erased pixel is simply no longer painted (black when the section has no
  bg). Nothing "burns to black" over a coloured background.
- The beam is a solid 1-real-pixel-wide bar from the origin edge to the head
  pixel inclusive, in the colour of the pixel being erased (my call, James
  did not object: a red headline is erased by red beams; rainbow text by
  rainbow beams).
- Pixels not yet reached stay lit, so the old message is visibly eaten from
  the origin edge.
- An outgoing with zero lit pixels (boot, wake from dark, blank widget)
  makes this phase zero-length: the transition goes straight to writing.

### Write phase (remainder)

- The incoming widget is snapshotted once per firing into a second readable
  raster (drawn at `cursor_pos=0`). Lit pixels collected in raster order;
  `n_in` = count.
- Each frame: `snap_reset(canvas, incoming_bg_color)` (Fill with the
  section bg or Clear), then every lit pixel already visited is painted via
  `real.SetPixel` in its snapshot colour, then the beam is drawn in the
  colour of the pixel being written. The runner's own per-frame
  Fill/Clear is overridden by the `snap_reset` so the incoming `bg_color`
  shows from the first write frame.
- Written pixels stay lit. Dark pixels are never visited (the head jumps
  over them; the bar relocates).

### Snap (t ≥ `SNAP_THRESHOLD` 0.95)

Standard idiom: `snap_reset(canvas, incoming_bg_color)` + full
`incoming.draw(canvas, cursor_pos=0)`. The write phase is scheduled to
complete at t = 0.95 (all `n_in` pixels visited), so the snap changes
nothing visible on a same-scale transition.

## Raster order

- Lines are **physical** rows (top/bottom) or **physical** columns
  (left/right) of the real canvas. On the bigsign (scale 4) a logical pixel
  is a 4×4 block and gets written in four passes of four pixels: this is the
  intended "cell by cell" look, and the beam stays one real pixel wide.
- The first line is the one nearest the origin edge; lines advance away from
  it. Within a line the head moves one way, then reverses on the next line
  (boustrophedon). Lines with no lit pixels are skipped entirely (no
  frames spent on them).
- The write phase restarts at the origin edge but **continues the sweep
  parity** from where the erase phase ended (if the erase's last line ran
  right→left, the write's first line runs left→right). My call; it keeps the
  "one beam, one continuous raster" feel without a visible reset.
- A pixel counts as **lit** when the snapshot slot is set AND its colour is
  not pure black `(0, 0, 0)`. Widgets that paint their own black fill (gif
  pillars, image letterbox) are therefore not "written" pixel by pixel.
- **Section bg never enters a snapshot (builder-check finding, resolved
  without a core change).** The section `bg_color` is painted by the engine
  (`reset_canvas` / `run_transition`'s per-frame `Fill`), never by the
  widget, so a snapshot drawn through our own raster contains only the
  widget's content. The erase phase needs no outgoing-bg knowledge: an
  erased pixel simply stops being painted and the runner's
  `Fill(outgoing_bg)` shows through. No `outgoing_bg_color` kwarg, no core
  release, core floor stays `>= 4.31`. Widget-LEVEL fills are content and
  get lasered like everything else: an `image`/`gif` widget with its own
  `bg_color` field, or a `two_row` with band colours, writes its fill pixel
  by pixel (bounded by panel px; see **Perf contract**).

## Timing

- One `[transitions] duration` covers both phases. The head moves at
  **constant speed in lit pixels**: with `N = n_out + n_in`, the number of
  pixels visited at progress `t` is `floor(N · min(t, 0.95) / 0.95)`; the
  first `n_out` of them are erase visits. Time therefore splits in
  proportion to the two pixel counts, not a fixed 50/50.
- `min_frames = 48` (2.4 s at the 50 ms tick) is the floor so the global
  0.5 s default can't make it a 10-frame blur. Docs recommend
  `duration = 3.0` for a full 160-px line, in line with typewriter's
  ~150 ms/char (a 20-char message ≈ 3 s). My call; tune after the visual
  gate.
- `linear` easing is the intended look; other easings simply speed the
  head up or down and are allowed.
- There is no settle/`frames_to_rest` interaction: the transition owns its
  whole timeline.

## Scale, bg, cross-scale

- `scale_switch_at = 1.0` (hard-edged family convention): the runner keeps
  the outgoing bg and outgoing-scale wrapper for the whole transition. The
  erase phase inherits the runner's outgoing-bg Fill; the write phase paints
  the incoming bg itself via `snap_reset` each frame.
- Cross-scale (incoming section at a different `scale`): the incoming
  snapshot is drawn through the CURRENT (outgoing-scale) wrapper, so the
  write phase renders incoming content at the outgoing scale and the size
  pop lands on the final snap frame. Same accepted limitation as
  `flair.fairy` / `flair.lightning` / `flair.fireworks`.
- Readable raster: a small plugin-local `_Raster` (SetPixel / SubFill /
  Clear / Fill / **SetImage** / `get(x, y)`, out-of-bounds writes ignored)
  sized to the REAL canvas. `SetImage(pil_image, x, y)` decodes the image
  into slots so `gif` / `image` / `still` widgets (which paint via
  `unwrap_to_real(canvas).SetImage`) snapshot correctly instead of tripping
  the breaker with an AttributeError (builder-check call: image widgets are
  IN scope). Pillow is already a core dependency; importing `PIL` does not
  violate `test_import_purity` (which only polices `led_ticker.*` imports).
  The raster is wrapped in `ScaledCanvas(raster, scale=canvas.scale,
  content_height=canvas.content_height)` when `is_scaled(canvas)` so
  widgets draw into it exactly as they draw into the panel (hires widgets
  reach the raster via `unwrap_to_real`). Core's `PixelBuffer` is not on
  the public plugin surface; the plugin-local raster avoids a core release
  and a floor bump. `real` is re-derived from the live canvas on every call
  and never cached (constraint #1).
- Snapshots are per firing: `t < self._last_t` is the refire detector
  (spinout / fairy precedent) and invalidates both rasters and the pixel
  lists. The rasters are re-allocated only when the canvas geometry changes
  (`matches`-style key of real width, height, scale, content_height).

## Perf contract

Per frame: at most `n_out` (erase, unvisited) or `n_in` (write, visited)
SetPixels, one `snap_reset` in the write phase, plus a beam of at most one
panel dimension. Every quantity is bounded by the physical pixel count, so work is
uniform by construction. Snapshot + lit-pixel extraction happens once per
firing (two widget draws and one pass over the raster). Same committed
`TestPerfUniformity` tripwire shape as fairy / lightning: per-frame SetPixel
≤ 1.5× panel px on bigsign dims, first firing and refire. A full-panel gif
on the bigsign is the worst case (~16k lit pixels ≈ panel px per frame):
`Dissolve` already does the same SetPixel count at its t=0.5 peak on the
bigsign, so the budget is proven; the perf sweep (gate 1) adds a
full-panel-image case to confirm it.

## Beams (added 2026-10-28 after the first-look gifs)

James's reaction to the single-beam gif was "I'm imagining not a single
laser but everything lasering in at once or a couple lasers." A spike
rendered 1, 2, 3 beams and an every-line-at-once mode; his pick: **default
3 beams**, every-line-at-once dropped ("doesn't look like it actually
writes things in correctly, it just looks like a blur unrelated to the
final letters").

- `beams` (positive int, default **3**): the lit CONTENT extent (union of
  the outgoing and incoming lit pixels along the across axis — width for
  top/bottom, height for left/right) is split into `beams` near-equal
  contiguous slices, one independent beam per slice. Splitting the panel
  width instead would hand a centred headline to a single beam. Clamped to
  the extent width (a 2-px-wide content gets at most 2 beams).
- Each beam owns its own (erase, write) pixel lists and visits them at its
  own constant speed (`visited_k(t) = floor(n_k · min(t, 0.95) / 0.95)`),
  so beams with less to do start writing earlier than their neighbours and
  every beam finishes at t = 0.95.
- The bg cuts over to the incoming section (per-frame `snap_reset`) the
  moment the FIRST beam starts writing; beams still erasing then show their
  outgoing pixels on the incoming bg. Unavoidable with concurrent beams and
  accepted. With `beams = 1` this is exactly the single-beam behaviour above.
- Two snapshot rasters are kept alive at once (outgoing + incoming) so the
  content extent can be computed over both.
- `flair.laser.alternating` / `.random` forward `beams` to their four
  sub-transitions: `transition = {type = "flair.laser.alternating", beams = 2}`.

## Knobs

`beams` (above). Nothing else beyond the runner's `duration` / `easing`.
`transition_colors` does not reach plugin transitions and is irrelevant here
(the beam is always content-coloured). A future `beam_color` override is
possible but not in scope.

## Registration

`Laser` class in `plugins/flair/src/led_ticker_flair/flair/laser.py` with
an `_origin` class attribute (`"top"` / `"bottom"` / `"left"` / `"right"`)
and thin subclasses `LaserBottom` / `LaserLeft` / `LaserRight`;
`LaserAlternating` and `LaserRandom` wrap four instances (the
`FairyAlternating` / `WipeAlternating` shape, `min_frames` forwarded).
`register(api)` adds `api.transition("laser.top")(...)` through
`("laser.random")`. Each registered type constructs independently with its
own state. No new core seams: uses `Canvas`, `ScaledCanvas`, `is_scaled`,
`unwrap_to_real`, `snap_reset`, `SNAP_THRESHOLD` from `led_ticker.plugin`.
Core floor stays `>= 4.31`.

## Tests (`plugins/flair/tests/test_flair_laser_plan.py` + `_transition.py`)

- Plan: raster order for each origin on a small synthetic raster (first
  line nearest the origin edge, boustrophedon, empty lines skipped), lit
  detection ignores black and the bg colour, write phase continues parity.
- Timing: proportional split (n_out=30, n_in=10 → erase ends at
  t ≈ 0.7125); zero outgoing → first frame after t=0 is already writing;
  all `n_in` visited at t = 0.95.
- Endpoints: t=0 shows outgoing only, no beam; t ≥ 0.95 is incoming over
  bg with no stray black pixels (fill (7,7,7) incoming, both geometries).
- Erase frame: unvisited pixels painted in snapshot colours, visited
  pixels NOT painted (bg shows through), beam from the origin edge to the
  head in the head pixel's colour, no live `outgoing.draw` after the
  snapshot (drift probe: a widget whose draw output changes between calls
  erases cleanly).
- Lit detection: `None` slots and pure black are unlit; any other colour
  (including a widget-level fill colour) is lit.
- Image widgets: a widget that paints via `SetImage` snapshots into the
  raster at real resolution; the write phase reproduces it pixel by pixel.
- Write frame: `snap_reset` called with `incoming_bg_color`; visited pixels
  in snapshot colours; unvisited absent; beam colour = head pixel colour.
- Scaled canvas: through a `ScaledCanvas` at scale 4 the beam is 1 real px
  wide and the write lands at real-pixel grain (not block-expanded).
- Refire: `t < last_t` re-snapshots (a changed incoming widget writes the
  new content); alternating cycles top → right → bottom → left; random
  picks from the four (seeded `random.Random` for the test).
- Registration: six `laser.*` types present, distinct instances.
- Perf uniformity tripwires as above.

## Performance verification (mandatory, lightning-convention gates)

1. Frame-time sweep on bigsign dims (256×64, scale 4), fresh instance +
   refire, text case AND full-panel-image case: worst ≤ 5× avg, no
   phase-boundary outlier; numbers in the PR body.
2. Fresh-process construction (~0) + first-ever frame (ms-class).
3. The committed `TestPerfUniformity` tripwires.

## Visual gate

Bigsign + smallsign GIFs (all four origins at least once; alternating across
two firings; one bg_color section; one empty-outgoing entry) — HARD STOP for
James before the PR. Expected tuning surface: `min_frames`, recommended
`duration`, whether the beam should be `scale` px wide on the bigsign
instead of 1 px, beam colour during erase.

## Deliverables

- `laser.py` + registration + tests.
- Bigsign smoke config `plugins/flair/examples/config.laser-smoke.bigsign.toml`
  (sections: top / bottom / left / right / alternating / random / bg-hold
  with DIFFERENT outgoing and incoming bgs / empty-entry / clock drift probe
  / full-panel gif / perf-feel), trimmed to the fairy smoke shape.
- flair README entry + committed demo GIF. Docs-site entry on
  `transitions/sprite.mdx` ("Text-effect transitions") in the core repo with
  a `demos-long/transitions-laser.toml` demo, following the fairy entry.
- Release after merge word: `cut_release.py flair minor`.

## Left to the builder

- Internal data layout of the lit-pixel lists (flat list of
  `(x, y, (r, g, b))` is fine) and how the phase boundary index is cached.
- Whether `LaserAlternating` / `LaserRandom` share a tiny base or are two
  short classes.
- Exact smoke-config section copy and GIF render durations (use the
  `making-a-gif` skill's planner).
