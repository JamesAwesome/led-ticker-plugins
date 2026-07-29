# Handoff: Weather — Multi-Day Forecast

## Overview
A new **multi-day forecast** mode for the LED-Ticker weather plugin, rendered in the physical-LED dot-matrix language of the existing product (flight tracker / stock ticker family). It is authored three times, once per physical sign, and **scales the day count to the sign's width**:

- **smallsign** — 160 × 16 physical pixels (logical 160 × 16, scale 1, 5 px cells) · **BDF text only** · **3-day** strip
- **bigsign** — 256 × 64 physical pixels (logical 64 × 16, scale 4, 4 px cells) · hi-res text · **5-day** (today hero + 4-day strip)
- **longboi** — 512 × 64 physical pixels (logical 128 × 16, scale 4, 3 px cells) · hi-res text · **7-day** (today hero + 6-day strip)

The signs are pure black with lit "dots"; content is drawn to a framebuffer, not DOM. Conditions are **hand-built LED glyphs** (drawn procedurally with circles / lines, no image assets). The palette is semantic: **hi temp warm-orange, lo temp cool-blue**, sun amber, rain/precip cyan, clouds slate-gray.

## About the Design Files
The files in this bundle are **design references created in HTML** — a working prototype showing the intended look and data mapping. They are **not** production code to ship verbatim. The task is to **recreate this mode in the target codebase** (the real LED sign renderer / firmware / display service and its weather data pipeline), following that codebase's established patterns.

The prototype reuses the product's own LED engine (`LED.Sign`, bundled here as `led-engine-bundle.js`) so dot geometry, glow, and text rasterization match the real signs exactly. If the production renderer exposes the same primitives (`px`, `blit`, `bdf`, `hires`, `hiresMask`, `render`), the draw logic ports almost 1:1. If not, treat the draw functions as an exact spec for pixel positions, colors, and layout.

## Fidelity
**High-fidelity.** Colors, pixel positions, font sizes, glyph shapes, and data mapping are locked. Recreate pixel-for-pixel. The only intentionally-placeholder part is the **sample data** (see Data Sources) — wire it to the live weather feed. The sample is a fixed summer week for `BOSTON`; night-time glyph variants (`clear`, `partlyNight`) exist in the icon set but are not exercised by the daytime sample.

## The LED engine (dependency)
`led-engine-bundle.js` exposes a global `window.LED` after load. Key API used here:

- `new LED.Sign(canvasEl, {logW, logH, scale, cell, glow})` — creates a sign bound to a `<canvas>`. Physical size = `logW*scale × logH*scale`; `cell` = screen px per physical dot.
- `sign.px(x, y, rgb, brightness)` — light one physical pixel. **`rgb` is 0–1 per channel**, not 0–255. `brightness` 0–1. Writes are additive-max.
- `sign.hires(text, physX, physY, rgb, px, weight, opts)` — rasterize + blit hi-res (Inter) text; returns pixel width. **bigsign/longboi only.**
- `sign.hiresMask(text, px, weight)` → `{w,h,alpha}` — rasterize only (measure / cache).
- `sign.bdf(text, logX, logY, rgb, px, opts)` — crisp BDF (Silkscreen) text at **logical** coords, expanded by `scale`. **smallsign uses this** (no hi-res on that panel).
- `sign.blit(mask, physX, physY, rgb, brightness, opts)` — stamp a mask; `opts.x0/x1/y0/y1` clip to a physical band.
- `sign.clear()` / `sign.render()` — per frame: clear framebuffer, draw, flush.
- `sign.glow` (bool) — LED bloom toggle.

> **Critical gotcha:** the engine multiplies stored colors by 255 at render time, so **all colors must be stored 0–1**. The prototype keeps its palette 0–255 for readability and normalizes once in `boot()` (`x/255`). If you copy the palette, either pre-divide or replicate that step.

## Layouts (per sign)

Each sign has one draw fn, signature `fn(sign, ctx)`. Coordinates below are **physical pixels** unless noted.

### smallsign → `weatherSmall` (160×16, BDF)
Too short for a hero, so it runs a clean **3-day strip**: today + next two days. Three 53 px columns, each = a **14 px condition glyph** on the left, then a text block: day label (amber BDF px7) over `hi/lo` (white BDF px7, degree-less). Thin dotted separators between columns. Day labels use `TDY` for today.

### bigsign → `weatherBig` (256×64) — today hero + 4-day strip
- **Hero, left (x4–108):** location label (`LOC`, dim, px9, top-left) sitting **above** a big current-temp number (`78°`, white, px27) — the temp is dropped low enough that the city always clears its full height. Below: `hi°/lo°` (warm/cool, px11, centered) then `FEELS xx°` (cyan, px8). The condition glyph (30 px) sits at far left.
- **Divider:** dotted vertical rule at x112.
- **Strip, right (x118–252):** four day columns, each = day label (amber px9), 18 px glyph, then **hi over lo stacked** (warm px12 / cool px12) — stacked because the columns are too narrow for a horizontal `hi/lo`.

### longboi → `weatherLong` (512×64) — expanded hero + 6-day strip
- **Hero, left (x6–156):** location **left-justified** at top (px11, truncated with an ellipsis via `fitText` if it exceeds the hero width). Big current temp (`78°`, white, px28) pushed **right** (x70) into the open horizontal space, with `hi°/lo°` (px11, centered under the temp) and `FEELS xx°` (cyan, px8) below, with a deliberate gap above FEELS.
- **Divider:** dotted vertical rule at x156.
- **Strip, right (x162–506):** six day columns (~57 px each), each = day label (amber px10), 22 px glyph, horizontal `hi/lo` (px12), and **precip %** (px9; cyan when ≥50%, dim otherwise).

## Condition glyphs (`drawIcon(sign, kind, x, y, s)`)
All glyphs are drawn procedurally into a **square box** at `(x, y)` sized `s` px, so they scale cleanly to each sign (14 px on smallsign, 18–30 px on the hi-res signs). Built from `disc`, `rect`, `line`, `fatline` primitives. Supported `kind` values:

| kind | drawing |
| --- | --- |
| `sunny` | amber disc + 8 rays |
| `clear` | crescent moon (pale blue) — night clear |
| `partly` | small sun upper-left + slate cloud lower-right |
| `partlyNight` | crescent moon + cloud — night partly-cloudy |
| `cloudy` | single light-slate cloud |
| `overcast` | larger dark-slate cloud |
| `rain` | cloud + 3 cyan diagonal streaks |
| `thunder` | cloud + amber lightning bolt |
| `snow` | cloud + white flake crosses |
| `fog` | dim cloud + 2 horizontal fog lines |

Because framebuffer writes are additive-max (no erase), overlapping objects (sun peeking past a cloud in `partly`) are offset so they read as two shapes rather than compositing.

## Interactions & Behavior
- **Static content** — the forecast doesn't rotate or scroll (all days fit), so there is no clock/animation. A light `setInterval` (~15 FPS) simply re-renders on control changes; production can render once and only redraw on data / control updates.
- **Controls (prototype only — not part of the shipped widget):** GLOW toggle, and a **°F / °C** unit toggle (`TF()` converts and rounds; temps stored in °F).
- **Performance:** hi-res text rasterization is memoized per sign (`cacheRaster` wraps `hiresMask`/`hires` with a `{text|px|weight}` cache); an **IntersectionObserver** pauses drawing for off-screen signs.
- **Fonts:** `Silkscreen` (smallsign BDF + UI chrome) and `Inter` (hi-res sign text). The loop waits on `document.fonts.ready` before booting so text measures correctly.

## Data Sources — WeatherAPI.com (`https://api.weatherapi.com/v1/`)
All sample data in the prototype is **fictional placeholder** exercising the layouts. Endpoint:

```
GET /v1/forecast.json?key=KEY&q=<location>&days=7&aqi=no&alerts=no
```

Field mapping (also inlined as comments above the data block in the `.dc.html`):

- `LOC` = `location.name`
- **Current (hero):**
  - `tempF` = `current.temp_f` · `feelsF` = `current.feelslike_f`
  - `windMph` = `current.wind_mph` · `hum` = `current.humidity`
  - `kind` = `condKind(current.condition.code, current.is_day)`
- **Per day (`forecast.forecastday[]`):**
  - day label from `date` (weekday abbrev)
  - `hiF` = `day.maxtemp_f` · `loF` = `day.mintemp_f`
  - `pop` (precip %) = `day.daily_chance_of_rain`
  - `kind` = `condKind(day.condition.code, 1)`
- **`condKind(code, isDay)` — WeatherAPI condition code → glyph:**
  - `1000` → `sunny` (day) / `clear` (night)
  - `1003` → `partly` (day) / `partlyNight` (night)
  - `1006` → `cloudy` · `1009` → `overcast`
  - `1030 / 1135 / 1147` → `fog`
  - `1063 / 1150–1201 / 1240–1246` → `rain`
  - `1066 / 1114 / 1210–1225 / 1255–1258` → `snow`
  - `1087 / 1273–1282` → `thunder`
- **Units:** the prototype stores °F and converts to °C on toggle; wire the toggle (or a config flag) to the display's locale.

## Design Tokens
Semantic palette (shown 0–255 for readability — **store as 0–1**, i.e. divide by 255):

| Token   | RGB (0–255)   | Use |
| ------- | ------------- | --- |
| ident   | 255,255,255   | Current temp / neutral text |
| label   | 70,90,130     | Dim labels, dividers, low precip, hi/lo slash |
| amber   | 255,180,0     | Day labels |
| hi      | 255,148,36    | High temp (warm) |
| lo      | 70,180,255    | Low temp (cool) |
| cyan    | 0,200,255     | FEELS line, precip ≥50% |
| sun     | 255,192,32    | Sun disc + rays |
| moon    | 212,224,255   | Crescent moon (night) |
| cloudLt | 168,182,208   | Cloud (default) |
| cloudDk | 92,108,146    | Overcast cloud |
| fog     | 128,144,174   | Fog cloud + lines |
| rain    | 0,196,255     | Rain streaks |
| snow    | 224,236,255   | Snow flakes |
| bolt    | 255,208,40    | Lightning bolt |

**Sign geometry:** smallsign `{logW:160, logH:16, scale:1, cell:5}` → 160×16; bigsign `{logW:64, logH:16, scale:4, cell:4}` → 256×64; longboi `{logW:128, logH:16, scale:4, cell:3}` → 512×64.

**Prototype page chrome (HTML around the signs, not on the sign):** bg `#07090d`, text `#e7ecf3`, muted `#8593a8`/`#9aa7ba`, hairlines `rgba(255,255,255,.06–.08)`; fonts Inter + Silkscreen; sign bezel is `#000` with `border-radius:12px` and `inset 0 0 40px rgba(0,0,0,.7)`.

## Assets
No external image assets — every glyph is drawn procedurally on the framebuffer. Fonts: **Silkscreen** and **Inter** (Google Fonts). Dependency: **`led-engine-bundle.js`** (`window.LED`).

## Files
- `Weather Forecast.dc.html` — the full prototype: HTML gallery page + logic class with the sample data, drawing primitives, glyph functions, and the three per-sign draw functions. Data-source field mappings are inlined as comments above the data block. This is the authoritative spec.
- `led-engine-bundle.js` — the LED renderer (`window.LED`) used by the prototype; matches the real signs' dot geometry, glow, and text rasterization.

> Note: the prototype is authored as a Design Component (`.dc.html`) — the `<x-dc>` wrapper and `support.js` reference are the design-tool runtime and are **not** part of the widget. Only the logic class (draw functions + data) and the LED engine calls are relevant to production.
