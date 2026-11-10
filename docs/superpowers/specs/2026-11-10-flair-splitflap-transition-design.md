# flair.splitflap transition — design

**Date:** 2026-11-10
**Status:** approved in chat by James ("sounds awesome, get to building")
**Issue:** JamesAwesome/led-ticker-plugins#139
**Inspiration:** the Solari split-flap departure board.

## Intent

A whole-message transition that changes the outgoing message into the
incoming one the way an airport/rail departure board does: every character
is a flap hinged across its middle; it clatters through a few in-between
characters and lands on the new one, with a ripple so characters settle one
after another. It is meant to be **watched** — a slow, deliberate clatter
(~3 s), not a snap.

## Decided by James

- **Whole message to start.** Not a per-digit clock/score updater (that
  would be a different feature: only changed characters flip, in a live
  widget).
- **Cycle through a few in-between characters**, not a single old→new flap.
- **In place (mockup option A).** The message's own characters flip where
  they sit, in the widget's own font, size and colour, on the normal panel
  background. **No tiles, no board grid, no hinge line.**
- **Slow clatter, ~3 seconds** for a full message change.

## Accepted recommendations (proposed by Claude, accepted by James)

- **Works between any widgets, best on text.**
  - Text: one flap per character.
  - Gif / image / icon / background-effect content: no characters to find,
    so it is cut into character-width vertical **strips** that flip the
    same way. Never blank, never an error.
  - Two-row widgets: each row flips separately on its own hinge.
  - Mismatched lengths: extra positions flip from blank / to blank.
- **In-between characters are borrowed from the two messages** (cells cut
  from the snapshots), so they automatically match font, size and colour
  and the plugin needs no access to widget text. They are a shuffle of
  on-screen characters, not an A-B-C alphabet run. James confirmed this is
  fine.

## Claude's calls (stated to James, not objected to)

- **Variants** (flair convention, ripple direction):
  - `flair.splitflap.forward` — ripple left → right.
  - `flair.splitflap.reverse` — right → left.
  - `flair.splitflap.alternating` — forward, reverse, forward… one per firing.
  - `flair.splitflap.random` — characters settle in a random order (fresh
    order each firing). Note: unlike laser/interlock `.random`, this
    randomises the *settle order*, not the variant; James accepted that
    description.
- **Knobs:** `flips` (in-between characters per position, default 3) and
  `stagger` (how spread out the ripple is). Both on every variant.
- **Shading:** the moving flap is slightly darkened so it reads as a flap,
  not a glitch.
- **Both signs.** Built for bigsign and smallsign; the visual-gate GIFs
  decide whether the 16-row smallsign result is good enough to recommend.

## Goals

- The classic split-flap read on the bigsign (256×64, scale 4) for text,
  with a graceful, still-recognisable result for every other widget type
  the snapshot transitions handle (two_row, gif/image/still, bordered,
  background effects, bg-coloured sections, letterboxed sections).
- Same structure and conventions as the other flair snapshot transitions
  (interlock, blinds, laser): snapshot once per firing, pure function of
  `t`, `SNAP_THRESHOLD` snap to the real incoming draw.
- No new core seams; core floor unchanged (>= 4.32).

## Non-goals

- Live per-character updates inside a widget (clock/score/countdown digits).
- Real alphabet cycling (needs widget text + font; explicitly traded away).
- Tiles, board grid, hinge line, sound.
- Matching characters across different fonts or scales "correctly" — cells
  are pixel snapshots.

## Anti-goals (a failure even if it technically works)

- Reads as a vertical wipe or a flicker rather than flaps falling over a
  hinge.
- Reads as a fast snap. Default pacing must feel deliberate at 3 s.
- Any blank panel mid-transition, or a "border on black" flash at the snap.
- The border ring flipping with the text (it stays put, as in accordion).

---

## Behaviour

### Snapshots and cells

- Snapshot **both** widgets once per firing (outgoing at
  `outgoing_scroll_pos`, incoming at 0). Both are on screen together, so
  `scale_switch_at = 1.0` (blinds/laser convention): the runner keeps the
  outgoing bg + scale until the snap. Accepted limitations, same as blinds
  and laser: a cross-scale incoming renders at the outgoing scale until the
  snap, and a bg-colour change lands at the snap.
- Cut each snapshot into **bands and cells** with accordion's existing
  segmentation (`accordion_cards.build_decks`): one band per row (two_row →
  two bands), cells = maximal runs of lit columns, the border ring
  separated out and held static. Image widgets and background-effect
  widgets come back as one band of large cards.
- **Strips:** any cell wider than twice the typical character width is cut
  into equal strips of about that width. Typical width = median width of
  the "character-like" cells (no wider than the band is tall) across both
  snapshots in that band; with none, fall back to half the band height.
- **Hinge:** per band, the vertical middle of the lit rows of that band
  across both snapshots (so it splits glyphs at their visual middle, not at
  the band's nominal middle).

### Pairing

- **Band correspondence (Claude's call, from the builder check).** Bands
  pair by index, top to bottom. When the counts differ (two_row ↔ message,
  two_row ↔ gif/image, two_row ↔ background-effect widget), the one-band
  side pairs with the TOP band and the other side's extra band pairs with
  an empty band, so its cells flip from / to blank. Each band pair gets one
  hinge: the vertical middle of the union of both sides' lit rows in that
  pair; the strip width and the in-between pool are likewise per band
  pair. (Rejected: one panel-wide band, which cuts two_row glyphs at the
  panel middle; splitting a single row's cells across both bands.)
- Within a band pair, pair outgoing cell *i* with incoming cell *i* in
  left-to-right order. Extra cells pair with an empty cell (blank).
- A pair whose two cells are pixel-identical at the same position does not
  flip (real boards don't flip unchanged characters) but still holds its
  slot in the ripple.
- Each half is drawn at its **own** cell's home x (old halves at the old
  position, new halves at the new). In-between characters are drawn
  centred on the incoming cell's centre (outgoing cell's when the incoming
  side is blank). Motion is purely vertical.

### In-between characters

- For each flipping pair, pick `flips` cells from the pool of that band's
  cells across both snapshots, excluding the pair's own two cells and never
  the same cell twice in a row. An instance RNG (seedable in tests), drawn
  fresh each firing. A pool too small to pick from → fewer in-between
  flips for that pair (down to a direct old → new flap).

### One flap

A flap from glyph A to glyph B at local progress `p` in [0, 1], about the
hinge row:

- **p < 0.5:** above the hinge shows B's top half; below shows A's bottom
  half; the falling flap is A's top half squashed toward the hinge to
  `(1 − 2p)` of its height (nearest-row sampling), darkened.
- **p ≥ 0.5:** above shows B's top; the flap is B's bottom half unfolding
  down from the hinge to `(2p − 1)` of its height over A's bottom half
  (rows the flap covers are blanked to bg first), darkened.
- Darkening: scale the flap's RGB by roughly 0.6–0.85 (builder tunes at the
  visual gate). Every output pixel is clamped to the panel and painted at
  physical resolution (real canvas), like interlock/blinds.

### Timeline

- The animated part runs over `p = t / SNAP_THRESHOLD`; at
  `t >= SNAP_THRESHOLD` snap (`snap_reset` + real incoming draw), exactly
  like blinds.
- Each pair does `flips + 1` flaps of equal length `f`. Pairs start in
  ripple order; `stagger` is the fraction of the timeline spent rippling,
  so with `n` ranked positions: `start_k = k · stagger / max(n − 1, 1)`,
  `f = (1 − stagger) / (flips + 1)`. Every pair has landed at `p = 1`.
- Ripple rank: by the pair's x (incoming cell, else outgoing) across
  ALL bands together — a two-row widget's columns ripple together.
  `.reverse` reverses the rank; `.random` shuffles it per firing.
- The static border ring (outgoing's, switching to the incoming's at
  `p = 0.5`) is painted after the cells, with accordion's `under` handling.

### Knobs and validation

- `flips`: int, `>= 0`, default `3`. `0` = single old → new flap.
- `stagger`: float in `[0.0, 0.9]`, default `0.5`. bool rejected for both,
  same `ValueError` style as `strand` / `slats`.
- `min_frames`: enough that a default flap gets ~4 frames (≈ 36). README
  recommends `duration = 3.0`.

## Edge cases

- Empty outgoing (boot / wake): every pair flips from blank.
- Both empty: nothing paints until the snap.
- Identical outgoing and incoming: no pair flips; looks like a hold, then
  the snap.
- Letterboxed sections (`content_height × scale < panel`): cells come from
  lit pixels only, so letterbox bands stay bg; a border in the letterbox is
  the ring, held static.
- `.alternating` / `.random` refire rule: same `t == 0 or t < last_t` as
  `_variants`.

## Visual gate (before any PR)

Render bigsign (256×64 render-geometry copy) and smallsign GIFs of a
smoke config covering: text→text (different lengths), two_row, gif in and
out, bordered message, bg-coloured sections, letterbox, each variant, and
a `flips = 0` / `stagger` knob section. James decides on the smallsign.

## Left to the builder

- Module layout (expect `splitflap.py`, reusing `_snapshot`, `_raster`,
  `accordion_cards`, `_variants`), precomputation shape, exact shade factor
  and `min_frames` value, test structure.
