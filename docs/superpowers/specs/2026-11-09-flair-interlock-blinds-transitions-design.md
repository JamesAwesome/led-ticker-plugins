# flair.interlock + flair.blinds transitions — design

**Date:** 2026-11-09
**Status:** awaiting approval (brainstorm with James)
**Inspiration:** two classic LED-sign effects missing from the catalogue.

- **Interlock** is a BetaBrite / Alpha-protocol special mode: the even pixel
  rows race in from one end of the sign while the odd rows race in from the
  other, and the two sets mesh into the message. It is NOT the whole message
  sliding in from both sides (that is Alpha's separate "Slide" mode).
- **Blinds** (a.k.a. "shutter") is the venetian-blind reveal on modern
  HD/Huidu-class controllers and video tools: the panel is cut into N equal
  slats and every slat wipes open at the same time, in the same direction.
  The 3D "each slat rotates on its own axis" variant some video tools ship is
  a different effect and is out of scope.

James asked for "the classic definition" of each, with the variant modes
flair already uses (`.<direction>` / `.alternating` / `.random`, the laser
shape).

## Goals

- Faithful classic look on both reference signs (smallsign 160×16 scale 1,
  bigsign 256×64 scale 4), for every widget the other snapshot transitions
  handle (text, two_row, gif/image/still, bordered, bg-coloured sections).
- Same variant family as `flair.laser`: fixed-direction types plus
  `.alternating` and `.random`.
- No new core seams; core floor unchanged.

## Non-goals

- Interlock's 3D/rotating or staggered-cascade variants; blinds' rotating
  slats or cascaded (staggered) slats. Possible later knobs, not this PR.
- Per-character effects (split-flap, slot machine) — separate issues.

## Anti-goals (would be a failure even if it technically works)

- Interlock that reads as two half-transparent pushes overlapping, rather
  than strands visibly meshing. Strands must be wide enough to read as
  strands on both signs (see "Strand width").
- Blinds that reads as a plain wipe (too few slats) or as noise (too many).
- Any stretch where the panel sits empty mid-transition (interlock's single
  `t = 0.5` cut-over frame is the one accepted exception), or a stray
  "border on black" flash at the snap.

---

## flair.interlock

### What it does

Two phases, split at `t = 0.5`:

1. **Split (t < 0.5)** — the outgoing content is cut into *strands* (bands of
   rows for horizontal, bands of columns for vertical). Alternate strands
   slide off toward opposite edges: even strands one way, odd strands the
   other, until the panel is empty at `t = 0.5`.
2. **Mesh (0.5 ≤ t < SNAP_THRESHOLD)** — the incoming content's strands enter
   from opposite edges (even from one side, odd from the other) and lock
   together exactly in place at `t = SNAP_THRESHOLD`.
3. **Snap (t ≥ 0.95)** — `snap_reset(canvas, incoming_bg_color)` +
   `incoming.draw(canvas, cursor_pos=0)` (flair snap idiom).

Alpha only documents the mesh-in half; the split-out half is our addition so
the transition owns both widgets (James approved the split-then-mesh shape).

Conveyor direction (my call): each parity keeps ONE travel direction across
both phases. Even outgoing strands exit to the right and even incoming
strands enter from the left; odd strands mirror that. Every strand then
reads as a single conveyor belt. The alternative (exit back toward the edge
the incoming strand will come from) reads as a bounce; confirm at the
visual gate.

### Variants (registered types)

| type | strands | even strands travel | odd strands travel |
|---|---|---|---|
| `flair.interlock.horizontal` | row bands | left → right | right → left |
| `flair.interlock.vertical` | column bands | top → bottom | bottom → top |
| `flair.interlock.alternating` | cycles horizontal → vertical | | |
| `flair.interlock.random` | picks per firing from 4 (axis × parity flip), never the same back-to-back (WipeRandom policy) | | |

`horizontal` is the Alpha classic; `vertical` is the natural extension.
`.random`'s parity flip (even strands from the right instead of the left) is
what gives it four distinct choices — with only two axes, a no-repeat random
would otherwise be identical to `.alternating` (my call).

### Strand width

- A strand is `strand` LOGICAL rows (or columns) tall, i.e. `strand × scale`
  real pixels; knob `strand` (positive int, default **1**). On the smallsign
  that is one LED row — the literal classic. On the bigsign it is one
  logical row = 4 real rows, so block-scaled text meshes along its own pixel
  grid instead of slicing each logical pixel into four comb teeth.
- Strand bands are anchored at the wrapper's content top
  (`y_offset_real`) so they align with the logical grid; the letterbox bands
  above/below content (when `content_height × scale < panel_h`) belong to
  the nearest strand. Vertical strands are anchored at x = 0.
- Hi-res text on the bigsign still meshes in 4-real-row strands; that is
  intended (the strands are the sign's "rows", not the font's).

### Motion

- **Content-sized travel (decided by James 2026-11-09, after the builder
  check):** the travel distance comes from the snapshot's LIT extent, not
  the panel size. Panel-size travel left centred text blank for ~1/3 of the
  transition. Per snapshot and per travel direction, `D` is the distance
  that just clears the lit content off the edge it moves toward. For
  horizontal, with lit x-extent `[lo, hi]` of that PARITY GROUP's pixels,
  `D_right = W − lo` and `D_left = hi + 1`. Vertical is the same with y and
  H. All strands moving the same way share one `D`, so they move in
  lockstep (classic). An empty snapshot has nothing to move. (Per-parity
  rather than whole-snapshot is an implementation ruling: a whole-snapshot
  extent lets one parity clear before t = 0.5.)
- Offset is a pure function of `t`. In the split phase,
  `d = D · (t / 0.5)`, so the outgoing has just cleared at `t = 0.5`. In the
  mesh phase, `d = D · (1 − (t − 0.5) / (0.95 − 0.5))`, so the incoming
  starts at its edge and lands at 0.95. Both are clamped. The only empty
  frame is the `t = 0.5` cut-over itself, which is accepted and is what
  makes the bg/scale switch invisible. Motion is linear in the runner's
  (already eased) `t`; `easing = "ease_out"` gives the "lock-in" snap. The
  builder may add an internal ease if linear looks mechanical at the visual
  gate.
- Integer real-pixel offsets (round, don't truncate) so strands move
  smoothly at real-pixel grain on the bigsign.

### Scale, bg, cross-scale (accordion pattern)

- Keep the runner's default `scale_switch_at` (0.5). The runner paints the
  outgoing bg for `t < 0.5` and the incoming bg for `t ≥ 0.5`; the split
  phase empties the panel exactly at the cut-over, so bg changes are
  invisible.
- Outgoing snapshot is taken on the first frame of a firing; the incoming
  snapshot is taken LAZILY on the first `t ≥ 0.5` frame from that frame's
  (possibly re-wrapped) canvas, so a cross-scale incoming meshes in at its
  native size (accordion precedent).
- Snapshot-only: neither widget is drawn live after its snapshot (except the
  snap draw). Refire detector `t == 0.0 or t < _last_t` (accordion).
- Reuse `flair/_raster.py` (`Raster`, `snapshot_into`, `is_lit`) unchanged;
  rasters re-allocated only when geometry changes (laser's key).
- All painting is `real.SetPixel` on `unwrap_to_real(canvas)` re-derived
  every call (constraint #1).

### Border and backgrounds

- My call: no ring special-casing — a widget's border is part of its
  snapshot and splits/meshes with the content. If the visual gate shows a
  static ring reads better, port accordion's `_border_only` approach in a
  follow-up, not this PR.
- Lit = `is_lit` (set and not pure black), so section `bg_color` never moves
  and image letterbox black isn't strand-shifted.

### Knobs

`strand` (above). Plus the runner's `duration` / `easing`. `.alternating` /
`.random` forward `strand` to their sub-instances.

### Timing

`min_frames = 24` (1.2 s at 50 ms). Alpha's interlock is brisk; recommend
`duration = 1.5` in docs. My call; tune at the visual gate.

### Perf

Per frame: one pass over the active snapshot's lit pixels (≤ panel px),
each SetPixel'd at a shifted x/y; pixels shifted off-panel are skipped.
Pre-group lit pixels by strand + parity at snapshot time so the per-frame
loop is a flat list walk. `TestPerfUniformity` shape as laser (≤ 1.5× panel
px per frame on bigsign dims, first firing and refire).

---

## flair.blinds

### What it does

- The panel is split into `slats` equal bands: horizontal bands for
  `.down`/`.up`, vertical bands for `.left`/`.right`. Horizontal bands split
  the CONTENT band, anchored at `y_offset_real` like interlock's strands,
  and letterbox rows fold into the first and last slat. This changed after
  the final review: a full-panel split showed only 2 of 4 slats over the
  content on a letterboxed sign. Smallsign and bigsign have no letterbox, so
  they're unaffected. Pending James's confirmation at the visual gate.
- Every slat opens simultaneously from its leading edge: at progress `p`
  (`p = min(t, 0.95) / 0.95`) the first `round(p × slat_size)` real
  rows/columns of EACH slat show the incoming; the rest show the outgoing.
- At `t ≥ 0.95`: flair snap idiom.
- No leading-edge sweep line (classic blinds have none; wipe already owns
  the sweep-line look). Possible later `edge_color` knob.

### Variants (registered types)

| type | slats | each slat opens |
|---|---|---|
| `flair.blinds.down` | horizontal | top → bottom |
| `flair.blinds.up` | horizontal | bottom → top |
| `flair.blinds.right` | vertical | left → right |
| `flair.blinds.left` | vertical | right → left |
| `flair.blinds.alternating` | cycles down → right → up → left (laser order) | |
| `flair.blinds.random` | picks from the four, never back-to-back | |

### Slat geometry

- Knob `slats` (positive int). Default depends on orientation (my call):
  **8** horizontal slats (smallsign: 2 rows each; bigsign: 8 real rows =
  2 logical rows each; raised from 4 at the visual gate, where 4 read as
  about 2 bands) and **8** vertical slats (smallsign 20 px, bigsign
  32 real px each). `.alternating`/`.random` with an explicit `slats` use it
  for both orientations; without it each orientation keeps its default.
- Slat boundaries snap to multiples of `scale` real pixels so a slat edge
  never splits a logical pixel at rest; the opening edge inside a slat moves
  at real-pixel grain (smooth on the bigsign). Remainder pixels go to the
  last slat.
- Validate: `slats` clamped so every slat is ≥ 1 logical pixel; a
  non-positive / non-int / bool `slats` raises `ValueError` at construction
  (laser `_coerce_beams` shape).

### Scale, bg, cross-scale (laser pattern)

- Both widgets are on screen together, so `scale_switch_at = 1.0` (hard-
  edged family convention) and BOTH snapshots are taken on the first frame
  of a firing. Cross-scale incoming renders at the outgoing scale until the
  snap — same accepted limitation as laser / fairy / lightning.
- The runner fills the outgoing bg for the whole transition. Blinds paints
  the revealed region's incoming bg itself: one `SubFill` per slat with
  `incoming_bg_color` (black when `None`), then the incoming lit pixels in
  the revealed region, then the outgoing lit pixels in the unrevealed
  region.
- Snapshot-only, refire `t < _last_t`, `_raster.py` reuse, `unwrap_to_real`
  every call — as interlock.

### Knobs

`slats` (above) plus `duration` / `easing`.

### Timing

`min_frames = 16` (0.8 s). Recommend `duration = 1.0`. My call; tune at the
visual gate.

### Perf

Per frame: ≤ `slats` SubFills + one pass over each snapshot's lit pixels,
each tested against its slat's reveal edge (precompute per-pixel slat
offset at snapshot time) → ≤ 2× panel px SetPixel-equivalent worst case,
same tripwire shape (≤ 1.5× panel px counting only SetPixel, SubFill counted
as one call).

---

## Shared

### Registration

New modules `flair/interlock.py` and `flair/blinds.py`; `register(api)` in
`flair/__init__.py` adds the ten types after the accordion block. Thin
subclasses per fixed variant (laser `_origin` shape). The alternating /
random wrappers follow laser's `_LaserMulti` shape; with three users now,
the builder MAY extract a shared delegate base into `flair/_variants.py` —
if so, migrate only the two new transitions; leave laser untouched.

Imports only from `led_ticker.plugin` (`Canvas`, `ScaledCanvas`,
`is_scaled`, `unwrap_to_real`, `snap_reset`, `SNAP_THRESHOLD`). No
`from __future__ import annotations`. Core floor stays where it is.

### Tests (per transition: `_plan.py` pure math + `_transition.py`)

- Pure math: strand assignment / parity per pixel for both axes and both
  `strand` widths, at scale 1 and 4 (bigsign strand = 4 real rows,
  anchored at `y_offset_real`); slat boundaries snap to `scale`; reveal
  count per slat at given `p`.
- Endpoints: t = 0 is outgoing only (unshifted / unrevealed); t ≥ 0.95 is
  incoming over its bg with no stray black pixels.
- Interlock: content-sized `D` per direction from the lit extent (centred,
  left-hugging, right-hugging, empty). Centred text has outgoing pixels on
  screen until just before 0.5 and incoming pixels on screen from just after
  0.5, so the only empty frame is t = 0.5. The first `t ≥ 0.5` frame
  triggers the lazy incoming snapshot, through the re-wrapped canvas on
  cross-scale.
- Blinds: revealed region gets `SubFill(incoming_bg)`; incoming pixels only
  in revealed rows/cols; outgoing only in unrevealed.
- Snapshot-only drift probe (no live `outgoing.draw` after snapshot), image
  widget via `SetImage`, refire re-snapshots, alternating cycle order,
  seeded random never repeats, knob validation, registration (ten types,
  distinct instances), `TestPerfUniformity`.

### Performance verification (lightning-convention gates)

Frame-time sweep on bigsign dims (256×64, scale 4), fresh + refire, text and
full-panel-image cases: worst ≤ 5× avg, no phase-boundary outlier (interlock
has one at t = 0.5 — the lazy incoming snapshot; it must stay ms-class);
numbers in the PR body.

### Visual gate — HARD STOP for James before the PR

Bigsign + smallsign GIFs: every fixed variant at least once, alternating
across two firings, a bg_color section with different in/out bgs, a
bordered message, a two_row, a full-panel gif, and an empty-outgoing entry.
Tuning surface: interlock exit direction (conveyor vs bounce), `strand`
default on the bigsign, ring behaviour, `slats` defaults, `min_frames`,
recommended durations. Render via the `making-a-gif` skill; bigsign renders
need the rows=64/cols=256/chain=1 config copy.

### Deliverables

- `interlock.py`, `blinds.py`, registration, tests.
- flair `CLAUDE.md` invariants sections for both (laser-section shape) and
  the namespace summary line updated.
- Smoke configs `plugins/flair/examples/config.interlock-smoke.bigsign.toml`
  and `config.blinds-smoke.bigsign.toml` (laser smoke shape).
- flair README entries + committed demo GIFs.
- Core repo docs: entries on `docs/site/src/content/docs/transitions/sprite.mdx`
  (the flair-pack page) with pinned demos
  `docs/site/demos-pinned/transition-flair-interlock.toml` /
  `transition-flair-blinds.toml` (GIFs in `public/demos-pinned/`), following
  the laser entry (#503); demo TOML and the page snippet match verbatim.
- Release after merge word: `cut_release.py flair minor`.

Suggested PR split (my call): one PR per transition (interlock first —
it's the Alpha classic), docs PR in core after each release.

### Left to the builder

- Internal data layout of the per-strand / per-slat pixel lists.
- Whether to extract `_variants.py` (see Registration).
- Exact smoke-config copy and GIF render durations.
