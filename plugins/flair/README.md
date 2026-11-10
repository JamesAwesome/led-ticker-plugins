# led-ticker-flair

Homage sprite-trail transitions and text animations for [led-ticker](https://github.com/JamesAwesome/led-ticker) — four sprite families plus text-effect transitions and animations, all in one wheel.

## Sprite-trail transitions

| Family | Type strings | Notes |
|---|---|---|
| nyancat | `nyancat.forward` / `nyancat.reverse` / `nyancat.alternating` | Hi-res sprite on bigsign |
| pokeball | `pokeball.forward` / `pokeball.reverse` / `pokeball.alternating` | Hi-res sprite + `:pokeball.ball:` emoji |
| pacman | `pacman.forward` / `pacman.reverse` / `pacman.alternating` | Low-res |
| sailor_moon | `sailor_moon.forward` / `sailor_moon.reverse` / `sailor_moon.alternating` | Low-res |

> **Unofficial fan homage.** These sprites are the property of their respective rights holders and are **not** covered by this project's license. Non-commercial homage only; no affiliation or endorsement. See the repo [NOTICE](https://github.com/JamesAwesome/led-ticker-plugins/blob/main/NOTICE.md).

## Propeller animation

`flair.propeller` spins a message widget's text in-plane on visit entry — a full-rotation ease-out that settles flat — then holds the text readable for the rest of the configured hold time. Transitions wait for the spin to finish before starting.

Requires **led-ticker-core >= 4.3**; with **core >= 4.5** the spin runs at
physical resolution on scaled displays (bigsign) — hi-res fonts and emoji
spin too.

### Config

Shorthand (all defaults):

```toml
[[playlist.section.widget]]
type = "message"
text = "Hello!"
animation = "flair.propeller"
```

Inline table with overrides:

```toml
[[playlist.section.widget]]
type = "message"
text = "Hello!"
animation = {style = "flair.propeller", revolutions = 3, spin_seconds = 1.5, direction = "ccw"}
```

### Knobs

| Field | Type | Default | Notes |
|---|---|---|---|
| `revolutions` | int ≥ 1 | `2` | Full rotations completed during the spin-in |
| `spin_seconds` | float > 0 | `1.0` | Wall-clock duration of the spin phase |
| `direction` | `"cw"` / `"ccw"` | `"cw"` | Clockwise or counter-clockwise |

### Caveats

- **Message widgets only.** `flair.propeller` works on `message` widgets (core rejects `animation` on other widget types at config load). GIF / image text-overlay widgets accept `animation` but ignore the rotation.
- **Hi-res fonts spin on scaled displays (core >= 4.5).** Mid-spin renders at half detail and sharpens at settle; animated `font_color` providers (rainbow, color_cycle, shimmer) freeze during the spin and resume at settle. On scale-1 displays hi-res fonts still display unrotated — `led-ticker validate` warns (rule 63) for that case only.
- **Short-hold warning.** If `spin_seconds` outlasts `hold_time` the spin is truncated and the text appears only briefly. `led-ticker validate` warns (rule 62). Either raise `hold_time` or lower `spin_seconds` / `revolutions`.
- **Phase resets each visit.** The spin restarts from the beginning every time the widget enters the rotation — it does not continue mid-spin across section cycles.

## Spinout transition

`flair.spinout` spins the outgoing widget's on-screen content like a propeller — starting at rest and accelerating — then cuts to the incoming widget. The outgoing section's background color holds through the entire spin.

Requires **led-ticker-core >= 4.6**.

### Config

```toml
[[playlist.section]]
transition = "flair.spinout"
```

With knobs:

```toml
[[playlist.section]]
transition = {type = "flair.spinout", revolutions = 3, direction = "ccw"}
```

### Knobs

| Knob | Default | Meaning |
| --- | --- | --- |
| `revolutions` | `2` | Full turns over the transition window (int >= 1). No landing constraint — the cut replaces the content mid-whirl. |
| `direction` | `"cw"` | `"cw"` or `"ccw"`. |

### Notes

- Spin duration comes from the standard `[transitions] duration` — no separate timing knob.
- Pairs with the propeller animation for a full cycle: `animation = "flair.propeller"` spins the text in, it rests, then `transition = "flair.spinout"` spins it out.
- The outgoing content is snapshotted at its final position (scrolled text spins from where it stopped); colors freeze during the spin, same as the propeller animation.
- A propeller-animated widget cut off mid-spin (hold shorter than its spin — `led-ticker validate` rule 62 warns) enters the spinout with a residual angle and briefly compounds rotations; cosmetic and sub-second.


## Fireworks transition

`flair.fireworks` holds the outgoing widget while staggered firework bursts launch from the bottom edge, open, and fade over it; every burst's radius then blooms in lockstep toward full-panel coverage, revealing the incoming widget through the expanding circles until the whole panel is covered.

Requires **led-ticker-core >= 4.10**.

### Config

```toml
[[playlist.section]]
transition = "flair.fireworks"
```

With knobs:

```toml
[[playlist.section]]
transition = {type = "flair.fireworks", bursts = 3, colors = [[255, 60, 60], [0, 220, 220]]}
```

### Knobs

| Knob | Default | Meaning |
| --- | --- | --- |
| `bursts` | size-adaptive (3-6) | Number of firework bursts. Auto-picked from the panel's width-to-height ratio when omitted — wider panels get more bursts (smallsign: 5, bigsign: 4, longboi: 6) — or set explicitly in `[2, 8]`. |
| `colors` | 8-color built-in palette | List of `[r, g, b]` triples, cycled across bursts in order. **Note:** this is `colors`, NOT `transition_colors` — core's `transition_colors` config field does not reach plugin transitions (a known gap); `colors` is this transition's own constructor kwarg. |
| `seed` | `None` (OS entropy) | Fixes the RNG for reproducible bursts. See "Determinism and re-fire" below — this is NOT a promise that the same seed always plans the same sequence forever. |

### Notes

- **Size-adaptive by default.** Burst count, radius, and stagger timing are all derived from the panel's actual width/height at draw time — the same `transition = "flair.fireworks"` line looks right on smallsign, bigsign, and longboi without per-sign tuning.
- **Two-phase design, painted through black.** Phase one (`t < 0.5`) plays over the outgoing widget: bursts launch as a rising streak, open into a black "burn-through" hole ringed by radial spoke trails flying outward from the burst's center (bright white heads, fading colored tails — an asterisk, not an outline), while the rest of the panel still shows the outgoing widget. Phase two (`t >= 0.5`) switches to the incoming widget underneath and blacks out everything OUTSIDE the union of the (now still-growing) burst circles — so the incoming widget is revealed exactly where a burst has reached, and the transition guarantees full coverage by `t == 1.0` regardless of how any individual burst was staggered. During the bloom the spoke trails detach from the reveal: they coast a little farther, hold position, and fade to fully dark by `t = 0.85`, so the final cut to the incoming section changes nothing visible. This two-phase-through-black shape exists because there is no way to read back what's already on the panel (see the no-`GetPixel` rationale below) — every frame is drawn from scratch from the widgets + burst geometry, never composited from a previous frame's pixels.
- **No `GetPixel`.** Like every core transition, `flair.fireworks` only ever calls `SetPixel` — the real hardware framebuffer stores pre-computed GPIO bitplane data, not readable RGB, so there is no way to sample "what's currently on the panel" and erase around it. The complement-blackout in phase two is the same idea worked the other direction: instead of reading what's painted and subtracting, it computes the union of burst circles as pure geometry and paints black everywhere outside it.
- **Determinism and re-fire.** With an explicit `seed`, two FRESH `Fireworks` instances plan an identical first firing — useful for regression tests and reproducible demo GIFs. But the same instance firing a SECOND time (a real display looping through its playlist) continues drawing from that same RNG stream rather than restarting it, so consecutive firings on one running sign still look different from each other, even with a pinned seed. Leave `seed` unset (the default) for a real deploy — every firing draws fresh OS entropy and varies at runtime regardless of instance lifetime.
- **Complement pass scales with the black area, not the panel.** Phase two paints black only OUTSIDE the burst union, computed per row as merged circle/x-intervals (each circle meets a row in at most one interval; merging <= 8 is trivial) — cost is `O(rows x bursts log bursts + black_pixels)`, shrinking to zero as the bloom completes. The widest late-bloom frames on a 512-wide longboi measure well under a millisecond.


## Fireworks background

`flair.fireworks` is ALSO a **background** effect: `background = "flair.fireworks"` on a `message`, `countdown`/`countup`, `two_row`, `gif`, `image`, or `clock` widget plays continuous fireworks BEHIND the widget's content for as long as it is on screen. Same look as the transition (a rocket streak rises from the bottom edge, pops into a 10-14 spoke asterisk that eases open, coasts and fades), but it never blacks anything out and never ends — a new rocket launches every `3s / bursts`. The name is shared with the transition on purpose; `background = ...` and `transition = ...` are different registries, so the two coexist. Because `background` is its own slot, it composes with a real `border` (e.g. `border = "rainbow"`).

Requires **led-ticker-core >= 4.32** (the `background` field; see [Backgrounds](https://docs.ledticker.dev/concepts/backgrounds/)).

### Config

```toml
[[playlist.section.widget]]
type = "message"
text = "HAPPY NEW YEAR"
font_color = [255, 255, 255]
border = "rainbow"
background = "flair.fireworks"
```

With knobs:

```toml
background = {style = "flair.fireworks", bursts = 3, speed = 1.5, colors = [[255, 60, 60], [255, 180, 0]]}
```

### Knobs

| Knob | Default | Meaning |
| --- | --- | --- |
| `bursts` | size-adaptive (3-6) | Concurrent firework slots, phase-staggered evenly. Same auto-pick as the transition (smallsign: 5, bigsign: 4, longboi: 6) or explicit in `[2, 8]`. |
| `speed` | `1.0` | Playback multiplier. `1.0` = a slot's full launch→open→fade cycle takes 3 s (60 engine ticks); `2.0` halves that, `0.5` doubles it. |
| `colors` | 8-color built-in palette | List of `[r, g, b]` triples; each burst picks one at random (the transition cycles them in order). |
| `seed` | `None` (OS entropy) | Fixes the show for reproducible demo GIFs. Unseeded, each instance draws one seed at construction, so two signs differ but a single sign's show is still a pure function of its frame counter. |

### Notes

- **Behind everything, by construction.** Every host widget paints `background` first — under the image on `gif`/`image`, before the `border`, before the text — so content always wins on collision and no z-order knob is needed.
- **Never paints black.** The transition's burn-through holes and complement blackout are deliberately NOT used here, and any spoke/tail pixel that rounds to pure black is dropped — a background must not erase a host's `bg_color` or image.
- **Frame-pure.** Each burst's plan is derived from `(seed, slot, cycle index)` and its phase from the host's `frame_for("background")` counter alone, so a transition that pauses the counter and re-renders the widget while compositing sees the same pixels every time. `restart_on_visit = False`: the show continues across `loop_count > 1` visits instead of replaying the opening rocket.
- **Physical resolution.** Paints to the real canvas (`unwrap_to_real`), so a spoke is one LED on the bigsign, not a 4×4 block; burst count and radius follow the REAL panel dims.
- **Static fast paths.** `frame_invariant = False`, so the `gif`/`image` static-text fast path is bypassed and the background animates — the same contract animated borders use.

## Stickers transition

`flair.stickers` holds the outgoing widget while individual emoji stickers pop on randomly across the panel in a jittered grid, building toward full coverage by `t=0.5`, then pop off in an independent order revealing the incoming widget underneath.

![flair.stickers — a wall of taco cards builds over the outgoing widget, then peels away to reveal the incoming one](docs/transition-stickers.gif)

Requires **led-ticker-core >= 4.18.0**.

### Config

Taco wall — all stickers are the same emoji:

```toml
[[playlist.section]]
transition = {type = "flair.stickers", emoji = ["taco"]}
```

Mixed assortment — multiple distinct emoji:

```toml
[[playlist.section]]
transition = {type = "flair.stickers", emoji = ["sun", "moon", "star_yellow"]}
```

Bare random form — each firing samples up to 12 distinct slugs from the full drawable set (flair >= 0.13.0; with core >= 4.21.0's standard-emoji pack that set is ~1,360 emoji) and builds the wall from those:

```toml
[[playlist.section]]
transition = "flair.stickers"
```

Swarm looks — swap the card for a lighter sticker body:

```toml
transition = {type = "flair.stickers", emoji = ["taco"], backing = "shadow"}
transition = {type = "flair.stickers", emoji = ["taco"], backing = "none"}
```

`backing` picks the sticker body: `"card"` (default — tilted black card with a
white rim; the only mode that fully covers the panel at the midpoint),
`"shadow"` (black silhouette halo, no card), or `"none"` (bare sprites). The
latter two read as an emoji **swarm** over the content rather than a wall —
the outgoing widget stays visible through the gaps between sprites, by design.


### Knobs

| Knob | Type | Default | Meaning |
| --- | --- | --- | --- |
| `emoji` | list of strings, or omitted | omitted (random assortment) | Slug pool for stickers. Each string must be a known drawable emoji slug (e.g., `taco`, `sun`, `moon`, `star_yellow`, `heart_red`, `pride`). A single-item list (`["taco"]`) creates a themed wall of one emoji; explicit lists are never capped. Omitting the field samples ≤ 12 distinct slugs per firing (`_RANDOM_VARIETY_CAP`) from the complete drawable set — resampled every firing, so consecutive firings differ wildly while each wall stays coherent. |
| `backing` | `"card"` / `"shadow"` / `"none"` | `"card"` | Sticker body. `"card"`: tilted black card with a white rim — the only mode that fully covers the panel at the midpoint. `"shadow"`: black silhouette halo, no card. `"none"`: bare sprites. Shadow/none read as an emoji swarm over the content (gaps stay visible, by design). |
| `seed` | int, or omitted | omitted (OS entropy) | Fixes the sticker positions, angles, and arrival/departure timing for reproducible patterns. See "Determinism and re-fire" below. |

### Notes

- **Die-cut appearance.** Each sticker sits on a black card with a white rim outline — the cards are square and sized to fully cover the panel when arranged in a jittered grid, so `t=0.5` (full build) reaches 100% coverage regardless of emoji shape or panel geometry. Rotations tilt each card within its slot for visual variety.
- **Full coverage at mid-transition guaranteed.** The grid layout (`plan_stickers`) is constructed from a `GRID_OVERLAP` ratio that ensures no uncovered gaps between card squares; coverage is proved across all drawable emoji and both panel geometries (smallsign and bigsign) via the test suite's seed-sweep calibration tests. If coverage ever fails, tighten `GRID_OVERLAP` in the source; do not weaken the tests.
- **Unknown emoji slugs rejected at config-load.** Writing `emoji = ["dragon"]` raises a validation error at `led-ticker validate` time (before deploy) because `"dragon"` is not in the drawable slug set. Use only known slugs: `taco`, `fire`, `sun`, `moon`, `star_yellow`, `heart_red`, `pride`, and any other emoji registered via `emoji_slugs()` (which includes core slugs and plugin-registered custom emoji).
- **Determinism and re-fire.** With an explicit `seed`, two FRESH `Stickers` instances plan an identical FIRST firing. But firing the SAME instance a second time (a real display looping through its playlist) continues drawing from that same RNG stream, so consecutive firings vary at runtime even with a pinned seed. Leave `seed` unset for a real deploy.
- **Single pass rasterization.** Stickers are captured, composed (sprite + black backing + white rim), and rotated ONCE during the first `frame_at` call for a given canvas size and scale — every subsequent frame just paints the pre-rasterized pixels at different positions and scales. The preparation is cheap compared to spinning emoji sprites mid-transition, so plan-time rasterization is preferred over per-frame capture.


## Poker transition

`flair.poker` holds the outgoing widget while rainbow card suits (♥ ♦ ♣ ♠) pattern in and emit suit-shaped ripple rings — an expanding heart emits heart-shaped rings, a club club-shaped ones — revealing the incoming widget through expanding ripple wakes until the whole panel is washed.

![flair.poker — rainbow suit glyphs emit suit-shaped ripples that wash in the incoming widget](docs/transition-poker.gif)

Requires **led-ticker-core >= 4.18.0**.

### Config

All four suits (hearts, diamonds, clubs, spades cycle):

```toml
[[playlist.section]]
transition = "flair.poker"
```

Diamonds only:

```toml
[[playlist.section]]
transition = {type = "flair.poker", suits = ["diamonds"]}
```

Clubs only:

```toml
[[playlist.section]]
transition = {type = "flair.poker", suits = ["clubs"]}
```

With seed for reproducibility:

```toml
[[playlist.section]]
transition = {type = "flair.poker", suits = ["hearts", "spades"], seed = 42}
```

### Knobs

| Knob | Type | Default | Meaning |
| --- | --- | --- | --- |
| `suits` | list of strings | `["hearts", "diamonds", "clubs", "spades"]` (all four) | Suit pool to cycle. Valid names: `hearts`, `diamonds`, `clubs`, `spades`. Unknown suit names fail at config-load. |
| `seed` | int, or omitted | omitted (OS entropy) | Fixes the glyph positions and hue ordering for reproducible patterns. See "Determinism and re-fire" below. |

### Notes

- **Suit shapes are pure math masks.** Each suit (heart, diamond, club, spade) is defined by an implicit curve or lobes; the same mathematical mask is used for both the resting glyph and every ripple ring, giving suit-shaped expanding waves.
- **Two-phase design.** Phase one (first ~0.45 of the transition) paints glyphs and ripples over the outgoing widget. Phase two switches to the incoming widget and blacks out everything OUTSIDE the reveal union until the whole panel is washed — **incoming widget is revealed against black during the second half, not composited over the old content** (hardware constraint: no `GetPixel` support means no pixel-by-pixel reading and masking of the displayed content).
- **Determinism and re-fire.** With an explicit `seed`, two FRESH `Poker` instances plan an identical FIRST firing. But firing the SAME instance a second time continues drawing from that same RNG stream, so consecutive firings vary at runtime even with a pinned seed. Leave `seed` unset for a real deploy.
- **Plan-time ring pre-rasterization only.** Ring pixel-lists (the ripple wavefronts and glyph interiors) are computed once per firing and cached; per-frame work is SetPixel iteration only — no shape rasterization per tick. Tripwire test `test_no_ring_rasterization_after_first_frame` enforces this performance contract.


## Lightning transition

`flair.lightning` strikes a zigzag bolt across the outgoing widget — white-hot head, flickering electric blue-white trail — then the crack pulls apart into twin glowing zigzag edges, revealing the incoming widget inside the widening gap.

![flair.lightning — a zigzag bolt strikes across, then the crack opens revealing the incoming widget](docs/transition-lightning.gif)

Requires **led-ticker-core >= 4.18.0**.

### Config

Fresh bolt shape every firing:

```toml
[[playlist.section]]
transition = "flair.lightning"
```

Reproducible bolt path:

```toml
[[playlist.section]]
transition = {type = "flair.lightning", seed = 42}
```

Tinted trail (the strike head stays white-hot):

```toml
[[playlist.section]]
transition = {type = "flair.lightning", color = [255, 92, 38]}
```

### Knobs

| Knob | Type | Default | Meaning |
| --- | --- | --- | --- |
| `seed` | int, or omitted | omitted (OS entropy) | Fixes the bolt path for reproducible strikes. Leave unset for a real deploy — every firing gets a fresh bolt. |
| `color` | `[r, g, b]` (0–255), or omitted | electric blue-white `[150, 190, 255]` | Tints the bolt trail and the peel-phase crack edges. The strike head is always white. |

### Notes

- **Two-phase design.** Phase one (first ~0.45 of the transition) draws the bolt left→right over the outgoing widget. Phase two cuts to the incoming widget and opens the crack: the zigzag duplicates into two edges moving apart, the incoming is visible between them, and everything outside the gap is blacked out — **the incoming is revealed against black, not composited over the old content** (hardware constraint: no `GetPixel` means the outgoing's pixels can't be read back and slid apart).
- **Bolt geometry.** A random-walk zigzag with a vertex every 6–10 logical px, strictly alternating direction, confined to the center half of the panel height. Section backgrounds (`bg_color`) show inside the gap from the first sliver.
- **No caches, no warm-up.** Every frame is a pure function of `t`; the only per-firing state is the bolt polyline. The first firing after boot costs the same as every other one, and per-frame paint volume is bounded by panel size (enforced by the `TestPerfUniformity` tripwires).


## Fairy transition

`flair.fairy` sends a Tinkerbell-style fairy — a white-hot sparkle-star — across the panel trailing a long cone of gold pixie dust and settling a thin line; when the fairy reaches the far edge the line opens into two twinkling gold edges, revealing the incoming widget in the widening gap.

![flair.fairy — a fairy trails pixie dust across the panel, then the line opens to reveal the incoming widget](docs/transition-fairy.gif)

Requires **led-ticker-core >= 4.18.0**. Comes in three direction variants (sprite-family convention):

### Config

Flies left→right / right→left:

```toml
[[playlist.section]]
transition = "flair.fairy.forward"
```

```toml
[[playlist.section]]
transition = "flair.fairy.reverse"
```

Direction flips every firing:

```toml
[[playlist.section]]
transition = "flair.fairy.alternating"
```

Reproducible flight + tinted dust (the fairy head stays white):

```toml
[[playlist.section]]
transition = {type = "flair.fairy.forward", seed = 42, color = [180, 120, 255]}
```

### Knobs

| Knob | Type | Default | Meaning |
| --- | --- | --- | --- |
| `seed` | int, or omitted | omitted (OS entropy) | Fixes the flight path and the pixie-dust spark field. Leave unset for a real deploy — every firing gets a fresh flight. |
| `color` | `[r, g, b]` (0–255), or omitted | gold `[255, 215, 120]` | Tints the pixie dust, the settled line, and the peel-phase edges. The fairy head is always white. |

Direction is **not** a knob — pick the variant (`.forward` / `.reverse` / `.alternating`).

### Notes

- **Two-phase design.** Phase one (first half of the transition) flies the fairy across, drawing over the outgoing widget with a dwelling cone of stateless sparks. Phase two cuts to the incoming widget and opens the settled line: the two edges move apart, incoming visible between them, everything outside blacked out — **revealed against black, not composited over the old content** (same no-`GetPixel` constraint as lightning/poker). Section `bg_color` shows inside the gap from the first sliver.
- **Near-straight flight.** The path is single-valued per column (the reveal machinery requires it): a gentle center-band line with small drift and wobble. The magic is in the dust, not a loop-de-loop.
- **Stateless sparks, no warm-up.** Every spark is a pure function of `(column, index, quantized t)` — no particle lists, no caches. The first firing after boot costs the same as every other, and per-frame paint volume is bounded by panel size (enforced by the `TestPerfUniformity` tripwires).


## Laser transition

`flair.laser` writes the sign the way a commercial LED message board's "laser" effect does: beams reach in from one panel edge, erase the old content pixel by pixel in a back-and-forth raster, then write the new content the same way. Each beam is a solid one-pixel bar from the edge to the pixel it is working on, in that pixel's own colour, so a red headline is erased by red beams and a rainbow one by rainbow beams. It works on every widget type — the content is snapshotted as pixels, not as text.

![flair.laser — three beams erase the old message from the top, then write the new one](docs/transition-laser.gif)

Requires **led-ticker-core >= 4.32**. Six variants, named by the edge the beams come from:

| Type | Beams come from | Raster |
| --- | --- | --- |
| `flair.laser.top` | top edge | row by row, top row first |
| `flair.laser.bottom` | bottom edge | row by row, bottom row first |
| `flair.laser.left` | left edge | column by column, left first |
| `flair.laser.right` | right edge | column by column, right first |
| `flair.laser.alternating` | cycles top → right → bottom → left | one origin per firing |
| `flair.laser.random` | a different edge each firing | never the same twice running |

### Config

```toml
[transitions]
duration = 2.5        # the floor is 2.4 s (min_frames = 48); 2.5–3.5 s reads well

[[playlist.section]]
transition = "flair.laser.top"
```

A different edge every firing:

```toml
[[playlist.section]]
transition = "flair.laser.alternating"
```

Two beams instead of three, or the classic single raster:

```toml
[[playlist.section]]
transition = {type = "flair.laser.left", beams = 2}
```

```toml
[[playlist.section]]
transition = {type = "flair.laser.top", beams = 1}
```

Erase from one edge, write from another — the old text leaves to the left while the new text arrives from the right:

```toml
[[playlist.section]]
transition = {type = "flair.laser.left", write_from = "right"}
```

```toml
[[playlist.section]]
transition = {type = "flair.laser.alternating", write_from = "opposite"}   # whatever edge erases, the opposite one writes
```

### Knobs

| Knob | Type | Default | Meaning |
| --- | --- | --- | --- |
| `beams` | positive int | `3` | Number of independent beams. The lit content is split into that many equal slices (across the panel for top/bottom, down it for left/right) and each beam erases then writes its own slice at its own constant speed. `1` is the classic single back-and-forth raster. |
| `write_from` | `"top"` / `"bottom"` / `"left"` / `"right"` / `"opposite"`, or omitted | omitted (same edge as the erase) | The edge the **write** phase's beams come from. The type names the erase edge. `"opposite"` mirrors whatever edge is erasing, so it composes with `.alternating` and `.random`. When the two edges share an axis (left/right, or top/bottom) each beam erases and writes the same slice; across axes (left then top) the slices are split per phase and beams pair up by index. |

The erase direction is **not** a knob — pick the variant. The beam colour is always the content's own colour.

### Notes

- **Two phases, one timeline.** The transition's `duration` covers both erase and write; time splits in proportion to how many lit pixels each side has, so a short message erases quickly and a long one takes longer. An empty outgoing (boot, wake from dark) goes straight to writing. All beams finish together at 95 % of the duration; the last 5 % is the usual snap to the incoming widget.
- **Backgrounds.** The section `bg_color` is painted by the engine, never by the widget, so it is never lasered: erased pixels simply show the old background, and the panel switches to the new background the moment the first beam starts writing. A widget's own fill (`image`/`gif` `bg_color`, `two_row` band colours) IS content and gets written pixel by pixel.
- **Snapshot, not a live draw.** Both widgets are drawn once per firing into an offscreen raster at physical resolution; the beams work from that. A clock ticking over or a source refreshing mid-transition can't leave stray pixels behind. On the bigsign a logical pixel is a 4×4 block and gets written in four passes of four, with a one-real-pixel beam.
- **Cross-scale sections.** When the next section uses a different `scale`, the incoming content is written at the outgoing scale and pops to its own size on the final frame — the same accepted limitation as `flair.fairy` / `flair.lightning` / `flair.fireworks`.
- **Perf.** Per-frame work is bounded by the number of lit pixels (≤ panel size) plus one bar per beam; the only non-trivial cost is the one snapshot frame per firing. Enforced by the `TestPerfUniformity` tripwires.

## Accordion transition

`flair.accordion` plays the outgoing content like a dealer spreading a deck of cards: the message bunches into an overlapping stack that slides off one edge, then the incoming stack slides in from the far edge and fans out into place. Overlap is real occlusion, like a card fan, and the spread is tied to travel, so the content is tightest at the panel edge and reaches its full spacing exactly on arrival. It works on every widget type; the content is snapshotted as pixels, not as text.

![flair.accordion.sweep — the old message bunches into a deck and slides off left, the new one slides in and fans out](docs/transition-accordion.gif)

Requires **led-ticker-core >= 4.32**. Two motions, each with an alternating variant:

| Type | Motion |
| --- | --- |
| `flair.accordion.sweep` | Cards are scooped up one by one and the stack is pushed off; the incoming stack is laid down card by card. |
| `flair.accordion.stretch` | The content moves as one piece, squeezing shut as it leaves and opening up as it lands. |
| `flair.accordion.sweep.alternating` | Sweep, flipping sides each time it fires: left, then right, then left. |
| `flair.accordion.stretch.alternating` | Stretch, flipping sides each time it fires. |

### Config

```toml
[transitions]
duration = 2.0
easing = "ease_in_out"

[[playlist.section]]
transition = "flair.accordion.sweep"

[[playlist.section]]
transition = {type = "flair.accordion.stretch", direction = "right"}
```

### Knobs

| Knob | Type | Default | Meaning |
| --- | --- | --- | --- |
| `direction` | `"left"` / `"right"` | `"left"` | `"left"` exits left and enters from the right; `"right"` mirrors it. |

On the `.alternating` variants, `direction` picks the side of the **first** firing; after that it flips every time (`"left"` → left, right, left, …; `"right"` → right, left, right, …).

```toml
transition = {type = "flair.accordion.sweep.alternating", direction = "right"}
```

Recommended: `duration = 2.0` with `easing = "ease_in_out"`.

### Notes

- **Borders stay still.** A bordered widget keeps its border ring in place, painted over the cards; the content moves, including any text that overlaps the ring.
- **Two-row widgets.** Each row gets its own deck; the decks move in lockstep. Each pixel goes with the row that draws it, so a descender, an i or j dot, or a `text_y_offset` nudge stays with its own row; where the two rows overlap, a pixel both rows draw goes to the band it sits in. (A two-row widget with a `background` is the exception: see below.)
- **Background effects.** A widget with a `background` effect (and full-panel image/gif widgets) has no gaps to fan, so it slides as a single card (both rows of a `two_row` included).
- **Image/gif widgets.** Core draws only the picture during a transition (no border, no text overlay), so a bordered or captioned image gets no ring and no row split: the picture moves as one deck.
- **Backgrounds.** The section `bg_color` is painted by the engine, never by the transition. The panel switches to the new section's background at the halfway point, on the same frame the incoming deck starts to slide in, with no black flash. The short empty beat just before it (which can be zero frames on a fast transition) still shows the outgoing background.
- **Cross-scale sections.** The incoming content is snapshotted at its own scale, so it arrives at its native size.

## Fisheye animation

`flair.fisheye` sends a scrolling message through a stationary "fisheye lens" centered on the panel: letters enter compressed at the edges, swell as they cross the middle, and compress again on the way out — the marquee bulges through a fixed lens while the text moves through it.

Requires **led-ticker-core >= 4.7**. Message widgets only (v0.4.0). On scaled displays (bigsign) the whole scroll renders at half detail; the lens distortion masks it.

### Config

```toml
[[playlist.section.widget]]
type = "message"
text = "FISH EYE MARQUEE"
animation = "flair.fisheye"
```

With knobs (a stronger lens):

```toml
[[playlist.section.widget]]
type = "message"
text = "FISH EYE MARQUEE"
animation = {style = "flair.fisheye", magnify = 1.33, edge_squeeze = 0.45}
```

### Knobs

| Knob | Default | Meaning |
| --- | --- | --- |
| `magnify` | `1.3` | Center scale (both axes). Capped by the panel height: `magnify × font line-height ≤ content_height`, else the bulged text would clip and config-load raises. For the default 6×12 font in a 16-row band the ceiling is ~1.33. |
| `edge_squeeze` | `0.6` | Edge scale (`0 < edge_squeeze ≤ 1`). Lower = more edge compression = a more dramatic lens. |
| `profile` | `"cosine"` | The falloff curve from edge to center. |

### Notes

- The lens is stationary; the scroll provides all the motion — so the effect is continuous with no phase, and a section can cut away at any instant.
- **Edges show more text by design.** The lens is width-preserving (total scroll traversal matches an unwarped scroll), but the compressed edges reveal ~8–9 extra characters per side — the squeeze fits more in.
- Colors stay live through the lens: a `rainbow` / `color_cycle` `font_color` keeps sweeping as the text scrolls (no freeze).
- Held (non-overflowing) text shows a static center bulge — a legitimate emphasis look.


## Lottery widget

`flair.lottery` rolls N labeled balls in from off-canvas left, one at a time, in a staggered relay — each ball tumbles as it rolls (the word visibly spins with the face) and settles flat, upright, into an evenly spaced slot across the panel. A physical lottery-ball draw, rendered as a held widget.

Requires **led-ticker-core >= 4.10** (the rotation-translation seam the roll-in uses) and a **scaled display (bigsign only)** — the balls paint at physical resolution via the same hi-res machinery as inline emoji and hi-res fonts. On an unscaled display (smallsign, `default_scale = 1`) the widget logs a warning once and paints nothing; `led-ticker validate` also warns at config-load time so this shows up before deploy, not after.

### Config

```toml
[[playlist.section.widget]]
type = "flair.lottery"
words = ["fresh", "hot", "kebab"]
ball_style = "classic"
border = "rainbow"
```

### Both styles

- **`ball_style = "classic"`** (default) — a white face with a colored rim ring and dark text, like a real lottery ball.
- **`ball_style = "solid"`** — a solid color-filled face with white text.

```toml
[[playlist.section.widget]]
type = "flair.lottery"
words = ["fresh", "hot", "kebab"]
ball_style = "solid"
colors = [[255, 60, 60], [60, 220, 60], [255, 180, 0]]
```

### Knobs

| Field | Type | Default | Notes |
|---|---|---|---|
| `words` | list[str], 1-8 | required | One ball per word. |
| `ball_style` | `"classic"` / `"solid"` | `"classic"` | See above. |
| `colors` | list of `[r, g, b]` | auto-palette | Must match `words` length if given. Colors the ring (classic) or the fill (solid). |
| `roll_ms` | int >= 100 | `800` | Wall-clock roll duration per ball (the staggered relay's per-ball window). |
| `choreography` | `"rack_fill"` / `"roll_through"` | `"rack_fill"` | Entry order. `rack_fill`: first ball rolls to the RIGHTMOST slot, each next stops short — no ball ever crosses a settled one. `roll_through`: balls fill left-to-right in word order, later balls visibly rolling in front of the settled ones they pass. Both end reading `words` left-to-right. |
| `font` | str | `"Inter-Bold"` | Hi-res font used for each ball's label. |
| `border` | any core border spec | none | Same `border` field as `message`/`countdown`/`two_row`/etc — paints the panel perimeter, not the balls. |

### Auto-palette when `colors` is omitted

Omitting `colors` cycles the balls through an 8-color built-in palette in order (red, green, amber, blue, magenta, cyan, orange, violet), repeating if there are more than 8 words. Set `colors` explicitly to override any or all of them — the list must be the same length as `words`.

### Derived sizing — no size knobs

There is no `ball_size` / `diameter` field: ball diameter, slot spacing, and font size are all derived from the panel geometry and word count (`layout()` fits `n` evenly-spaced slots across the panel width, capped by the content-band height; `auto_font_size()` picks the largest label size that fits the ball's circular face). Fewer/shorter words get bigger balls; more/longer words get smaller ones. If a word genuinely can't fit any legible label size, `led-ticker validate` warns at config-load and the ball still renders (unlabeled) at render time — check the warning rather than trying to tune around it with a size knob that doesn't exist.

### Bigsign-only, and border support

Same physical-resolution requirement as inline hi-res emoji — see the requirement note above. `border` composes normally: it paints the panel perimeter before the balls (same order as every other bordered widget), and the smoke config in `examples/config.lottery-smoke.bigsign.toml` demonstrates a `rainbow` border alongside classic-style balls.

## Blink animation

`flair.blink` flashes a message widget's text hard on and off: the text is visible for the "on" fraction of each period and blank for the rest. Frame 0 is always ON, so a visit opens on readable text; when a hold would end mid-blank, the hold is extended to the next ON phase so the transition leaves from visible text (up to the engine's 1 s settle limit, which is why an OFF phase longer than 20 frames is refused).

Requires **led-ticker-core >= 4.33**.

### Config

```toml
[[playlist.section.widget]]
type = "message"
text = "SALE TODAY"
font_color = [255, 80, 80]
animation = "flair.blink"
```

With knobs:

```toml
animation = {style = "flair.blink", period_ms = 1500, duty = 0.6, count = 4}
```

### Knobs

| Knob | Default | Meaning |
| --- | --- | --- |
| `period_ms` | `1000` | One on+off cycle, counted in animation frames (`period_ms / 50`, rounded). Minimum `850` without `allow_fast`; the OFF phase (`period - on`) may be at most 20 frames (1 s). |
| `duty` | `0.75` | Fraction of the period the text is visible, in `(0, 1)`. |
| `count` | `0` | Number of blinks, then stay on. `0` = blink forever. |
| `allow_fast` | `false` | Opt in to periods shorter than 850 ms (on/off rates above 3 Hz). |

### Notes

- **Photosensitivity guard.** The period counts animation frames, and on scrolling text the engine advances a frame once per scroll step (as fast as 20 ms), not every 50 ms. So that blinking never exceeds 3 Hz (WCAG 2.3.1) even at a 20 ms scroll cadence, the minimum `period_ms` is `850` (17 frames x 20 ms = 340 ms per cycle). Faster on/off rates are refused at config-load unless you set `allow_fast = true`. Think before you do.
- **Long OFF phases are refused.** The OFF phase (`period_ms` x (1 - `duty`), in frames) may not exceed 20 frames (1 s), the most the engine will extend a hold to land a transition on visible text. Use a shorter period or a higher duty (for example `period_ms = 2000, duty = 0.5` is fine; `3000` at `0.5` is not).
- Emoji and colored value tokens blank with the text; borders and backgrounds stay lit.
- Blink shares the ONE `animation` slot with twinkle, `typewriter` and `flair.fisheye`, so they cannot be combined. On `gif`/`image` widgets an animation needs a non-scroll `text_align`.
- `allow_fast` must be a real boolean (`true`/`false`), not a string.

## Twinkle animation

`flair.twinkle` makes a message widget's text sparkle TwinkleFOX-style: a share of the text's pixels each cycle between dim and full brightness on their own phase, so the letters shimmer while staying readable.

Requires **led-ticker-core >= 4.33** (the per-pixel `pixel_gain` seam).

### Config

```toml
[[playlist.section.widget]]
type = "message"
text = "MAKE A WISH"
font_color = [255, 220, 120]
animation = "flair.twinkle"
```

With knobs:

```toml
animation = {style = "flair.twinkle", density = 0.8, speed = 1.5, min_brightness = 0.1}
```

### Knobs

| Knob | Default | Meaning |
| --- | --- | --- |
| `density` | `0.6` | Fraction of text pixels that twinkle, in `(0, 1]`; the rest hold full brightness. |
| `speed` | `1.0` | Twinkle rate in `(0, 2.0]` (capped to stay photosensitivity-safe). |
| `min_brightness` | `0.15` | Dimmest a twinkler gets, in `[0, 1)`. |
| `seed` | `None` (OS entropy) | Fixes the pattern for reproducible demo GIFs. |

### Notes

- **Twinkle speed follows the scroll cadence.** On scrolling text the animation counter advances once per scroll step, so the shimmer runs faster on fast-scroll sections. Twinkle never dims a pixel fully off, so it is not a WCAG flash and has no rate cap beyond `speed <= 2.0`.
- **Twinkle is a hold effect.** The sparkle field is fixed to the panel, not to the text, so on scrolling text it reads as static noise rather than letters shimmering. Use it on text that holds still.
- Twinkle, blink, `typewriter` and `flair.fisheye` all share the ONE `animation` slot of a widget, so they cannot be combined. On `gif`/`image` widgets an animation needs a non-scroll `text_align`.
- Only the text twinkles; borders and backgrounds are untouched, so it composes with `background = "flair.twinkle"` or `"flair.snow"`.
- BDF text on a scaled sign (bigsign) twinkles per logical pixel; hi-res fonts twinkle per real pixel. Animated image emoji do not twinkle.

## Twinkle background

`flair.twinkle` is ALSO a **background** effect: `background = "flair.twinkle"` paints a twinkling starfield BEHIND a `message`, `countdown`/`countup`, `two_row`, `gif`, `image`, or `clock` widget. Stars are single physical LEDs, so the field looks like fine glitter on every sign. It never paints black, so it can't erase a `bg_color` or an image.

Requires **led-ticker-core >= 4.32**.

### Config

```toml
[[playlist.section.widget]]
type = "message"
text = "STARRY NIGHT"
font_color = [180, 200, 255]
background = "flair.twinkle"
```

With knobs:

```toml
background = {style = "flair.twinkle", density = 0.05, speed = 1.2, color = [255, 200, 120]}
```

### Knobs

| Knob | Default | Meaning |
| --- | --- | --- |
| `density` | `0.03` | Fraction of panel pixels that are stars, in `(0, 1]`. |
| `speed` | `1.0` | Twinkle rate in `(0, 2.0]`. |
| `color` | `[255, 230, 180]` | Peak star color; each star scales it by its brightness. |
| `seed` | `None` (OS entropy) | Fixes the starfield for reproducible demo GIFs. |

### Notes

- Frame-pure and physical-resolution, like every flair background; `restart_on_visit = False` so the field keeps twinkling across repeat visits.

## Snow background

`flair.snow` is a **background** effect: `background = "flair.snow"` drops snow BEHIND a widget's content. Each flake falls at its own speed, drifts a little sideways and re-enters at a new column when it wraps. Flakes are `"dot"` (one LED), `"plus"` (a 5-LED cross), `"flake"` (a hand-drawn 5x5 snowflake, 9 LEDs) or an 8x8 emoji sprite; emoji flakes are painted 1:1 on the real panel, so on a bigsign they are 8 LEDs wide, not block-expanded. Emoji slugs use their 8x8 low-res form, which is not always a snowflake: `:snow:` is a grey rain-cloud weather icon, so use `flake = "flake"` for snow.

Requires **led-ticker-core >= 4.32**.

### Config

```toml
[[playlist.section.widget]]
type = "message"
text = "LET IT SNOW"
font_color = [200, 230, 255]
background = "flair.snow"
```

With emoji flakes and knobs:

```toml
background = {style = "flair.snow", flake = "flake", density = 1.0, wind = 0.1}
```

### Knobs

| Knob | Default | Meaning |
| --- | --- | --- |
| `flake` | `"dot"` | `"dot"`, `"plus"`, `"flake"` (5x5 snowflake), or an emoji slug with an 8x8 low-res form. Hires-only / pack-only slugs are refused. |
| `density` | `3.0` | Flakes per 1000 panel pixels, in `(0, 50]`. |
| `speed` | `1.0` | Fall speed in `(0, 5]`. |
| `speed_variation` | `0.4` | Per-flake speed spread in `[0, 1)`. |
| `drift` | `0.3` | Sideways sway amplitude, `>= 0`. |
| `wind` | `0.0` | Constant sideways push (negative blows left). |
| `color` | `[200, 220, 255]` | Flake color for `dot`/`plus`/`flake` (emoji keep their own colors). |
| `seed` | `None` (OS entropy) | Fixes the pattern for reproducible demo GIFs. |

### Notes

- Never paints black and is a pure function of the host's frame counter, so transitions re-rendering the widget see identical pixels.

## Snow transition

`flair.snow` swaps content behind a flurry: a ragged front of snow sweeps down the panel, and flakes lead it, revealing the incoming widget above the front while the outgoing content is still visible below. The flurry builds in the middle and thins to nothing before the final cut. Works on every widget type (content is snapshotted as pixels).

Requires **led-ticker-core >= 4.32**.

### Config

```toml
[[playlist.section.widget]]
type = "message"
text = "WINTER"
transition = "flair.snow"
```

With knobs:

```toml
transition = {type = "flair.snow", flake = "flake", density = 8.0, wind = 0.2}
```

### Knobs

| Knob | Default | Meaning |
| --- | --- | --- |
| `flake` | `"dot"` | `"dot"`, `"plus"`, `"flake"` or an 8x8 emoji slug (same rules as the background). |
| `density` | `6.0` | Flakes per 1000 panel pixels at the peak, in `(0, 50]`. |
| `drift` / `wind` | `0.3` / `0.0` | Sideways sway / constant push. |
| `color` | `[230, 240, 255]` | Flake color for `dot`/`plus`/`flake`. |
| `seed` | `None` (OS entropy) | Unset, every firing draws a new pattern; set it for reproducible GIFs. |
| `mode` | `"flurry"` | Only `"flurry"` today; `"build"` is reserved. |

### Notes

- Known limit: a cross-scale incoming widget renders at the outgoing scale until the snap (the scale switch is deferred to the final cut, same as `flair.laser`).
- Cross-scale sections: the scale switch is deferred to the final snap, so adjacent sections with different `bg_color` pop at the snap rather than following the front (same limitation as `flair.laser` / `flair.fairy`).

## Install

Part of the [led-ticker-plugins](https://github.com/JamesAwesome/led-ticker-plugins) monorepo. Install:

```bash
pip install "git+https://github.com/JamesAwesome/led-ticker-plugins.git@flair-v0.1.0#subdirectory=plugins/flair"
```
