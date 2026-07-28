# weather.forecast render polish — design

**Date:** 2026-07-27
**Status:** approved (brainstorm), pre-implementation
**Branch:** `weather-forecast` (folds into the open PR led-ticker-plugins#87)

## Motivation

Hardware validation of `weather.forecast` on longboi (512×64) and the reference
signs surfaced three rendering defects the demo-engine GIF previews did not:

1. **Low-res strip icons.** The hero draws the crisp 32×32 hires sprite, but the
   day-strip cells `blit_emoji_scaled` the **8×8 lowres** sprite integer-upscaled
   (2× bigsign / 3× longboi). Upscaled 8×8 reads as blocky next to the hero — the
   "low-res emoji" observed on the sign.
2. **Rough small text.** Day labels (px9/10), hi/lo temps (px11/12), `FEELS`
   (px8), and precip % (px9) all render through the **Inter TTF** at 8–12px, where
   stroke widths go lumpy and uneven.
3. **Short-feed left-squish.** A feed shorter than the layout's max day count
   (e.g. a WeatherAPI plan returning fewer forecast days) leaves the strip
   unbalanced — clustered content with dead space, most visibly on the smallsign
   (hard left-squish) and as an airy right-margin on the wide signs.

Evidence renders (icon crispness, Inter-vs-spleen, per-sign fill) were produced
during the brainstorm and drove the decisions below.

## Goals

- Strip icons as crisp as the hero, at every sign.
- Uniform, legible small text on the hires signs.
- A balanced strip at any day count, on every sign.
- No regression to the smallsign (already crisp: BDF text + 8×8 icons are correct
  at 160×16).

## Non-goals

- No change to the hero's big temperature or the location label — Inter looks
  correct large; both stay Inter.
- No change to smallsign icons/text (only its fill).
- No new core API — reuse the public surface (`draw_emoji_at`, `resolve_font`,
  `get_pixel` readback, `ScaledCanvas`).
- No change to the condition-code → kind mapping, data layer, or `demo` fixture.

## Design

### 1. Strip icons → downscaled hires (unified slug)

New helper in `paint.py`:

```
blit_hires_downscaled(real, slug, x, y, target)   # target = 16 (big) | 24 (long)
```

- Rasterize the 32×32 hires sprite **once per slug** into an `(r,g,b)` grid via an
  offscreen `HeadlessBackend(32,32)` wrapped in `ScaledCanvas(scale=1)` +
  `get_pixel` readback — the documented readback pattern already used by
  `_emoji_pixels` for the lowres cache. `@functools.lru_cache` the grid.
- **Box-area downscale** 32→`target` (average the source pixels each target pixel
  covers). Non-black results only are stamped, per-pixel bounds-clipped (same
  clipping contract as `blit_emoji_scaled`). Averaging black into edge pixels
  yields a soft anti-aliased edge, which reads well on the panel; if hardware
  shows a dim halo, switch to coverage-weighted averaging (documented follow-up,
  not expected to be needed).
- `_strip_cell` calls `blit_hires_downscaled(real, KIND_SLUGS[kind][1], cx-target/2,
  icon_y, target)` — **the hero's hires slug** (`[1]`), not the lowres `[0]`. This
  unifies the icon language: overcast / patchy-rain get their richer pack sprites
  (`sun_behind_large_cloud`, `sun_behind_rain_cloud`) in the strip too, matching
  the hero.
- `blit_emoji_scaled` / `_emoji_pixels` **stay** — the smallsign strip keeps the
  8×8 lowres path (no ScaledCanvas hires there; 8×8 is right at 160×16).

### 2. Small text → spleen (hires signs only)

Spleen (`spleen-6x12`, bundled) is a bitmap pixel font: crisp and uniform at
small sizes, monospace 6px advance. Measured metrics at size 12, threshold 80:
**ascent 9 / descent 3; glyph ink-top lands exactly at the draw `y_top`** — so no
`cap_top` conversion is needed for spleen (unlike Inter). Advance is exactly
`6·len(text)` (exact pins are the project convention for pixel fonts).

New helpers in `paint.py`:

```
SPLEEN = resolve_font("spleen-6x12", 12, 80)      # module-level, cached by resolve_font
spleen(shim, text, x, y_top, rgb) -> advance       # y_top IS the visual top
spleen_center(shim, text, cx, y_top, rgb)
spleen_segs(shim, segs, cx, y_top)                 # multi-color, one centered run
spleen_width(text) -> 6 * len(text)                # exact monospace
```

Field routing:

| Field | Sign(s) | Font (was → now) |
|---|---|---|
| hero big temp | big, long | Inter 27/28 — **unchanged** |
| location | big, long | Inter 9/11 — **unchanged** |
| hero hi/lo | big, long | Inter 11 → **spleen** |
| hero `FEELS` | big, long | Inter 8 → **spleen** |
| strip day label | big, long | Inter 9/10 → **spleen** |
| strip temps | big, long | Inter 12 → **spleen** |
| strip precip % | long | Inter 9 → **spleen** |
| everything | small | BDF `FONT_SMALL` — **unchanged** |

`cap_top` remains, used only by the surviving Inter callers (temp, location).

**Retuned geometry** (12px spleen cell vs the old 8–12px). Verified to fit 64px in
the brainstorm prototype:

- **longboi strip** (`_LONG_GEO`): `day_y=1`, `icon` 24 @ `icon_y=13`, `temp_y=38`
  (horizontal hi/lo segs), `pop_y=51`. day(1–12) · icon(13–36) · temps(38–49) ·
  precip(51–62).
- **bigsign strip** (`_BIG_GEO`): `day_y=2`, `icon` 16 @ `icon_y=15`, stacked
  `temp_y=33` / `+12`. Fits with headroom.
- **longboi hero**: hi/lo spleen centered in the temp column near y≈41; `FEELS`
  spleen at y≈52. bigsign hero analogous.

Exact final y-values are pinned during TDD against the fit constraints above.

### 3. Short-feed fill → center-group (everywhere)

Replace the "widen columns to fill + center content in each" behavior with a
single **center-the-group** rule shared by all three strip renderers:

- Lay out `n` cells at the layout's **natural design pitch** (the full-count
  column width — longboi 344/6, bigsign 134/4, smallsign fixed 53).
- Center the resulting `n·pitch` block within the available span (equal margins
  both sides). `n==1` → centered single cell.
- Smallsign's dotted separators are placed at the midpoints **between** the
  centered cells (never trailing the last cell).

This is symmetric at any `n` (fixes the left-squish) and consistent across signs.
Chosen over edge-to-edge justify for simplicity and because justify stranded the
smallsign separators in the gap and looked broken at 2–3 days. Accepted tradeoff:
with few days the last cell does not reach the panel edge (symmetric margins
instead).

A shared helper computes cell x-positions:

```
center_group_x(x0, x1, n, pitch) -> list[int]     # left edge of each cell
```

used by `render_strip_small`, and by `_strip` (hires) with the geometry's pitch.

## Testing impact

The suite's exact-pinned assertions **will change by design** — this is a
deliberate visual retune, re-pinned to the new geometry:

- **Retune:** lowres-blit pins, divider/day pins, hero `y` pins, shape-level hires
  assertions → new positions.
- **New pins:**
  - strip cell draws the **hires** slug (`KIND_SLUGS[kind][1]`), not lowres —
    guards the icon-language unification.
  - `blit_hires_downscaled` output dims/box-averages (a target pixel is the mean
    of its 32-space footprint) — a small deterministic fixture.
  - spleen advance is `6·len` and ink-top == `y_top` (locks the no-`cap_top`
    assumption).
  - center-group: `n < max` centers symmetrically (equal left/right margin);
    `n==1` centered; separators between cells only.
  - longboi vertical-fit guard: precip row bottom ≤ 63 (the tight-budget
    tripwire).
- `ruff check` + `ruff format --check` clean; `pyright plugins/weather/src` 0
  errors.

## Fallout to own

- Re-render the three demo-mode preview GIFs; update the PR body's images.
- Update `plugins/weather/CLAUDE.md` forecast invariants: spleen small-text
  (no-`cap_top`, 6px monospace), unified hires-downscale strip icons, center-group
  fill.
- The smoke configs (`config.forecast_smoketest.{bigsign,longboi}.toml`) need no
  change (demo mode covers it); re-boot-smoke them.
- Note in the README "Divergences from the design handoff" that strip icons are
  now hires-downscaled and small text is spleen (further, intentional divergence
  from the handoff's Inter/procedural glyphs).

## Validation

- Headless render of all three signs at full + short (5/3/2/1-day) feeds; eyeball
  crispness, fit, and balance.
- Boot-smoke both smoke configs through `run()` (frames non-blank, no raise).
- On-sign check per the "Test on the sign" flow before merge (longboi is the
  binding case — tight vertical budget + widest strip).
