# flair.poker — card-suit ripple transition — Design

**Date:** 2026-07-17
**Repo:** led-ticker-plugins (`plugins/flair` only — no core seam needed)
**Status:** approved (brainstormed with a VISUAL GATE: three PIL prototype GIFs
rendered during design; James picked variant B and signed off on the
black-backdrop fidelity caveat below)

## Concept

Rainbow card suits (♥ ♦ ♣ ♠) pattern in over the outgoing widget, repeating
across the panel, then each suit emits **suit-shaped** rainbow ripple rings —
an expanding heart emits heart-shaped rings, a club club-shaped ones — and the
incoming widget is revealed inside the ripple wakes until the panel is fully
washed. Named for the table: `transition = "flair.poker"`.

## Decisions (user-approved 2026-07-17, visual-gated)

1. **Reveal = ripples wash it in** (not a midpoint cutover, not overlay+snap).
2. **Variant B: repeating pulses** — each glyph emits ~2.5 waves during the
   transition (picked over single-staggered-ripple variant A at the gate).
3. **Black-backdrop caveat, explicitly approved:** the prototype composited
   old content in unrevealed areas — the real engine cannot (no GetPixel,
   constraint #3; a transition can't per-pixel composite two widgets). The
   shipped second half shows the incoming widget inside the wakes **against
   black** with rings on top — the fireworks bloom pattern, proven on
   hardware. First half still paints over the live outgoing widget.
4. **Config:** `suits = [...]` list from `hearts` / `diamonds` / `clubs` /
   `spades`; omitted = all four cycling. Unknown suit names fail at
   config-load naming the valid options. `seed` knob (stickers convention).

```toml
transition = "flair.poker"                                   # all four suits
transition = {type = "flair.poker", suits = ["diamonds"]}    # just diamonds
transition = {type = "flair.poker", suits = ["clubs"]}       # just clubs
transition = {type = "flair.poker", suits = ["hearts", "spades"], seed = 7}
```

## Suit shapes are pure math masks

One `inside(suit, dx, dy, r) -> bool` family (offsets from glyph center,
radius r), used for BOTH the resting glyph and every ripple ring — that
identity is what makes suit-shaped rings possible at any radius:

- `diamond`: `|dx| + |dy| <= r`
- `heart`: classic implicit curve `((x² + y² − 1)³ − x²y³ <= 0)` on
  normalized, y-flipped coords
- `club`: three lobes (circles radius `0.45r` centered `0.5r` from center at
  90°/210°/330°) + stem (`|dx| <= 0.16r`, `0 <= dy <= r`)
- `spade`: flipped heart body (`heart(dx, −dy·0.95, 0.92r)`) + the same stem

A ripple RING at radius r with thickness w is `inside(r) AND NOT inside(r−w)`.
These live in the pure plan module exactly as the prototype validated them
(the gated prototype is committed at
`docs/superpowers/prototypes/2026-07-17-flair-poker-proto.py`; its shapes read
correctly at LED resolution in the gate GIFs — club and spade included).

## Choreography (tuned constants from the gated prototype)

- **Grid:** cell `GRID = 32` real px, jitter ±3px x / ±2px y → 8×2 glyphs on
  bigsign (256×64), 5×1 on smallsign (160×16). Suits assigned cycling
  through the configured pool; hue random per glyph; per-glyph stagger
  uniform in [0, 0.25] of transition-t.
- **Glyph intro (t 0 → ~0.2):** each glyph scales in to `GLYPH_R = 7` px,
  painted in its hue over the outgoing widget (which draws every frame,
  standard pause/guard semantics). Glyphs stay until their pulses start.
- **Pulses:** from each glyph's stagger point, `PULSES = 2.5` waves expand to
  `max_r = 1.2 × cell diagonal` (≈54px) — ring thickness `RING_W = 3.5` px,
  ring hue = glyph hue + 0.7×phase (cycles as it expands).
- **Cutover (~t = 0.45):** switch to incoming-against-black: incoming widget
  draws fully, the NOT-yet-revealed complement is blacked out, rings paint
  on top. The FINAL wave's interior is the permanent reveal; because
  `max_r` covers the cell diagonal ×1.2, neighboring wakes overlap and the
  union reaches every pixel — full reveal by construction (fireworks
  lockstep-bloom lesson).
- **Snap:** `SNAP_THRESHOLD` + `snap_reset(canvas, incoming_bg_color)` —
  the standard no-border-flash contract.
- **Determinism / re-fire:** stickers/fireworks idiom — explicit `seed`
  reproduces a firing; `seed=None` reseeds per re-fire (`_last_t`
  detection).

## Engine strategy (perf, the stickers + fireworks lessons combined)

- **Plan-time pre-rasterization only:** ring pixel-lists per (suit, integer
  radius, thickness) computed once per firing (bbox-scan of the mask
  functions), cached per-run; per-frame work is plain SetPixel iteration.
  Tripwire mirrors stickers' mutation-verified
  `test_no_rasterization_after_first_frame`.
- **Monotone reveal mask:** revealed pixels tracked in a per-firing
  `bytearray(W×H)`; each frame adds the final-wave ring DELTAS (interior at
  radius r ⊇ interior at r−1, so integer-radius ring lists ARE the deltas) —
  every panel pixel is added exactly once across the whole transition
  (amortized O(panel)).
- **Complement blackout:** per frame after cutover, scan the mask and
  SetPixel-black the unrevealed pixels — the count shrinks monotonically to
  zero (the fireworks complement idea; no per-row interval math needed
  because the mask scan is O(panel) with a shrinking paint set).
- Paints at PHYSICAL resolution via `unwrap_to_real` (fireworks precedent);
  works identically at scale 1.
- All core access via `led_ticker.plugin`: `SNAP_THRESHOLD`, `snap_reset`,
  `unwrap_to_real`, `is_scaled`. No new core surface.

## Testing

- **Shape functions (pure):** point-in/point-out fixtures per suit (center
  in, corners out, stem in for club/spade); ring = interior difference;
  radius monotonicity (`inside(r1) ⊆ inside(r2)` for r1 < r2 — required by
  the delta-mask design).
- **Plan:** determinism per seed; suit cycling respects the pool; stagger
  bounds.
- **Full-reveal guarantee:** seed sweep (≥25 seeds) × both geometries ×
  (all-suits, single-suit each) — at t just below SNAP, the revealed mask
  covers every pixel. If it fails, raise `max_r`'s factor; never weaken.
- **Transition class:** t=0 outgoing-only; snap respects `incoming_bg_color`;
  post-cutover frame = incoming + black complement + rings only (no
  outgoing paint after cutover); knob validation (bad suit named, valid
  accepted); no-rasterization-after-first-frame (spy, mutation-check it).
- **GIF gate on the real implementation before merge** (render-path change):
  all-suits + diamonds-only on bigsign, all-suits on smallsign — confirming
  the black-backdrop second half reads well (the approved caveat).

## Rollout

1. Flair PR: plan module + `Poker` class + registration + tests +
   README/CLAUDE.md + `plugins/flair/examples/config.poker-smoke.bigsign.toml`
   (smoke example committed per the stickers precedent) → GIF gate → merge →
   **flair-v0.10.0** via `cut_release.py flair minor`.
2. Core-side follow-ups ride the existing open items: docs-site transitions
   entry + catalog `provides` line (batch with the pending stickers docs-site
   entry), and any example-config adoption James asks for.

## Out of scope

- Card RANKS / full playing-card faces (this is suits only).
- Red/black traditional suit coloring (rainbow was the ask; a `colors` knob
  could come later via the standard transition_colors forwarding if wanted).
- Per-suit mixed sizing, variant A (single ripple) as a knob — YAGNI until
  asked.
