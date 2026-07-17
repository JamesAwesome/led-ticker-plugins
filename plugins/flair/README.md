# led-ticker-flair

Homage sprite-trail transitions and text animations for [led-ticker](https://github.com/JamesAwesome/led-ticker) — four sprite families plus the propeller animation, all in one wheel.

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


## Stickers transition

`flair.stickers` holds the outgoing widget while individual emoji stickers pop on randomly across the panel in a jittered grid, building toward full coverage by `t=0.5`, then pop off in an independent order revealing the incoming widget underneath.

Requires **led-ticker-core >= 4.10**.

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

Bare random form — random slug per sticker, drawn from the full drawable set:

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
| `emoji` | list of strings, or omitted | omitted (random assortment) | Slug pool for stickers. Each string must be a known drawable emoji slug (e.g., `taco`, `sun`, `moon`, `star_yellow`, `heart_red`, `pride`). A single-item list (`["taco"]`) creates a themed wall of one emoji; omitting the field draws a random slug per sticker from the complete drawable set. |
| `backing` | `"card"` / `"shadow"` / `"none"` | `"card"` | Sticker body. `"card"`: tilted black card with a white rim — the only mode that fully covers the panel at the midpoint. `"shadow"`: black silhouette halo, no card. `"none"`: bare sprites. Shadow/none read as an emoji swarm over the content (gaps stay visible, by design). |
| `seed` | int, or omitted | omitted (OS entropy) | Fixes the sticker positions, angles, and arrival/departure timing for reproducible patterns. See "Determinism and re-fire" below. |

### Notes

- **Die-cut appearance.** Each sticker sits on a black card with a white rim outline — the cards are square and sized to fully cover the panel when arranged in a jittered grid, so `t=0.5` (full build) reaches 100% coverage regardless of emoji shape or panel geometry. Rotations tilt each card within its slot for visual variety.
- **Full coverage at mid-transition guaranteed.** The grid layout (`plan_stickers`) is constructed from a `GRID_OVERLAP` ratio that ensures no uncovered gaps between card squares; coverage is proved across all drawable emoji and both panel geometries (smallsign and bigsign) via the test suite's seed-sweep calibration tests. If coverage ever fails, tighten `GRID_OVERLAP` in the source; do not weaken the tests.
- **Unknown emoji slugs rejected at config-load.** Writing `emoji = ["fire"]` raises a validation error at `led-ticker validate` time (before deploy) because `"fire"` is not in the drawable slug set. Use only known slugs: `taco`, `sun`, `moon`, `star_yellow`, `heart_red`, `pride`, and any other emoji registered via `emoji_slugs()` (which includes core slugs and plugin-registered custom emoji).
- **Determinism and re-fire.** With an explicit `seed`, two FRESH `Stickers` instances plan an identical FIRST firing. But firing the SAME instance a second time (a real display looping through its playlist) continues drawing from that same RNG stream, so consecutive firings vary at runtime even with a pinned seed. Leave `seed` unset for a real deploy.
- **Single pass rasterization.** Stickers are captured, composed (sprite + black backing + white rim), and rotated ONCE during the first `frame_at` call for a given canvas size and scale — every subsequent frame just paints the pre-rasterized pixels at different positions and scales. The preparation is cheap compared to spinning emoji sprites mid-transition, so plan-time rasterization is preferred over per-frame capture.


## Poker transition

`flair.poker` holds the outgoing widget while rainbow card suits (♥ ♦ ♣ ♠) pattern in and emit suit-shaped ripple rings — an expanding heart emits heart-shaped rings, a club club-shaped ones — revealing the incoming widget through expanding ripple wakes until the whole panel is washed.

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

## Install

Part of the [led-ticker-plugins](https://github.com/JamesAwesome/led-ticker-plugins) monorepo. Install:

```bash
pip install "git+https://github.com/JamesAwesome/led-ticker-plugins.git@flair-v0.1.0#subdirectory=plugins/flair"
```
