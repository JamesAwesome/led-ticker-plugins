# flair.accordion transition — design

Status: draft for James's approval (brainstormed 2026-11-03).

## Intent

A transition that looks like a dealer working a deck of cards on felt. The
outgoing content bunches up into a squared-up deck and slides off one edge.
The incoming content arrives as a deck from the opposite edge and fans out
into place. The spreading happens WHILE the deck moves, tied to the panel's
width, never as a separate "arrive, then expand" step. James rejected the
first mockup ("less come in then expand, more expand as it moves").

## Goals

- Two motions, both shipped (James: "lets do both"):
  - **`sweep`** (dealer's sweep): an invisible hand crosses the whole
    panel. Outgoing: the hand enters from the far edge and scoops up each
    card as it reaches it, pushing a growing stack off the exit edge.
    Incoming: the hand enters from the far edge carrying the full stack
    and lays down each card in its slot as it passes, so the fan trails
    out behind it.
  - **`stretch`** (stretching accordion): the content moves as one piece,
    and its spacing is a function of how far it has travelled. Outgoing
    squeezes shut as it slides out and is fully stacked as it leaves.
    Incoming enters fully stacked and opens up continuously, reaching
    normal spacing exactly as it lands.
- **Card-fan stack look** (James's pick over "full pile" and "half
  overlap"): every card is opaque and hides the cards under it. A stacked
  deck shows only a thin edge of each buried card, like a squared-up deck
  seen from above.
- It works with any widget: plain text, emoji, hi-res text on the bigsign,
  images, bordered widgets (the border stays put) and two-row widgets (one
  deck per row).

## Non-goals

- No per-letter knowledge of the widget. Cards come from rendered pixels,
  not from the widget's text.
- No vertical (up/down) variants.
- No `alternating` / `random` wrappers in v1 (see Knobs).
- No new core seams. No core release. The flair core floor stays where it is.

## Anti-goals (a failure even if it technically works)

- An "arrive, then expand" pause. The spread must be coupled to travel the
  whole way.
- Stacked letters smearing into an unreadable blob of OR'd strokes. That
  was the rejected "full pile" look. Cards must occlude.
- Visible jumps. A card must never teleport between frames when it joins or
  leaves the stack (see the continuity rule under Motion math).
- Panel freezes or stalls: the same rules as every flair transition
  (paint-only, bounded per-frame work, no exception escapes `frame_at`).

## What a "card" is (my call, James agreed)

The snapshot of a widget is split into cards along **blank real-pixel
columns**. A card is a maximal run of columns that each contain at least
one lit pixel. The blank columns between runs are gaps and belong to no
card.

- Text: roughly one card per letter. Spaces are gaps. Glyphs that touch
  with no blank column between them (some hi-res fonts, tight kerning)
  become one card. Accepted.
- Emoji: one card each (or merged with a touching letter, as above).
- A picture with no blank columns (a full-width gif or image) is **one
  card** and simply slides. James: "okay".
- Lit means the slot was set AND is not pure black. This is the laser
  rule, so gif letterboxing and pillarboxing are not cards. The section
  `bg_color` never enters a snapshot because the runner paints it, not
  the widget.

Each card records its natural left column `slot_i` (REAL px), its width
`w_i`, and its lit pixels relative to its left edge, as
`(dx, y, (r, g, b))`.

### Borders stay put (James: option a)

When the widget has a `border` (duck-typed: `getattr(widget, "border",
None)` is not None), the border ring does NOT become part of any card.

- **Ring depth.** The ring is the outer `d` real px on every side, where
  `d = border.thickness` for the core ring borders (`RainbowChaseBorder`,
  `ColorCycleBorder`, `ConstantBorder`, `ColorBandsBorder`). The builder
  must confirm the right depth for `LightbulbBorder`, whose bulb size is
  not a `thickness`, and fall back to measuring it from the snapshot if no
  attribute exists. Unknown border shapes are a builder call, documented
  in the plugin CLAUDE.md.
- **Card scan.** Cards are segmented only from the inset region inside the
  ring.
- **Painting the ring.** The ring pixels are painted static, at their
  snapshot colours, every frame of that widget's phase: the outgoing ring
  during the outgoing phase and the incoming ring during the incoming
  phase. The ring is painted AFTER the cards, so cards travelling to and
  from the panel edge pass under the frame.
- **Animation.** The ring is frozen at its snapshot frame. Transitions
  pause effect counters anyway.

Full-panel `background` effects (e.g. `flair.fireworks`) cannot be
separated from content. A widget with a background effect degrades to one
card that slides. Accepted. Document it in the README.

### Two-row content gets one deck per row (James: option a)

When the widget is two-row, each row is its own deck. Two-row is
duck-typed as a `two_row` widget, or an image or gif with a non-empty
`bottom_text`; the builder picks the exact predicate, using only public
attributes.

- **Band boundary.** The boundary comes from the widget's band heights:
  `resolve_band_heights(content_height, top_row_height)`, which is on the
  public plugin surface, converted to real rows through `scale` and the
  wrapper's vertical offset.
- **Segmentation.** Cards are segmented per band, and occlusion is per
  band (a per-band owner array).
- **Motion.** Both decks use the same anchor and spread progression, so
  they move in sync. Each deck uses its own slots and peek.

Single-row widgets have one band covering the whole height.

### Too many or too narrow cards: adaptive peek (my call)

Dense text and sparse pixel-art can yield cards spaced closer than `P`.
Then a stacked deck would be WIDER than the fanned content, so stretch
would grow while "squeezing" and sweep would race.

- **Effective peek, per deck:** `P_eff = min(P, (slot_{n−1} − slot_0) / (n − 1))`,
  with `P_eff = P` when `n ≤ 1`. The stacked deck is then never wider than
  the fanned one.
- **No card cap and no merging.** Cards smaller than one real column are
  impossible by construction.

## Stack geometry

- **Peek** (the visible edge of each buried card) = `2 × scale` real px:
  2 px on the smallsign, 8 px on the bigsign at scale 4. This is my call
  and a tuning surface at the visual gate.
- With direction `left` (the default), card `i+1` sits on top of card `i`.
  The topmost card is the one nearest the far (entry) edge, and each
  buried card shows its exit-side edge. Direction `right` mirrors this.
- **Occlusion without a fill colour.** For each real column, only the
  topmost card covering that column is painted. Columns a card covers but
  where its own pixels are unlit show whatever the runner painted, which is
  the section bg. This gives exact card-fan occlusion with no knowledge of
  the bg colour. That matters because `frame_at` receives
  `incoming_bg_color` but not `outgoing_bg_color`. Do NOT add a core seam
  for it.

## Motion math (direction `left`; `right` is the horizontal mirror)

Panel width `W` (real px). `n` cards, indexed in natural left-to-right
order, with `P` = peek. Positions are each card's left column in real px.

**Continuity rule:** every card's position is a continuous function of
phase progress. Joining or leaving the stack never jumps.

### sweep

`P` below means the deck's `P_eff`.

- **Outgoing:** `pos_i = min(slot_i, g + i·P)`. Cards to the left of the
  hand stay in their slots, and the rightmost card is picked up first.
  - `g` starts at `max(W − (n−1)·P, max_i(slot_i − i·P))`. The hand starts
    at the panel's right edge, and the `max` guarantees t=0 equals the
    snapshot even for content scrolled hard against the right edge.
  - `g` ends at `−max_i(i·P + w_i) − 1`, so the whole stack is past the
    left edge.
- **Incoming:** `pos_i = max(slot_i, h + i·P)`. A card rides with the
  stack until its stacked position reaches its slot, then stays. That is
  a dealer's spread: the rightmost cards land first, and card 0 lands
  last.
  - `h` starts at `W`, with the stack just off the right edge.
  - `h` ends at `min_i(slot_i − i·P)`, so EVERY card is in its slot by the
    end of the phase. No card jumps at the 0.95 snap.

### stretch

- **Outgoing:** `pos_i = a + lerp(i·P, slot_i − slot_0, s)`. The anchor `a`
  moves from `slot_0` to fully off the left edge, and the spread `s` goes
  from 1 to 0 along with it. `s` reaches 0 at or just before the stack
  clears the panel, so the stack leaves fully squared.
- **Incoming:** the same formula, with `a` moving from `W` to `slot_0` and
  `s` going from 0 to 1 over the same progress. Both reach their endpoints
  together, so it lands exactly at full spacing.

### Timeline

- `t ∈ [0, 0.475)`: outgoing phase (local progress `k = t / 0.475`).
- `t ∈ [0.475, 0.5)`: the panel shows bg only, a brief beat between decks.
- `t ∈ [0.5, 0.95)`: incoming phase (`k = (t − 0.5) / 0.45`).
- `t ≥ SNAP_THRESHOLD` (0.95): `snap_reset(canvas, incoming_bg_color)`,
  then a live `incoming.draw(canvas, cursor_pos=0)`, as in laser.
- **No internal easing (my call).** `run_transition` already hands
  `frame_at` an eased `t` (`t = ease_fn(i / frame_count)`), so a second
  ease inside the plugin would double-apply. Local `k` is linear in the
  `t` received, and the feel comes from the runner's `easing`.
  - The docs recommend `easing = "ease_in_out"` for this transition,
    which matches the mockups' feel.
  - Because the phase boundaries sit in eased-`t` space, the 0.475–0.5
    beat may collapse to zero frames under some easings. That is accepted.
- An empty outgoing snapshot (zero cards) gives a blank outgoing phase.
  An empty incoming snapshot gives a blank incoming phase until the snap.

## Snapshots, scale, bg, cross-scale

- Snapshot each widget once per firing into a readable plugin-local raster
  sized to the REAL canvas. Wrap it in `ScaledCanvas(raster, scale=…,
  content_height=…)` when `is_scaled(canvas)` so hi-res widgets paint
  exactly as they do on the panel. Use laser's `_Raster` (SetPixel, SubFill,
  Clear, Fill, **SetImage**, get). The builder may lift it into a shared
  private module (`flair/_raster.py`) and point laser at it. That is a
  refactor only, and laser's tests must stay green.
- Never draw the outgoing widget live after its snapshot (laser's drift
  invariant).
- Draw the outgoing snapshot with `cursor_pos=kwargs.get("outgoing_scroll_pos", 0)`.
- Draw the incoming snapshot LAZILY, on the first frame with `t ≥ 0.5`,
  using the live canvas. Keep the runner's default `scale_switch_at`
  (0.5). The runner then re-wraps at the incoming scale at 0.5 and paints
  outgoing bg before 0.5 and incoming bg after, so a cross-scale section
  change gets its native size for the whole incoming phase, and bg needs no
  handling in the plugin. (Unlike laser, which pins 1.0.)
- Refire detection: `t < self._last_t` invalidates both snapshots and the
  card lists. Re-allocate rasters only when the geometry key (real w, h,
  scale, content_height) changes.
- Re-derive `real` from the live canvas on every call and never cache it
  (constraint #1).

## Perf contract

- Per frame: at most one painted pixel per real panel pixel, because
  column-topmost occlusion paints each column from exactly one card. Build
  the column→top-card map in O(n + W) per frame: a sweep over cards in
  stacking order that writes a `W`-length owner array.
- Card segmentation and lit extraction run once per snapshot (one raster
  pass).
- Same `TestPerfUniformity` tripwire shape as laser, fairy and lightning:
  per-frame SetPixel ≤ 1.5 × panel px on bigsign dims, first firing and
  refire.

## Knobs

- `direction`: `"left"` (default: exits left, enters from the right) or
  `"right"` (the mirror). My call. James didn't ask for direction variants,
  and a knob is cheaper than four more type strings.
- `min_frames`: floor so the global 0.5 s default isn't a blur. Start at
  **30**, which is 1.5 s at the default 50 ms tick; section-entry
  transitions with `entry_fps` set run at their own cadence. Recommend
  `duration = 2.0` in docs. My call, tuned at the visual gate.
- No `peek` knob in v1. Add one only if the visual gate shows sign owners
  will want it.
- Nothing else beyond the runner's `duration` / `easing`.

## Registration

In `plugins/flair/src/led_ticker_flair/flair/accordion.py`:

- An `_Accordion` base holding the snapshot, card and occlusion logic.
- `AccordionSweep` and `AccordionStretch`, which differ only in the
  position functions.
- `register(api)` adds `api.transition("accordion.sweep")(AccordionSweep)`
  and `api.transition("accordion.stretch")(AccordionStretch)`.

Config: `transition = "flair.accordion.sweep"` or
`transition = {type = "flair.accordion.stretch", direction = "right"}`.

Imports come only from `led_ticker.plugin`. `test_import_purity` covers
that.

## Tests (`plugins/flair/tests/test_flair_accordion_plan.py` + `_transition.py`)

- **Segmentation:** blank-column splitting on a synthetic raster. Touching
  glyphs merge. A full-width image is one card. Black and unset pixels are
  unlit. An empty raster gives zero cards.
- **Continuity:** for both motions and both directions, no card's position
  changes by more than the per-frame travel bound between adjacent sampled
  `t` values (catches pickup and drop jumps).
- **Endpoints:**
  - At t=0, every card is in its slot. This is pixel-identical to the
    snapshot.
  - At the end of the outgoing phase, no outgoing pixel is on the panel.
  - At the start of the incoming phase, no incoming pixel is on the panel.
  - At t ≥ 0.95, `snap_reset` is called with `incoming_bg_color` and the
    incoming widget is drawn live.
- **stretch lands at full spacing:** at incoming `k = 1`, positions equal
  the slots.
- **sweep lands right-to-left:** under `direction="left"` with spacing
  ≥ P, card `n−1` lands before card 0.
- **Dense content:**
  - A deck whose cards are spaced < P uses `P_eff`, and the stacked width
    is ≤ the fanned width.
  - Content scrolled against the right edge is snapshot-identical at t=0.
  - Every card is in its slot at the end of the incoming phase (no snap
    jump).
- **Border:**
  - A bordered widget's ring pixels are in no card and are painted static,
    after the cards, during that widget's phase.
  - The inset content is split into multiple cards.
  - Each core border class's ring depth is honoured.
- **Two-row:**
  - Cards are segmented per band.
  - No card spans the band boundary.
  - Both decks reach stacked or landed at the same `t`.
- **Occlusion:** two overlapping cards paint only the top card in their
  shared columns, and the buried card's peek columns show its own pixels.
  Columns with no lit top-card pixel issue no SetPixel, so the bg shows
  through.
- **Direction mirror:** `right` is the horizontal mirror of `left` on a
  symmetric fixture.
- **Scaled canvas:**
  - Through `ScaledCanvas` at scale 4, cards are found at real-pixel grain.
  - Peek is 8 real px.
  - A hi-res-painting widget snapshots correctly.
- **SetImage widget:** snapshots, becomes one card, and slides.
- **Lazy incoming snapshot:** the incoming widget is not drawn before
  t=0.5. A cross-scale fixture snapshots incoming at the re-wrapped scale.
- **Refire:** re-snapshots changed content. Equal `t` is not a refire.
  The outgoing widget is never drawn live after its snapshot (drift probe).
- **Registration:** both types are present as distinct instances, and a
  bad `direction` raises `ValueError` at construction.
- **Perf uniformity tripwires.**

## Performance verification (mandatory, lightning-convention gates)

1. Frame-time sweep on bigsign dims (256×64, scale 4), fresh instance and
   refire, for a text case and a full-panel-image case. Worst frame ≤ 5 ×
   average, with no phase-boundary outlier, including the lazy incoming
   snapshot frame at t=0.5. Put the numbers in the PR body.
2. Fresh-process construction (~0) and first-ever frame (ms-class).
3. The committed `TestPerfUniformity` tripwires.

## Visual gate (HARD STOP for James before the PR)

Bigsign and smallsign GIFs of both motions in both directions, plus:

- one section with a `bg_color`
- one cross-scale section change
- one image widget
- one empty-outgoing entry
- one bordered message (rainbow and lightbulb)
- one `two_row` widget

Expected tuning surface:

- peek width
- phase split and ease curve
- `min_frames` and the recommended `duration`
- whether the beat between decks (0.475–0.5) should exist at all

## Deliverables

- `accordion.py`, registration, and tests (plus the optional `_raster.py`
  lift).
- Bigsign smoke config `plugins/flair/examples/config.accordion-smoke.bigsign.toml`.
- flair `README.md` entry, a flair `CLAUDE.md` invariants section
  (occlusion-by-column, continuity rule, lazy incoming snapshot), and a
  committed demo GIF.
- Docs-site entry in the core repo on `transitions/sprite.mdx`
  ("Text-effect transitions") with a pinned demo at
  `docs/site/demos-pinned/transition-flair-accordion.toml` (rendered to
  `public/demos-pinned/transition-flair-accordion.gif`), following the
  laser entry.
- Release after James gives the merge word: `cut_release.py flair minor`.

## Left to the builder

- Internal data layout of cards and the owner array.
- Whether `_Raster` is lifted to a shared module or imported from laser.
- Exact ease function, provided the mockup feel is preserved.
- How the stretch outgoing `s` curve is shaped so that it reaches 0 as the
  stack clears the edge.

## Reference

Brainstorm mockups (throwaway):
`<scratchpad>/.superpowers/brainstorm/56114-1793729565/content/motion-v2.html`.
Its `sweepIn`/`sweepOut` use the earlier, jumpy pickup rule. The
continuity rule above supersedes it.
