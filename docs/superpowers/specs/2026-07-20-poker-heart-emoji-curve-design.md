# poker heart mask — adopt the emoji's implicit curve

**Date:** 2026-07-20
**Status:** approved (quick brainstorm with James; candidate B picked from a
rasterized A/B/C comparison at r=7/12/20 + spade renders)

## Problem

James (2026-07-19, watching poker on the sign): "the bottom of the heart looks
a bit pinched." The current `_in_heart` (two lobe circles + a LINEAR wedge
tapering to the point) narrows too fast — at every radius a 1–2 px spike
dangles below the body, worst on the resting glyphs (r=7) and large ripple
rings. The spike also inverts into a needle on spades (which reuse the heart
mask flipped).

## Decision

Replace `_in_heart`'s body with core's **hi-res `:heart:` emoji curve** — the
classic implicit heart with the EMOJI'S normalization (this is the load-bearing
part: the curve was tried in July and read as a SHIELD, but that was a
different normalization; with the emoji's `scale = diameter/2.6` and `+0.25`
vertical bias it renders proper rounded lobes and a short clean tip at every
LED size, r=7 included — verified in the rasterized comparison James approved).

New mask (poker.py, replacing the lobes+wedge body of `_in_heart`):

```python
def _in_heart(x, y, r):
    # Core's hi-res :heart: emoji curve (pixel_emoji._generate_heart_hires):
    # classic implicit heart with the EMOJI's normalization — scale spans
    # 2.6 curve-units across the 2r-px box, +0.25 vertical bias. The July
    # "shield" reading came from a different normalization, not the curve;
    # adopted 2026-07-20 to fix the pinched bottom (spec
    # 2026-07-20-poker-heart-emoji-curve-design.md).
    if r <= 0:
        return False
    s = (2 * r) / 2.6
    nx = x / s
    ny = -y / s + 0.25
    return (nx * nx + ny * ny - 1) ** 3 - nx * nx * ny * ny * ny < 0
```

`_in_spade` is UNCHANGED (still `_in_heart(x, -y * 0.95, r * 0.92)` + stem) —
it inherits the fix; the comparison showed it produces the cleanest spade of
the three candidates.

## Bounds & invariants

- **Fits the rasterizer's scan box** (`interior_pixels` scans ±(ceil(r)+1)):
  curve extents ≈ nx ±1.14, ny ∈ [−1, 1.2] → pixels x ≈ ±0.88r,
  y ∈ [−0.73r, 0.96r]. All within ±r.
- **Scale-homogeneous** (mask depends only on x/r, y/r), same as the old
  mask — ring shells and the reveal union behave identically in kind.
- **Top notch persists at all radii** (scale-invariant), exactly like the old
  mask's notch — no new coverage class. The full-reveal guarantee still rests
  on `_MAX_R_FACTOR = 1.45` + neighboring glyphs; the existing seed-matrix
  tests re-verify it empirically against the new shape.
- **Perf:** two extra float products per mask eval; geometry is process-cached
  (flair 0.10.1's `_ring_geom`/`_interior_geom`), so shape cost is paid once
  per process. No cache-key changes.

## Verification

1. **Full test suite** — the full-reveal matrix (`_FULL_REVEAL_POOLS` ×
   geometries × seeds + the pinned clubs regression cases) must pass
   unchanged. `test_union_of_rings_covers_interior` (shapes file) re-verified
   against the new mask. Any shape-pinned assertions in
   `test_flair_poker_shapes.py` that encode the OLD silhouette get adapted
   with intent preserved (heart-ness properties: symmetry, notch at top,
   tip at bottom, no sub-2px-wide rows except the tip row class).
2. **Perf sweep (lightning-convention gate):** one frame-time sweep on
   bigsign dims (fresh + refire) to confirm no regression — ring pixel counts
   change slightly with the fuller shape.
3. **Visual gate:** re-render a hearts-only poker GIF (bigsign) for James
   before merge; check `:spades:`-pool GIF too. The glyph-level comparison is
   already approved; this confirms in-motion.

## Non-goals

- No change to diamonds/clubs, ring width, pulse timing, or knobs.
- No change to core's emoji sprites (poker borrows the curve; core is
  untouched).
- No version-floor change (pure shape fix → flair patch release).
