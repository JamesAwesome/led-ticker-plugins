# weather.forecast — Multi-Day Forecast Widget

**Date:** 2026-07-22
**Repo:** led-ticker-plugins (`plugins/weather/`)
**Design handoff:** `plugins/weather/design/` (committed verbatim from `weather-handoff.zip`; normative)

## Summary

A new `weather.forecast` widget in the weather plugin: a **held multi-day forecast card**
rendered per-sign in the dot-matrix design language of the flight tracker family. Layout is
auto-detected from the canvas (baseball/flight `resolve_layout` pattern):

- **smallsign** (160×16, scale 1) — 3-day BDF strip: icon + day label + `hi/lo` per column
- **bigsign** (256×64, scale 4) — today hero (location, current temp, hi/lo, FEELS) + 4-day strip
- **longboi** (512×64, scale 4) — expanded hero + 6-day strip with precip %

`weather.current` is untouched. Condition icons come from the **packaged emoji** (curated
weather sprites + emoji-pack sprites on hi-res signs), not the handoff's procedural glyphs —
see Divergences.

## Decisions made during brainstorming

| Question | Decision |
| --- | --- |
| Widget shape | New `weather.forecast` widget beside `weather.current` (same plugin package) |
| Short forecast data (free-tier keys return 3 days) | Degrade gracefully: render the columns the feed provides, widen to fill, INFO log |
| Icons | No new glyphs. Packaged emoji: curated 8 everywhere; pack sprites add fidelity on hi-res signs (hero slot only) |
| Structure | Flight-pattern modules + one shared parameterized strip cell (the handoff's own factoring) |

## Architecture

New modules in `plugins/weather/src/led_ticker_weather/`; registration in `__init__.py`
adds `api.widget("forecast")(ForecastWidget)` → config `type = "weather.forecast"`.

```
forecast.py           # ForecastWidget (attrs + FrameAwareBase) + resolve_forecast_layout
                      #   + validate_config / validate_config_warnings + start()/update()
forecast_data.py      # fetch_forecast (/v1/forecast.json), condKind(code, is_day),
                      #   kind→slug tables, CurrentConditions / DayForecast models
palette.py            # handoff semantic tokens as Color constants
paint.py              # physical-pixel helpers: hires() (Inter via resolve_font, cap-top y),
                      #   js_round, dotted vdivider, blit_emoji_scaled
forecast_layouts.py   # render_strip_small (BDF) + render_hero_big + render_hero_long
                      #   + shared _strip_cell(geo) + _BIG_GEO/_LONG_GEO geometry tables
design/               # the handoff, committed verbatim (README.md, .dc.html, led-engine bundle)
```

All modules import core symbols from `led_ticker.plugin` only (import-purity contract).
No `from __future__ import annotations` (PEP 649 rule). All handoff-ported math goes through
`js_round(v) = floor(v + 0.5)` — never bare `round()`.

## Layout resolution

`resolve_forecast_layout(cfg_layout, scale, phys_w) -> str` — pure, stateless, resolved
fresh on every `draw()` tick (hot-reloads / canvas swaps always re-resolve).

`VALID_LAYOUTS = ("auto", "strip", "big", "long")`

| Input | Result |
| --- | --- |
| any, `scale <= 1` | `"strip"` (hi-res layouts impossible; explicit `big`/`long` coerced, advisory warning at validate) |
| `"auto"`, scale > 1, `phys_w < 400` | `"big"` |
| `"auto"`, scale > 1, `phys_w >= 400` | `"long"` |
| explicit `"long"`, scale > 1, `phys_w < 400` | `"big"` (width-fit degrade — hardcoded anchors would clip off-panel) |
| explicit `"strip"`, any scale | honored (draws at logical coords through the wrapper) |
| explicit `"big"`, scale > 1 | honored |

## Data

- **Endpoint:** `GET https://api.weatherapi.com/v1/forecast.json?key=KEY&q=<location>&days=7&aqi=no&alerts=no`,
  polled through the **engine's shared aiohttp session** (never closed or reconfigured;
  per-request `ClientTimeout`). `WEATHERAPI_KEY` from env, same as `weather.current`.
- **Models:**
  - `CurrentConditions`: `temp_f = current.temp_f`, `feels_f = current.feelslike_f`,
    `kind = condKind(current.condition.code, current.is_day)`, `hi_f`/`lo_f` from
    `forecast.forecastday[0].day`.
  - `DayForecast` (one per `forecast.forecastday[1:]` — tomorrow onward): weekday abbrev
    from `date`, `hi_f = day.maxtemp_f`, `lo_f = day.mintemp_f`,
    `pop = day.daily_chance_of_rain`, `kind = condKind(day.condition.code, 1)`.
  - `location_name = location.name` (the hero's `LOC` label).
- **Units:** temps stored °F; `units = "imperial" | "metric"` converts at draw
  (handoff `TF()`: `round((f-32)*5/9)` for metric).
- **Degrade on short feed:** the strip renders `min(layout_days, len(days))` columns using
  the handoff's own `cw = strip_width / n` with the **actual** n, so a short feed widens
  columns to fill the strip. One INFO log when short. A 3-day key on longboi shows
  hero + 2-day strip.
- **Update cadence:** `update_interval` config, default 10800 s (3 h, matches
  `weather.current`), via `run_monitor_loop` with its standard backoff.
- **Visibility:** `should_display() -> False` until the first successful fetch — an empty
  card never enters the rotation.

## Icons

`condKind(code, is_day)` ports the handoff's WeatherAPI condition-code table verbatim:
1000 sunny/clear · 1003 partly/partlyNight · 1006 cloudy · 1009 overcast ·
1030/1135/1147 fog · 1063/1150–1201/1240–1246 rain · 1066/1114/1210–1225/1255–1258 snow ·
1087/1273–1282 thunder. `is_day = 0` swaps sunny→clear, partly→partlyNight (hero only;
strip days always resolve with `is_day = 1`).

Kinds map to packaged-emoji slugs via one table with a lowres and a hires column:

| kind | lowres (curated 8×8) | hires (32×32) |
| --- | --- | --- |
| sunny | `sun` | `sun` |
| clear (night) | `moon` | `moon` |
| partly | `partly_cloudy` | `partly_cloudy` |
| partlyNight | `partly_cloudy` | `moon` |
| cloudy | `cloud` | `cloud` |
| overcast | `cloud` | `sun_behind_large_cloud` **(pack)** |
| rain — patchy codes (1063, 1150–1183, 1240) | `rain` | `sun_behind_rain_cloud` **(pack)** |
| rain — solid codes | `rain` | `rain` |
| thunder | `thunder` | `thunder` |
| snow | `snow` | `snow` |
| fog | `fog` | `fog` |

Placement rules:

- **Hero icon** (bigsign 30px slot, longboi 40px slot): the 32×32 hires sprite (curated or
  pack), centered in the handoff's slot box.
- **Strip icons**: always the curated **lowres** sprite, integer-blitted at 2× on bigsign
  (16px ≈ handoff's 18) and 3× on longboi (24px ≈ 22) via `paint.blit_emoji_scaled` —
  pack sprites never appear in strips (fixed 32×32 doesn't fit the strip bands).
- **smallsign**: `draw_emoji_at` directly (8×8 at logical coords) in the handoff's icon slot.

`blit_emoji_scaled(real, slug, x, y, k)`: offscreen-rasterize the 8×8 sprite once via
`draw_emoji_at` on a `HeadlessBackend` canvas, read back with `HeadlessCanvas.get_pixel`
(the one documented supported readback — baseball `_mask.py` precedent), `lru_cache` per
slug, stamp k×k blocks with `SetPixel`. **Zero new core API.**

## Renderers (`forecast_layouts.py`)

All coordinates, sizes, and colors are ported from the handoff's draw functions
(`weatherSmall` / `weatherBig` / `weatherLong` in `design/Weather Forecast.dc.html`) with
`js_round`. Hires text via `paint.hires()`: `resolve_font("Inter-Bold" | "Inter-Regular",
size)` (handoff weight 700 → Bold, 600 → Regular), physical coords, cap-top y conversion
(the baseball board renderer's hardware-validated formula).

- **`render_strip_small`** (logical coords, BDF): three 53px columns from x=2 — icon at the
  handoff slot, day label (amber) at y1, `hi/lo` (white, degree-less) at y9, `TDY` for
  today's column, dotted separators (`px` every 2 rows at column edge). Font: the closest
  bundled BDF to the handoff's px7 Silkscreen (`FONT_SMALL` family) — metric divergence
  documented if cell heights differ.
- **`render_hero_big`** (256×64 physical): location label (dim `label` color, px9) at (6,2);
  hero icon box (4,13,30); current temp (white px27) at (44,13); centered `hi°/lo°` segs
  (warm/`label` slash/cool, px11) in the (44, w=60) band at y41; `FEELS xx°` (cyan px8) at
  (44,53); dotted vdivider at x112 (y 6–58); 4-day strip x118–252, **stacked** hi over lo
  (px12, lineH 12), day label px9 at y2, 16px icon at y13, temps at y37.
- **`render_hero_long`** (512×64 physical): location `fit_text`-ellipsized to 148px (px11)
  at (6,2); hero icon box (4,15,40); temp (px28) at (70,14); centered `hi°/lo°` (px11) in
  (70, w=80) at y43; `FEELS xx°` (cyan px8) at (70,56); vdivider at x156; 6-day strip
  x162–506, horizontal `hi/lo` segs (px12) at y40, day label px10, 22px slot (24px icon)
  at y13, **precip %** (px9) at y52 — cyan when `pop >= 50`, `label` dim otherwise.
- **`_strip_cell(sign, x, w, cell, geo)`** + per-sign `_BIG_GEO` / `_LONG_GEO` tables carry
  the handoff's `stripCell` options dicts verbatim (dayY/dayPx/iconS/iconY/tempY/tempPx/
  stack/lineH/popY/popPx) so the two hires strips cannot drift apart.

`palette.py` tokens (0–255 `Color` constants; the engine takes 0–255 — the handoff's 0–1
normalization is prototype-engine-specific and does NOT port): `ident` 255,255,255 ·
`label` 70,90,130 · `amber` 255,180,0 · `hi` 255,148,36 · `lo` 70,180,255 · `cyan` 0,200,255.
Glyph-drawing tokens (sun/moon/cloud/rain/snow/bolt colors) don't port — icon colors come
from the emoji sprites themselves.

## Widget behavior & config

- **Held card on every sign:** `draw()` returns `cursor = canvas.width` — the wrapper's
  **logical** width (held-cursor contract; returning `real.width` triggers the phantom
  scroll bug). Static content: no internal clock, no dwell rotation, no settle hook.
- **`bg_color` declared only** — the engine paints it; `draw()` never `Fill()`s.
- **Config surface** (no font/color/day-count knobs — the design pins the look):

```toml
[[section.widget]]
type = "weather.forecast"
location = "Boston"          # required unless demo = true; same query forms as weather.current
layout = "auto"              # auto | strip | big | long
units = "imperial"           # imperial | metric
update_interval = 10800      # seconds
demo = false                 # true → handoff's fixed BOSTON sample week, zero network
```

- **Demo mode** (flight precedent): seeds the handoff's sample week (`CUR` + 6-day `FC`,
  BOSTON) in construction; `start()` skips the initial fetch and the monitor loop. Used by
  GIF previews and layout tests.

## Error handling

- Initial fetch failure → logged (`exception`), background retry via `run_monitor_loop`
  backoff; `should_display()` keeps the widget out of rotation until data exists.
- Missing `WEATHERAPI_KEY` / API error payloads → `ValueError` (existing `fetch_current`
  convention), caught by the monitor loop.
- `validate_config` (classmethod, returns `list[str]`, never raises): `layout` in
  `VALID_LAYOUTS`; `units` in `("imperial", "metric")`; `location` present unless
  `demo = true`; `update_interval` positive number, bool excluded.
- `validate_config_warnings`: explicit `big`/`long` on a scale-1 sign → advisory
  ("will render as strip").

## Testing

Mirrors the flight plugin's suite shape (`plugins/weather/tests/`):

- `test_forecast_data.py` — per-code `condKind` tripwires (every code band, both `is_day`
  values); payload parsing; short-feed degrade; **slug-existence tripwire**: every lowres
  slug in the mapping table exists in the lowres+hires curated registries, every pack slug
  passes `emoji_pack.has_slug` (extends the existing `test_weather.py` pattern).
- `test_resolve_forecast_layout.py` — the full resolution table above, including both
  degrade guards.
- `test_forecast_layouts.py` — hires text asserted **shape-level only** (pixels of color C
  in region R; never exact-pinned — freetype varies across macOS/Linux). Lowres icon blits,
  dotted dividers, and `blit_emoji_scaled` output ARE exact-pinned (pure SetPixel math).
  Column-collision guards with worst-case content (`-99/-99`, `100%`) per sign.
- `test_forecast_widget.py` — held-cursor contract on smallsign/bigsign/longboi fixtures;
  `should_display` before/after data; shared-session handling (never closed); demo mode
  renders without network; layout hot-reload re-resolution.
- `test_import_purity.py` / `test_smoke.py` — extend automatically (AST scan covers new
  modules; smoke asserts `weather.forecast` registers).

Implementation-phase validation: GIF renders of all three signs (demo mode) reviewed
before commit — pixel-art iteration workflow.

## Divergences from the handoff (documented in plugins/weather/README.md, flight-style)

1. **Icons are packaged emoji, not procedural glyphs.** The handoff's `drawIcon` primitives
   (disc/rect/line glyph set) are not ported; curated weather sprites + hero-slot pack
   sprites replace them. Consequences: icon boxes snap to sprite-supported sizes (8/16/24/32
   vs the handoff's 14/18/22/30/40); the overcast-vs-cloudy distinction survives only on
   hi-res signs; partlyNight approximates (`partly_cloudy` lowres / `moon` hires).
2. **smallsign text font** is the nearest bundled BDF, not Silkscreen px7 (metrics may
   differ by ±1 row).
3. **No °F/°C runtime toggle or GLOW control** — prototype chrome; units come from config,
   glow is hardware.
4. **No 15 FPS re-render loop** — the engine's held-card cadence applies; content is static
   per data update.

## Out of scope

- `weather.current` changes of any kind (it already speaks the same emoji icon language).
- A `WeatherSource`-style token source for forecast fields.
- Day-count / font / color config knobs.
- Docs-site pages (plugin README is the user-facing surface for plugins).
