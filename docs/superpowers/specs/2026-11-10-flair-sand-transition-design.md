# flair.sand transition — design

**Date:** 2026-11-10
**Status:** awaiting approval (brainstorm with James)
**Mockup:** `.superpowers/brainstorm/5132-1794349641/content/sand-fill.html`
(option A; local, git-ignored)

The outgoing content crumbles into sand and falls off the bottom of the
panel. Then the incoming content forms out of sand that pours in from the
top. This is a sibling of `flair.snow`: same plugin, same snapshot approach,
but a different look.

## Intent

James wants a transition that feels physical: the old message falls apart
into grains and drops away, and the new one is built grain by grain. It
should read as sand, not as a dissolve or a wipe.

## Goals

- **Crumble (outgoing).** Every lit pixel of the outgoing widget becomes one
  grain in that pixel's own colour, so rainbow text falls as rainbow sand.
  Each grain lets go at its own slightly random moment, so the word comes
  apart unevenly ("whole-wordish, a little random") instead of in a clean
  line. Once released, a grain falls under gravity with a small sideways
  drift and leaves through the bottom edge. Grains do not pile up.
- **Pour (incoming).** Only the grains of the incoming widget's lit pixels
  fall, starting above the top edge and already in their final colours.
  Each grain drops **straight down** and stops dead at its target pixel
  (James: "straight drop sounds right"). Grains do not tumble or slide. The
  bottom rows land first, with jitter, so the content builds upward. The
  rest of the panel stays dark (or shows the section `bg_color`).
- **Everything that's drawn turns to sand.** Text, border and background
  all crumble and re-form, because the widget snapshot captures the whole
  `draw()` output. An animated background is captured as one still frame.
- **Grain = one real LED.** On the bigsign, grains run at physical
  resolution, which gives 16 grains per logical pixel at scale 4, the same
  reasoning as core constraint #11 for dissolve. On the smallsign, one grain
  is one pixel.
- **Length:** about 3 s in total, split roughly evenly between crumble and
  pour (James approved the mockup's ~1.4 s + ~1.5 s).

## Non-goals

- Grains piling up at the bottom, settling, or sliding sideways when they
  land.
- Option B from the mockup (fill the whole panel, then drain away the plain
  filler).
- Direction variants (`.up`, `.alternating`, …). Sand falls down. A single
  type is enough.

## Anti-goals (a failure even if it technically works)

- Reads as a dissolve: pixels popping in and out in place instead of
  visibly travelling.
- The whole word falls as one rigid block, or comes apart in a straight
  row-by-row sweep.
- Grains coarser than one real LED on the bigsign (4×4 logical blocks
  falling).
- Any new core seam or machinery. James: "don't want to invent new
  machinery."

## Constraints

- **No new core API.** Core floor is unchanged. The transition is built only
  from `led_ticker.plugin` exports, as `flair.snow` and `flair.blinds` are.
- **No GetPixel (core constraint #3).** The outgoing and incoming pixels
  come from the existing flair snapshot helpers (`_raster.Raster`,
  `snapshot_into`, `_snapshot.SnapshotCache`). They draw each widget into a
  readable plugin-local raster once per firing.
- **Snapshot black is not a grain.** `_raster.is_lit` excludes unset pixels
  and pure black. The section `bg_color` is painted by the engine, never by
  the widget, so it never becomes sand.
- **Swap capture (constraint #1).** Re-derive `real` on every `frame_at`
  call and never cache it, as blinds and snow do.
- **The runner clears the canvas before every `frame_at`.** The transition
  must not clear it itself.
- **Snap.** At `t >= SNAP_THRESHOLD`, call `snap_reset(canvas,
  incoming_bg_color)`, then `incoming.draw(canvas, cursor_pos=0)`, the
  pattern every flair snapshot transition uses.
- **Scroll position.** The outgoing snapshot uses `outgoing_scroll_pos`, so
  scrolled text crumbles from where it stopped.

## Decided how

- **Name / registration:** `transition = "flair.sand"`, registered in
  `plugins/flair/src/led_ticker_flair/flair/__init__.py` next to
  `flair.snow`. New module `flair/sand.py`.
- **Timeline in transition progress `t`:**
  - Crumble runs over `[0, 0.5)`.
  - Pour runs over `[0.5, SNAP_THRESHOLD)`.
  - Snap at `t >= SNAP_THRESHOLD`.

  The two phases are sequential: the panel is briefly empty between them,
  as in the mockup.

  All motion is expressed in `t`, not seconds, so the whole effect scales
  with the configured duration.
- **`scale_switch_at = 0.5`** (the runner default). The crumble therefore
  happens over the outgoing `bg_color` and scale, and the pour over the
  incoming ones, and cross-scale sections pour in at their native scale. The
  incoming widget is snapshotted lazily, on the first frame with
  `t >= 0.5`, against the re-wrapped canvas. This matches how
  `flair.accordion` handles the scale switch.
- **Knobs:** `seed` only. With no seed (the default), each firing gets fresh
  randomness. With an int seed, firings are reproducible; tests and demo
  renders use this.
- **Duration:** this comes from the existing transition `duration` field
  (top-level `[transitions] duration`, a per-section `transition_duration`,
  or the inline-table `duration` key). The plugin cannot set its own
  default. The README and docs recommend `duration = 3`. *(My call: adding a
  plugin-side default duration would be new core machinery.)*

## Settled after the builder check

The approved mockup settled the first two of these. The rest are my calls.

- **Every real LED is its own grain.** Release time, drift and pour start
  are drawn per real pixel, not shared across a 4×4 logical block. The
  mockup works this way. Because release times are confined to the first
  ~35% of the crumble, the word still reads as one word coming apart.
- **The pour uses gravity.** Each grain is released at rest from about 4 px
  above the top edge and accelerates down. Its fall time is
  `sqrt(2·dist/g)`, where `dist` is the distance to its target row. It
  stops dead on arrival. Choose `g` and clamp start times so that the
  longest fall (the bottom row, with maximum jitter) lands by
  `SNAP_THRESHOLD`.
- **No new dependencies, and numpy in particular.** Every grain costs one
  `SetPixel` per frame no matter how its position is computed, so numpy
  would not help much. Precompute per-grain constants once per firing and
  keep the per-frame loop to arithmetic plus `SetPixel`. Measure a fully lit
  bigsign frame with a render. If it overruns the tick, tell James before
  cutting corners. Never reduce the grain count silently.
- **Drift is set as total travel.** Define it as total horizontal travel
  over the crumble phase, as a small fraction of panel width (≤ ~2%),
  rather than per-frame units.
- **Easing.** The phases are defined on the `t` the runner passes, so a
  non-linear `easing` simply reshapes them. Nothing special is done and
  nothing is documented for it.
- **Smaller defaults.** `min_frames = 30`. Overlapping grains are
  last-write-wins. `seed` is validated the way snow validates it.

## Left to the builder

These are my calls unless James objects:

- **Crumble release times.** Each grain's release time is uniform over
  roughly the first 35% of the crumble phase, as in the mockup.
- **Sideways drift.** Each grain gets a small horizontal velocity of about
  ±0.15 px per mockup frame at 256 wide, scaled to panel width.
- **Gravity** is chosen from panel height and the phase length, so that a
  grain released last from the top row is off the panel by the end of the
  crumble. The effect then reads the same on 16-tall and 64-tall panels.
- **Pour start times.** A grain's start time is `(h-1-y)/h · ~0.55` plus a
  uniform jitter of `~0.25` (fractions of the pour phase), clamped so every
  grain has landed by `SNAP_THRESHOLD`.
- **Drop height.** Grains start just above the top edge, about 4 real
  pixels, as in the mockup.
- **Rounding.** Positions round to integer pixels.
- **Clipping.** Off-panel grains are skipped, never clamped.
- **Data layout.** A per-firing "plan" holds the precomputed grain lists
  (for example `(x, y, r, g, b, release, vx)` and `(x, y, r, g, b,
  start)`). It is rebuilt when `t == 0.0` or `t` goes backwards. This is the
  blinds pattern.
- **Performance.** Check the Pi-5 frame budget for a fully lit bigsign
  frame, for example a twinkle background, which is about 16k grains on each
  side. If it is too slow, vectorise or precompute per-grain trajectories.
  Do not reduce the number of grains.

## Tests (minimum)

- `t = 0` paints exactly the outgoing snapshot. The snap at `t >= 0.95`
  paints exactly the incoming widget, with the bg colour honoured.
- Mid-crumble frames paint only outgoing colours, and some grains have moved
  below their source row. By `t` just under 0.5, no outgoing grain is left
  on the panel.
- Mid-pour frames paint only incoming colours. Every painted grain is at or
  above its target row, in its target column (straight drop). Just before
  the snap, every incoming lit pixel is at its target.
- With the same `seed`, frames are identical; with no seed, two firings
  differ.
- On a `ScaledCanvas`, grains are painted at physical resolution, a
  constraint #11 analogue.
- `outgoing_scroll_pos` is passed through to the outgoing snapshot.
- Registration: `flair.sand` resolves through the plugin API.

## Deliverables

- `flair/sand.py`, its registration, and tests in the flair package.
- A flair README entry with a TOML example using `duration = 3`.
- Release notes for the next flair minor.
- A follow-up in the core repo: a docs-site catalogue entry plus a demo gif,
  following the snow/laser pattern.
