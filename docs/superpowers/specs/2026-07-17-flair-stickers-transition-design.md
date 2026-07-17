# flair.stickers — sticker-bomb transition — Design

**Date:** 2026-07-17
**Repos:** led-ticker-plugins (`plugins/flair`, the transition) + led-ticker core (one small seam)
**Status:** approved (brainstormed; James picked pop-off peel + full-assortment random)

## Concept

The screen gets sticker-bombed: emoji stickers pop on one at a time in random
order over the outgoing widget until the panel is fully covered at t=0.5, then
pop off one at a time in an independent random order, revealing the incoming
widget underneath. Flagship use: Taco Tuesday at the halal cart — a wall of
tacos swallows the gyro menu, then peels away.

## Decisions (user-approved 2026-07-17)

1. **Peel = pop-off in random order** (not fly-away, not sweep): stickers
   vanish one at a time, incoming showing through the holes.
2. **Random mode = full assortment**: with no `emoji` knob, each sticker
   independently picks a random slug — emoji-confetti chaos. A configured
   list restricts the pool (one slug = themed wall).
3. **Die-cut sticker look** (design call, approved with the design): each
   sprite renders over a 1px-dilated white outline with black fill behind
   the silhouette — reads as stickers on glass and makes coverage literal.
4. **Only real slugs, validated at config-load** (James: ":fire: is not in
   our set"): unknown slugs raise at config-load, so `led-ticker validate`
   catches the typo before the sign goes up.

## Config surface

```toml
transition = {style = "flair.stickers", emoji = ["taco"]}            # all-taco wall
transition = {style = "flair.stickers", emoji = ["sun", "moon"]}     # mixed set
transition = "flair.stickers"                                        # random assortment
```

Same inline-table knob pattern as `flair.fireworks`' `colors`. `emoji` is a
list of slug strings WITHOUT colons (matching the lottery `words` style of
plain strings; docs show the mapping to `:slug:` text usage). Validation:
every entry must be a known slug at config-load — the checked set is the
union of core + plugin-registered emoji at that moment (so `pokeball.ball`
is legal when the pokeball plugin is installed).

**The real core set (45 slugs, for docs/examples — never invent one):**
`taco`, `sun`, `moon`, `flower`, `droplet`, `bunny`, `instagram`, `email`,
`cloud`, `partly_cloudy`, `rain`, `snow`, `thunder`, `fog`,
`star` + `star_{blue,green,orange,pink,purple,red,yellow}`,
`heart` + `heart_{blue,green,orange,pink,purple,red,yellow}`,
`cat` + `cat_{black,brown,cream,gray,orange,white}`,
`pride` + `pride_{ace,bi,demi,lesbian,nb,rainbow,trans}`.
Both registries are parallel today (every slug has low-res AND hi-res), but
the transition still guards per-form lookups for plugin emoji that register
only one form.

## Choreography

Fireworks two-phase template (pure plan module + transition class):

- **Build (t 0 → 0.5):** outgoing widget draws every frame (frame-paused by
  `run_transition`, standard); stickers appear cumulatively in a seeded
  random order with `ease_in_out` pacing (slow first stickers, an
  accelerating pile-on). At t=0.5 every sticker is present and the panel is
  fully covered.
- **Peel (t 0.5 → 1.0):** incoming widget draws every frame; stickers
  disappear cumulatively in an INDEPENDENT seeded random order (not the
  reverse of arrival — reverse reads as a rewind).
- **Snap:** at `SNAP_THRESHOLD` (0.95) the frame is `snap_reset(canvas,
  incoming_bg_color)` + incoming only — the standard no-border-flash
  contract every flair transition honors. The 0.5 cut-over aligns with
  `run_transition`'s `incoming_scale` / bg cut-over conventions.
- **Determinism:** one RNG seeded per RUN (construction time), consumed by
  placement, slug choice, tilt, arrival order, and departure order. Two runs
  differ; frames within a run are pure functions of t (re-render safe).

## Placement & coverage guarantee

Random scatter cannot guarantee coverage, so stickers sit on a **jittered
grid sized so footprints overlap** — coverage at t=0.5 holds by
construction (the fireworks lockstep-bloom lesson, applied structurally):

- Cell size = sticker footprint × ~0.8 (overlap factor); jitter each
  sticker ±25% of cell within its cell; tilt ±15°.
- Bigsign (256×64 real): 32×32 hi-res sprites (with backing ≥ 34px
  footprint) → grid ≈ 10×3 ≈ 30 stickers.
- Smallsign (160×16): 8×8 low-res sprites → grid ≈ 24×2 ≈ 48 stickers.
- The die-cut backing (black fill behind the silhouette + white outline) is
  what makes cells opaque; the coverage test asserts the union of BACKING
  footprints covers the panel, not sprite ink.

**Tilt is pre-rasterized once per run**: each sticker's rotated pixel list
(sprite + backing) is computed at plan time and blitted as plain SetPixels
per frame. Rotating ~30 sprites via `rotate_blit` every frame would blow
the 50ms tick budget; caching makes tilt near-free. (Perf gate in testing.)

## Scale handling

Dispatch on `is_scaled(canvas)` like every flair paint site: bigsign paints
hi-res sprites to `unwrap_to_real(canvas)`; smallsign uses the 8×8 sprites
at logical resolution. A slug present in only one registry falls back to the
other form (mirroring `draw_emoji_at`'s dispatch), scaled to the footprint.

## Core seam (small core PR, released first)

Plugins cannot enumerate the emoji registry today. Core adds:

```python
def emoji_slugs() -> tuple[str, ...]:
    """Sorted slugs currently drawable inline (core + plugin-registered)."""
```

exported via `led_ticker.plugin.__all__` + the api-reference drift region.
Random mode and knob validation both consume it. Flair floors
`led-ticker-core >= <that release>`. Rejected alternative: a curated slug
list hardcoded in flair — violates the ecosystem's "never inline a static
slug list (it rots)" rule.

## Testing

- **Pure plan module** (`stickers.py` math, no canvas): coverage-union test
  (backing footprints cover panel at t=0.5, both sign geometries); arrival
  and departure orders are permutations and mutually independent; unknown
  slug raises with the slug named; determinism (same seed → same plan).
- **Transition class:** t=0 outgoing-only / t=1 incoming-only; snap frame
  respects `incoming_bg_color`; stub-canvas pixel assertions that stickers
  actually paint; no `create_canvas` calls (recycling contract).
- **Perf gate:** frame paint under budget with 30 pre-rasterized stickers
  (assert no per-frame rotation calls — AST or spy).
- **Core seam:** `emoji_slugs()` returns the 45 core slugs sorted; includes
  plugin-registered slugs after a test registration; api-reference drift
  test row.
- **GIF validation before merge** (render-path change): taco wall on
  bigsign geometry + random assortment + smallsign geometry, checked
  against docs/visual-validation.md.

## Rollout

1. Core PR: `emoji_slugs()` seam (+ docs row) → core release vNext (via
   `scripts/cut_release.py`).
2. Flair PR: `stickers.py` + transition registration + tests + README/docs
   catalog entry; floors core to the seam release → `flair-vNext`.
3. Halal-cart config PR (core repo): Taco Tuesday sections adopt
   `transition = {style = "flair.stickers", emoji = ["taco"]}` as the
   showcase (banner entry or between-section override — decided at
   implementation by what reads best in the GIF).

## Out of scope

- Fly-away/sweep peel variants (could be a `peel = "pop"` knob later if a
  second style ever ships — YAGNI now).
- Sticker persistence (stickers that stay during the hold) — different
  feature (border/overlay territory).
- Weighted random or per-sticker size variety.
