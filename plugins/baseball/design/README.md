# Handoff: Baseball LED Widgets

## Overview
Four ballpark data widgets — **Scores, Standings, Promotions, Statcast, Attendance** — rendered in the physical-LED dot-matrix language of the existing LED-Ticker product (flight tracker / stock ticker family). Every widget is authored twice, once for each physical sign:

- **bigsign** — 256 × 64 physical pixels (logical 64 × 16 cells, 4×4 px cells)
- **longboi** — 512 × 64 physical pixels (logical 128 × 16 cells, 3×3 px cells)

The signs are pure black with lit "dots"; content is drawn as a framebuffer, not DOM. Each view uses **one semantic hue per data field** so the board reads at a glance, brand-colored team chips, and either a held card or a live crawl depending on the sign width.

## About the Design Files
The files in this bundle are **design references created in HTML** — a working prototype showing the intended look, motion, and data mapping. They are **not** production code to ship verbatim. The task is to **recreate these widgets in the target codebase's environment** (the real LED sign renderer / firmware / display service and its data pipeline), following that codebase's established patterns for talking to the sign hardware and the MLB data feed.

The prototype happens to reuse the product's own LED engine (`LED.Sign`, bundled here as `led-engine-bundle.js`) so the dot geometry, glow, and text rasterization match the real signs exactly. If the production renderer exposes the same primitives (`px`, `blit`, `hires`, `hiresMask`, `render`), the per-widget draw logic can port almost 1:1. If not, treat the draw functions as an exact spec for pixel positions, colors, and layout.

## Fidelity
**High-fidelity.** Final colors, pixel positions, font sizes, motion timing, and data mapping are all locked. Recreate pixel-for-pixel. The only intentionally-placeholder part is the **sample data** (see Data Sources) — wire it to the live MLB feed.

## The LED engine (dependency)
`led-engine-bundle.js` exposes a global `window.LED` after load. Key API used by the widgets:

- `new LED.Sign(canvasEl, {logW, logH, scale, cell, glow})` — creates a sign bound to a `<canvas>`. `logW/logH` are logical cells; physical size = `logW*cell*... ` (the prototype uses `logW:64,logH:16,cell:4` for bigsign → 256×64, and `logW:128,cell:3` for longboi → 512×64).
- `sign.px(x, y, rgb, brightness)` — light one physical pixel. **`rgb` is 0–1 per channel**, not 0–255. `brightness` 0–1.
- `sign.blit(mask, physX, physY, rgb, brightness, opts)` — stamp a rasterized text mask. `opts.x0/x1` clip to a physical column band (used for scroll clipping).
- `sign.hires(text, physX, physY, rgb, px, weight, opts)` — rasterize + blit text in one call; returns pixel width. `px` = font size, `weight` = "600"/"700".
- `sign.hiresMask(text, px, weight)` → `{w, ...}` — rasterize only (measure or cache).
- `sign.clear()` / `sign.render()` — per frame: clear framebuffer, draw, flush to canvas.
- `sign.glow` (bool) — toggles the LED bloom.

> **Critical gotcha:** the engine multiplies stored color values by 255 at render time, so **all colors must be stored 0–1**. The prototype keeps its palette 0–255 for readability and normalizes once in `boot()` (`x/255`). If you copy the palette, either pre-divide or replicate that normalization step.

## Widgets / Views

Each widget has a bigsign draw fn and a longboi draw fn. Signature is always `fn(sign, ctx)` where `ctx = { t: msClock, speed: multiplier }`. Coordinates below are **physical pixels** on the sign.

### 1. Scores (default widget)
Rotates through games: **live → final → next**. Team names in brand color, **scores white** (winning final score turns green). Inning shown as ▲ (top) / ▼ (bottom) + number; bases as diamonds; count color-coded **balls green · strikes yellow · outs red**. Series wins shown as small orange dashes by each team.
- **bigsign → `twoRowScores`** — two-row layout: top band `AWAY score … HOME score` with series dashes; a dotted divider at y31; bottom band shows live state (inning triangle red, bases cluster, count) or centered `FINAL`. Paging dots bottom-right.
- **longboi → `scoreboardLong`** — full scoreboard: big team names (px20) and scores (px34) in the left/right thirds; centered live cluster — inning + outs pips (red) on top row, `B/S` count below, bases diamond to the right.
- **`tickerScores`** — a continuous single-line crawl variant also exists (built via `buildTickerSegs`), if a scrolling ticker is wanted instead of the held board.

### 2. Standings
Division board: brand chip, W-L, PCT, games back (amber, "—" for leader in gray), streak (green W / red L), L10.
- **bigsign → `standingsBig`** — rank, chip, team, W-L, GB, STRK across 5 rows (y starts 12, 10px pitch).
- **longboi → `standingsLong`** — adds PCT (amber) and L10 (cyan) columns.

### 3. Promotions
- **bigsign → `promoBig`** — holds ONE promo card, pages through the homestand: date (amber), name (white px16), opponent chip + `VS OPP` (violet), `offerType · BY sponsor` (cyan), start time (amber). Paging dots.
- **longboi → `promoLong`** — the whole schedule as a continuous hi-res crawl.
- **longboi → `promoLongCard`** — held single card: big name left, opponent/time/offer info block right, paging dots.
- **longboi → `promoLongScroll`** — same card but the **name scrolls** inside a fixed clipped band (x6–300) via `maskScroll`, for names too wide for the column (e.g. "Hawaiian Shirt & Beach Towel Giveaway"). The clip uses the engine's native `blit` `x0/x1` so the name never bleeds into the right info block.

### 4. Statcast
Notable batted balls rotate hero-style. Result colored by type (HR green, out red, else amber).
- **bigsign → `statcastBig`** — batter, big exit-velo number (amber) + MPH, then launch angle (cyan) · distance (magenta) · pitch (green). Paging dots bottom-right.
- **longboi → `statcastLong`** — batter + result on the left; EXIT VELO / LAUNCH / PITCH stat columns; a **procedural trajectory arc** (`traj`) whose peak height scales with launch angle, ending in the distance in feet.

### 5. Attendance
- **bigsign → `attendBig`** — big paid number (amber) with **% FULL** and **VS AVG** stat pair beside it; bar annotated "PAID ATTENDANCE" left, "`<cap>` CAP" right; capacity fill bar tinted the **home team's color** (lifted to LED brightness, hue preserved — see `homeColor()`), with a white season-average tick.
- **longboi → `attendLong`** — big paid number, PAID ATTENDANCE label, % FULL / VS AVG columns, `<cap> CAP` right, full-width home-colored fill bar with average tick.
- There is **no sellout field** — 100% full communicates a sellout on its own.

## Interactions & Behavior
- **Animation loop:** single `setInterval` at **30 FPS**. Each frame: advance `clock` by dt (capped 250ms), then for each visible sign `clear()` → `draw(sign, ctx)` → `render()`.
- **Card rotation:** held widgets pick the current item by `Math.floor(ctx.t / (period/ctx.speed)) % n` (periods 4200–5600 ms).
- **Crawls:** offset = `((t/1000) * pxPerSec * speed) % contentWidth`, redrawn each frame; content is repeated to fill the width (no gap).
- **Controls (prototype only — not part of the shipped widget):** SPEED slider (0.25–2.5×), GLOW toggle, Play/Pause.
- **Performance:** text rasterization is memoized per sign (`cacheRaster`) — `hiresMask`/`hires` are wrapped with a `{text|px|weight}` cache — and an **IntersectionObserver** pauses drawing for off-screen signs. Both matter: without the cache, `getImageData` per glyph per frame across many signs pegs the main thread.
- **Fonts:** `Silkscreen` (labels/UI chrome) and `Inter` (rasterized sign text). The loop waits on `document.fonts.ready` before booting so text measures correctly.

## Data Sources — MLB Stats API (`https://statsapi.mlb.com/api/v1/`)
All sample data in the prototype is **fictional placeholder** exercising the layouts. Every field below maps to a real API field except where noted. Field mapping is also inlined as comments above each data block in the `.dc.html`.

- **Scores** — `/schedule?hydrate=linescore` + `/game/{gamePk}/feed/live`
  - `ar/hr` = `liveData.linescore.teams.away|home.runs`
  - `half` = `isTopInning` (T/B) · `inn` = `currentInning`
  - `balls/strikes/outs` = `linescore.balls|strikes|outs`
  - `b1/b2/b3` = `linescore.offense.first|second|third` (presence = runner on base)
  - `state` = `gameData.status` (Scheduled / In Progress / Final)
  - `start` = `gameData.datetime.dateTime`
  - `as/hs` (series wins) = schedule `seriesStatus` (`include_series_status`); only meaningful in a series/postseason context.
- **Standings** — `/standings?leagueId=103,104&season=YYYY`
  - `w/l` = `teamRecords.wins|losses` · `pct` = `winningPercentage` · `gb` = `gamesBack`
  - `l10` = `teamRecords.records.splitRecords[type=lastTen]` · `strk` = `teamRecords.streak.streakCode`
- **Promotions** — `/schedule?hydrate=promotions` → `dates[].games[].promotions[]`
  - `name`, `offerType`, `presentedBy` (sponsor), `imageUrl`, `imageAltText` are the real object fields.
  - **There is no free-text tagline/detail field.** `offerType` is the categorical label ("Giveaway", "Theme Night", …); the prototype's second line is `offerType · BY presentedBy`. Do not invent descriptive copy.
- **Statcast** — `/game/{gamePk}/playByPlay` (GUMBO) `allPlays[].playEvents[]`
  - `ev` = `hitData.launchSpeed` · `la` = `hitData.launchAngle` · `dist` = `hitData.totalDistance`
  - `res` = `result.event` · `pv` = `pitchData.startSpeed` · `pt` = `details.type.code`
  - `p` (batter) = `matchup.batter.fullName`. Deeper Statcast metrics live on Baseball Savant, not statsapi.
- **Attendance**
  - `paid` = `/game/{gamePk}/feed/live` → `gameData.gameInfo.attendance`
  - `cap` = `/venues/{venueId}?hydrate=fieldInfo` → `fieldInfo.capacity`
  - `avg` = `/attendance?teamId=&season=` → `records.attendanceAverage`
  - `home` = team abbreviation (drives the bar color). 100% full = sellout; no separate flag.

## Design Tokens
Semantic palette (shown here 0–255 for readability — **store as 0–1**, i.e. divide by 255):

| Token   | RGB (0–255)     | Use |
| ------- | --------------- | --- |
| ident   | 255,255,255     | Primary text / scores / neutral |
| win     | 60,220,60       | Wins, % full, positive delta, balls |
| loss    | 255,60,60       | Losses, outs, inning triangle, negative delta |
| amber   | 255,180,0       | Headline numbers, dates, PCT, time |
| cyan    | 0,220,255       | Secondary metrics, L10, offer line |
| magenta | 255,80,255      | Distance / trajectory |
| violet  | 170,90,255      | Opponent (`VS`) |
| label   | 70,90,130       | Dim labels, dividers, empty bases, bar track |
| YEL     | 255,217,0       | Strikes in the count |
| ORANGE  | 255,128,0       | Series-win dashes |

**Team chip colors** (`TEAMS`, two-tone `c1/c2` diagonal split) and **scoreboard team-name colors** (`SCORECOL`) are defined in the logic class — extend both tables as more teams appear.

**Sign geometry:** bigsign `{logW:64, logH:16, scale:4, cell:4}` → 256×64; longboi `{logW:128, logH:16, scale:4, cell:3}` → 512×64. Frame rate 30 FPS.

**Prototype page chrome (HTML around the signs, not on the sign):** bg `#07090d`, text `#e7ecf3`, muted `#8593a8`/`#9aa7ba`, hairlines `rgba(255,255,255,.06–.08)`; fonts Inter + Silkscreen; sign bezel is `#000` with `border-radius:12px` and `inset 0 0 40px rgba(0,0,0,.7)`.

## Assets
No external image assets — everything is drawn procedurally on the framebuffer. Fonts: **Silkscreen** and **Inter** (Google Fonts). Dependency: **`led-engine-bundle.js`** (the product's LED renderer, `window.LED`).

## Files
- `Baseball LED Widgets.dc.html` — the full prototype: HTML gallery page + logic class with all data tables, drawing primitives, and per-widget draw functions. Data-source field mappings are inlined as comments above each data block. This is the authoritative spec.
- `led-engine-bundle.js` — the LED renderer (`window.LED`) used by the prototype; matches the real signs' dot geometry, glow, and text rasterization.

> Note: the prototype is authored as a Design Component (`.dc.html`) — the `<x-dc>` wrapper and `support.js` reference are the design-tool runtime and are **not** part of the widget. Only the logic class (draw functions + data) and the LED engine calls are relevant to production.
