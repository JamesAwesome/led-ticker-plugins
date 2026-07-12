# Handoff: LED-Ticker Flight Tracker

## Overview
A live aircraft-overhead display for physical **LED dot-matrix signs**. It reads nearby
ADS-B traffic (callsign, aircraft type, altitude + vertical rate, ground speed, track,
distance/bearing) and renders it — refreshed roughly every 10 s — as lit LEDs on pure
black, in the visual language of a real transit/airport sign. Information design is
modeled after *The Flight Wall*: data-forward, no filler.

Three physical sign form factors are targeted, each with one chosen layout:

| Sign | Logical grid | Physical px | Scale | Hi-res? | Chosen layout |
|------|-------------|-------------|-------|---------|---------------|
| **smallsign** | 160 × 16 | 160 × 16 | 1 | no (BDF only) | Single-line ticker |
| **bigsign** | 64 × 16 | 256 × 64 | 4 | yes | Hi-res hero ident |
| **longboi** | 128 × 16 | 512 × 64 | 4 | yes | Dashboard row |

> "Logical" = the addressable coarse grid the sign's firmware exposes. "Physical" =
> the real LED count. `scale` = physical LEDs per logical cell. On `scale 4` signs you
> may light individual physical LEDs ("hi-res") for smoother large type; on `scale 1`
> everything is drawn on the coarse grid using bitmap (BDF) fonts.

## About the Design Files
The files in this bundle are a **design reference built in HTML + Canvas** — a working
prototype that shows the intended look, color language, layout, and animation of each
sign. **They are not production firmware.** The real target is an LED panel driver
(e.g. an ESP32 / Raspberry Pi running `rpi-rgb-led-matrix`, WLED, or similar), where you
render into a framebuffer of the sizes above and push it to the panels.

Your task is to **recreate these layouts in the target environment** using its own
rendering primitives (framebuffer + BDF/bitmap font blitting + per-pixel color), following
the exact grids, colors, fonts, field order, and animation timings documented here. The
HTML prototype's own rendering pipeline (an offscreen Canvas rasterizer that samples web
fonts down to a lit-dot framebuffer) is a *simulation* of that — mirror the behavior, not
the implementation.

## Fidelity
**High-fidelity.** Colors, field order, font sizes, scroll speeds, and rotation cadence
are all final and exact. Reproduce them precisely. The one deliberate abstraction: the
prototype uses the web fonts **Silkscreen** (as a stand-in for the sign's BDF bitmap font)
and **Inter** (for hi-res type). In firmware, substitute the panel's real BDF font for
Silkscreen and any clean sans for Inter — keep the pixel sizes noted below.

---

## The rendering model (read first)
Everything is drawn into an RGB framebuffer of `physW × physH` and then lit as dots.
Two coordinate spaces:

- **Logical / BDF space** — used on smallsign and for the chunky text on scale-4 signs.
  A bitmap glyph is drawn at 1 mask-pixel → `scale` physical LEDs. Text is the
  **Silkscreen** substitute; in firmware use the panel's native BDF font.
- **Hi-res space** — scale-4 signs only. Glyphs are drawn 1 mask-pixel → 1 physical LED,
  using **Inter** at the noted px. This is how the big idents and small metric labels stay
  smooth.

Write pixels with a **max/brightest-wins** blend (not additive) so overlapping glows never
clip to white. Out-of-bounds writes are clipped. A scroll "window" is just a horizontal
clip range `[x0,x1)`.

### Semantic color palette (identical on every sign)
One hue per field type — never varies by sign or layout. RGB values are the LED drive
values (0–255):

| Field | Name | RGB | Hex |
|-------|------|-----|-----|
| Callsign / ident | `ident` | 255, 255, 255 | `#FFFFFF` |
| Aircraft type | `type` | 170, 90, 255 | `#AA5AFF` |
| Altitude | `alt` | 255, 180, 0 | `#FFB400` |
| Ground speed | `speed` | 60, 220, 60 | `#3CDC3C` |
| Track (heading) | `track` | 0, 220, 255 | `#00DCFF` |
| Distance / bearing | `dist` | 255, 80, 255 | `#FF50FF` |
| Climb cue ▲ | `climb` | 0, 255, 0 | `#00FF00` |
| Descent cue ▼ | `descend` | 255, 60, 60 | `#FF3C3C` |
| Level cue ▬ | `level` | 255, 180, 0 | `#FFB400` (= alt) |
| Field separator / labels | `label` | 70, 90, 130 | `#465A82` |
| Idle "no traffic" | `idle` | 0, 150, 200 | `#0096C8` |
| Live-refresh pulse | `live` | 0, 255, 0 | `#00FF00` |

### Vertical-rate cue
Computed from vertical rate `vr` (ft/min): `vr > 50` → **climb ▲** (green),
`vr < -50` → **descent ▼** (red), else **level ▬** (amber). BDF signs use 5×7 bitmap
up/down arrows and a 5×2 level bar; hi-res signs use the glyphs ▲ ▼ ▬.

### Airline tail-fin mark (trademark-safe branding)
Each flight leads with a small **swept vertical-stabiliser silhouette** in the airline's
brand palette — a brand cue, **not a copied logo**. It's derived from the alphabetic prefix
of the callsign:

| Prefix | Airline | Primary (c1) | Accent stripe (c2) |
|--------|---------|--------------|--------------------|
| `UA` | United | 40, 95, 210 (`#285FD2`) | 235, 240, 255 (`#EBF0FF`) |
| `DL` | Delta | 220, 40, 60 (`#DC283C`) | 30, 80, 150 (`#1E5096`) |
| `WN` | Southwest | 255, 190, 0 (`#FFBE00`) | 220, 45, 55 (`#DC2D37`) |
| `BA` | British Airways | 40, 95, 175 (`#285FAF`) | 220, 45, 55 (`#DC2D37`) |
| *(other)* | default | 150, 160, 175 (`#96A0AF`) | 90, 100, 115 (`#5A6473`) |

**Geometry**: for a fin of height `H` px, width `W = max(4, round(H·0.82))`. For each row
`r` in `0..H`, the left edge leans: `leftX = round(W·0.52·(1 − r/(H−1)))` (a triangle
leaning right, wider at top). Fill `leftX..W` with `c1`, except an accent band at rows
`round(H·0.5) .. round(H·0.5)+max(1,round(H·0.16))` which uses `c2`. This is trademark-safe
and legible down to 12 px tall — real logos are **not** used (they don't survive 16 LED rows
and are trademarked). Swap in real logo bitmaps only on the hi-res signs if artwork is later
provided.

---

## Screens / Views

### 1. smallsign — Single-line ticker
- **Grid**: 160 × 16 logical = 160 × 16 physical, `scale 1`, **BDF only** (no hi-res).
- **Purpose**: Show every field of every aircraft overhead in one endless horizontal
  crawl. No rotation, so it scales to any number of aircraft.
- **Layout**: One row, vertically centered (row height 12; `yTop = round((16 − 12)/2) = 2`).
  Content scrolls right → left continuously and loops seamlessly.
- **Per-flight token order** (left → right), all BDF 6×12 (`px 12`) except where noted:
  1. Airline tail-fin (H = 12) · gap 4
  2. Callsign — `ident` white · gap 5
  3. Separator dot (dim, `label`, mid-height, `scale`-sized) · gap 5
  4. Aircraft type — `type` violet · gap 5
  5. Separator dot · gap 5
  6. Vertical-rate arrow glyph (`climb`/`descend`/`level` color) · gap 2
  7. Altitude e.g. `34,000FT` — `alt` amber · gap 5
  8. Separator dot · gap 5
  9. Ground speed e.g. `460KT` — `speed` green · gap 5
  10. Separator dot · gap 5
  11. Track e.g. `247` + degree glyph `°` — `track` cyan · gap 5
  12. Separator dot · gap 5
  13. Distance e.g. `12KM NE` — `dist` magenta · gap 8
  14. **Between-flights** separator dot — brighter, `ident` white · gap 8
- **Scroll speed**: 26 physical px/sec × the global speed multiplier. Gap between the end
  of the full stream and its repeat: 0 (dots already delimit).
- **Separator dot**: a single `scale`-sized square, vertically centered, drawn at 0.7×
  brightness. Field dots use `label` color; the between-flights dot uses `ident` (white).

### 2. bigsign — Hi-res hero ident
- **Grid**: 64 × 16 logical = **256 × 64 physical**, `scale 4`, hi-res enabled.
- **Purpose**: One flight at a time, big and legible; rotate through the list.
- **Rotation**: hold each flight `4200 ms / speed`, then advance. `idx = floor(t / (4200/speed)) % count`.
- **Layout** (all physical px, origin top-left):
  - Airline tail-fin: drawn at `x 4, y 3`, `H 28`. Fin width `finW = max(4, round(28·0.82)) = 23`.
  - **Hero callsign**: Inter **700**, **26 px**, at `x = 4 + finW + 8`, `y 1`. Color `ident`.
  - **Second line** at `y 30`, same left x: airline name (Inter 700, 10 px, color = fin `c1`)
    then a 6 px gap, then aircraft type (Inter 600, 10 px, `type` violet).
  - **Metrics line** at `y 45`, starting `x 4`, Inter 600, 12 px, laid left→right with these gaps:
    - vertical-rate arrow ▲/▼/▬ (Inter 700, 10 px, at `y+1`) + 3 px
    - altitude `34,000FT` (`alt`) + 7 px
    - ground speed `460KT` (`speed`) + 7 px
    - track `247°` (`track`) + 7 px
    - distance `12KM NE` (`dist`)
  - **Paging dots** bottom-right: one 2·scale-spaced dot per flight; current = `ident` white,
    others = `label`. Positioned `x = physW − count·(2·scale) − 4`, `y = physH − scale·2 − 2`.

### 3. longboi — Dashboard row
- **Grid**: 128 × 16 logical = **512 × 64 physical**, `scale 4`, hi-res enabled, ~1 m wide.
- **Purpose**: The widescreen target and closest Flight Wall analog — hero ident on the
  left, labelled metric columns filling the width. One flight held, rotating.
- **Rotation**: hold `4800 ms / speed`. `idx = floor(t / (4800/speed)) % count`.
- **Layout** (physical px):
  - Airline tail-fin at `x 6, y 6`, `H 32` → `finW = max(4, round(32·0.82)) = 26`.
  - **Hero callsign**: Inter 700, **26 px**, at `hx = 6 + finW + 10`, `y 5`, color `ident`.
    Let `iw` = rendered width of the callsign.
  - **Under-ident line** at `y 40`, x = `hx`: airline name (Inter 700, 12 px, fin `c1`) +
    7 px + aircraft type (Inter 600, 12 px, `type`).
  - **Metric columns** — 4 equal columns starting at `x = max(hx + iw + 30, 190)`, each
    `colW = floor((physW − x − 16) / 4)` wide:
    | Column | Label (top) | Value |
    |--------|-------------|-------|
    | 1 | `ALT FT` | `34,000` (+ leading vertical-rate arrow, colored) |
    | 2 | `SPD KT` | `460` |
    | 3 | `TRK` | `247°` |
    | 4 | `DIST` | `12KM NE` |
    - Label: Inter 700, **10 px**, `label` color, at column x, `y 8`.
    - Value: Inter 700, **16 px**, semantic color, at `y 24`. Column 1's value is preceded
      by the vertical-rate arrow (Inter 700, 11 px, at `y 26`, climb/descent color) + 3 px.
  - **Paging dots** bottom-right (same rule as bigsign, offsets −6 / −3).

---

## Interactions & Behavior
- **Continuous ticker** (smallsign): offset = `(t_seconds · pxPerSec · speed) mod period`,
  where `period = contentWidth + gapBetween`. Draw the stream starting at `physW − offset`,
  repeating every `period` px until past the right edge. Seamless loop.
- **Rotation** (bigsign, longboi): hold one flight for its dwell time (4200 / 4800 ms ÷ speed),
  then advance with wraparound. Paging dots reflect the current index.
- **Live-refresh pulse**: a single `live`-green dot near the top-right blinks each ~10 s
  cycle — full brightness for the first 12 % of the cycle, then dim to 0.18. Represents the
  ADS-B data refresh.
- **Empty / "No Traffic" state** (0 aircraft): each sign idles. A slow vertical **radar-scan**
  column (`idle` color, ~0.10 brightness, brightest at vertical center) sweeps left→right on
  a 3200 ms loop, and centered text pulses (0.55–1.0 brightness, ~0.6 s sine):
  `"NO TRAFFIC"` on narrow signs, `"NO TRAFFIC OVERHEAD"` on wide ones (physical width ≥ 200).
- **Overflow**: on the scale-4 two-row style, a row that fits is drawn statically; a row wider
  than the sign auto-switches to scrolling. (Applies to alternate layouts; the three chosen
  layouts fit or scroll by design.)

### Prototype control bar (simulation only — not part of the sign firmware)
The HTML page has a sticky toolbar to demo states: **Traffic** (Busy 4 / Moderate 2 / Quiet 1 /
None 0), **Speed** multiplier (0.25×–2.5×), **Glow** toggle, **Pause/Play**. In firmware these
map to: number of aircraft in range, animation speed constant, an optional glow/bloom pass, and
a debug freeze. Reproduce only what your target needs.

## Animation loop / timing
- Driven at **~40 fps** via a fixed-interval tick (the prototype uses `setInterval(frame, 25)`
  because `requestAnimationFrame` is throttled when off-screen; firmware should use its own
  frame clock). Delta time is clamped to 250 ms to survive throttling. A global `clock`
  accumulates only while playing.
- All motion is a pure function of `clock`, so rendering is deterministic and resumable.
- The "20 FPS · SAMPLE FEED" label in the prototype is decorative.

## Rendering / glow pass (visual only)
The prototype draws each lit LED as a rounded square with a gap between cells (gap ≈ 16 % of
cell, corner radius ≈ 28 % of dot, capped 3 px) and, when cell ≥ 3 px and glow is on, an
additive soft bloom (~0.18 alpha, radius ≈ 0.9× dot) under the solid dots. This is purely to
make the on-screen mock look like real LEDs — physical panels produce their own glow, so it's
optional in firmware.

## State Management
- `clock` (ms, accumulates while playing) — the single source of truth for all animation.
- `speed` (float multiplier), `traffic` (int count of aircraft shown), `glow` (bool),
  `playing` (bool).
- Per-sign derived state: rotation `idx` and ticker `offset`, both computed from `clock`.
- **Data**: an array of flight objects. Each flight:
  `{ flt, type, alt, vr, gs, trk, dist, reg }` —
  callsign string, ICAO type code, altitude ft (int), vertical rate ft/min (int),
  ground speed kt (int), track ° (int 0–359), distance/bearing string, registration.
  In production, poll an ADS-B source (adsb.lol / airplanes.live) every ~10 s, filter to
  aircraft within range of the sign's location, and map into this shape.

## Design Tokens
- **Colors**: see the semantic palette and airline tables above (all as 0–255 RGB / hex).
- **BDF text size**: 6×12 (`px 12`) for smallsign body; 5×8 (`px 8`) for the alternate
  two-row styles.
- **Hi-res type (Inter)**: hero 26 px/700; airline name 10–12 px/700; type 10–12 px/600;
  metric values 16 px/700 (longboi) or 12 px/600 (bigsign); metric/column labels 10 px/700.
- **Vertical-rate thresholds**: ±50 ft/min.
- **Dwell times**: bigsign 4200 ms, longboi 4800 ms (÷ speed).
- **Ticker speed**: smallsign 26 px/s (× speed).
- **Refresh pulse**: 10 000 ms cycle, on for first 12 %.
- **Radar idle**: 3200 ms sweep; text pulse ~600 ms sine, 0.55–1.0 brightness.
- **Fonts**: Silkscreen (BDF substitute) → replace with panel BDF; Inter (hi-res).

## Assets
- **No image assets.** Airline tail-fins and all glyphs (arrows, degree sign, level bar,
  dots) are drawn procedurally from the geometry above.
- **Fonts**: Silkscreen + Inter via Google Fonts in the prototype. Firmware should use its
  panel's BDF font in place of Silkscreen and any clean sans in place of Inter.

## Files
- `Flight Tracker LED Layouts.html` — the reference page (chrome, control bar, three sign
  canvases, legend, spec chips).
- `app.js` — sample data, semantic palette, airline table, tail-fin geometry, the three
  layout functions (`smallB`, `bigA`, `longA`) plus alternates, and the animation loop.
- `led-engine.js` — the LED simulation engine: offscreen font rasterizer, framebuffer,
  max-blend pixel writer, BDF/hi-res blit, manual bitmap glyphs, and the lit-dot renderer.
  Use as a spec for the firmware's framebuffer + blit primitives.

> An earlier exploration with all 7 layout variants (2 smallsign, 2 bigsign, 3 longboi) is
> preserved in the project as `Flight Tracker LED Layouts v1 (7 variants).html` if you want to
> see the alternates that weren't chosen.
