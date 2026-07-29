# led-ticker-weather

A weather **plugin** for [led-ticker](https://github.com/JamesAwesome/led-ticker), backed by [WeatherAPI.com](https://www.weatherapi.com/). It contributes two widgets: `weather.current` (location label, current temperature, and a condition icon) and `weather.forecast` (a held multi-day forecast card).

This package split out of `led-ticker-feeds` (its `feeds.weather` widget); the type is now `weather.current`.

## Prerequisites

- A working [led-ticker](https://github.com/JamesAwesome/led-ticker) install.
- A free [WeatherAPI.com](https://www.weatherapi.com/) API key, exported as `WEATHERAPI_KEY`.
- Internet access on the Pi (the widget calls the WeatherAPI.com API).

## Install

The widget auto-registers via the `led_ticker.plugins` entry point — once the package is installed, no `[plugins]` config change is needed.

**Into a containerized led-ticker (recommended):** add this package to `config/requirements-plugins.txt` (copy it from `config/requirements-plugins.example.txt`), then rebuild:

```text
led-ticker-weather
```

```bash
# in your led-ticker checkout
docker compose up -d --build
```

**Standalone (a venv that already has led-ticker):**

```bash
pip install led-ticker-weather
```

See the led-ticker [Plugins docs](https://docs.ledticker.dev/plugins/) for the constraint-based install the Docker image uses.

## Configuration

Set the API key in your `.env`:

```text
WEATHERAPI_KEY=your-key-here
```

Then add the widget:

```toml
[[playlist.section]]
[[playlist.section.widget]]
type = "weather.current"
location = "London"
```

The widget polls WeatherAPI.com in the background and renders the label, temperature, and a condition icon. Conditions map to icon slugs via `_match_condition` (sun / cloud / rain / snow / thunder / fog).

## weather.forecast

A held multi-day forecast card. Layout is auto-detected per sign: smallsign (scale 1) shows a 3-day strip (today + 2 more); bigsign (scale > 1, physical width < 400px) shows a today hero next to a 4-day strip; longboi (scale > 1, physical width >= 400px) shows an expanded hero next to a 6-day strip with precipitation percentages.

```toml
[[playlist.section]]
[[playlist.section.widget]]
type = "weather.forecast"
location = "Boston, MA"
```

### Configuration

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `location` | string or `{lat = ..., lon = ...}` | **required** (unless `demo = true`) | Same location forms as `weather.current`: name / zip / "lat,lon" / a `{lat=…, lon=…}` table. |
| `layout` | string | `"auto"` | `"auto"` \| `"strip"` \| `"big"` \| `"long"`. `auto` picks by sign shape (see above). An explicit `"long"` on a panel narrower than 400px degrades to `"big"`; an explicit `"big"` or `"long"` on a scale-1 sign renders as `"strip"` — hi-res is impossible there (`led-ticker validate` warns in both cases). |
| `units` | string | `"imperial"` | `"imperial"` \| `"metric"`. |
| `update_interval` | int (seconds) | `10800` | How often the widget re-polls WeatherAPI.com (3 hours by default — forecasts don't need current-conditions cadence). |
| `demo` | bool | `false` | Render a fixed sample week (BOSTON) instead of calling the network — no API key or location needed. Useful for previews. |
| `demo_days` | int | `0` | Demo-only: truncate the fixed sample week to this many strip days (`0` = full 6-day week) so a config can preview a **short feed** — the strip justifying fewer days across the panel — without a live key. Ignored unless `demo = true`. |

### Requirements

Same `WEATHERAPI_KEY` env var as `weather.current` (see Prerequisites above). The widget calls `/v1/forecast.json?days=7`. Free-tier WeatherAPI.com keys only return 3 forecast days; the widget degrades gracefully — it renders however many days the feed actually provides and widens the strip columns to fill the available space (a 3-day key on longboi shows the hero next to a 2-day strip instead of 6).

### Divergences from the design handoff

The normative visual spec lives at [`design/`](design/) (`design/README.md` + the `.dc.html` prototype). This widget faithfully reproduces its layouts and palette, with six deliberate divergences:

- **Condition icons are the packaged emoji**, not the handoff's procedural glyphs. smallsign strips always draw the curated 8x8 weather sprite; bigsign/longboi strips and the hero slot both draw the hero's HIRES/32x32 sprite (box-downscaled to the strip's icon size on the strip, native on the hero) — this upgrades two hero-only distinctions (overcast, patchy rain) to standard-pack sprites the curated set can't draw on its own, and gives every hi-res sign the same icon language in the hero and the strip. Icon boxes snap to sprite sizes (8/16/24/32px) rather than the handoff's 14/18/22/30/40px boxes, so partly-cloudy-at-night is still approximated (`partly_cloudy` lowres on smallsign, a plain moon elsewhere).
- **Hi-res strip icons are downscaled from the 32x32 hires sprite, not upscaled from the 8x8 lowres one.** An earlier iteration integer-upscaled the curated 8x8 sprite (k=2 bigsign, k=3 longboi); a later pass switched to box-area-downscaling the same hires source the hero uses, for crisper edges and a consistent icon per condition across hero and strip.
- **Small hi-res text (day labels, hi/lo, precip %, FEELS) is the bundled `spleen-6x12` pixel font, not Inter.** An earlier iteration used Inter/freetype at every text size; spleen reads more crisply at small sizes on the panel and is deterministic (no freetype cross-platform variance) — so this text is now exact-pinned in tests, unlike the big hero temperature and location label, which stay Inter.
- **smallsign text uses the nearest bundled BDF font (5x8)**, not the handoff's Silkscreen px7 — metrics may differ by up to a row.
- **No °F/°C runtime toggle or GLOW control.** Those were prototype chrome; units come from the `units` config field, and glow is a property of the physical hardware, not something the widget can render.
- **No 15 FPS re-render loop.** The card is static per data update and follows the engine's normal held-card cadence — there's nothing to animate between polls.

## Weather value token (`:id:` in any widget's text)

Besides the `weather.current` **widget**, this plugin registers a `weather.current`
**source** — a live value you embed in another widget's text with a `:id:` token.

```toml
[[source]]
id = "weather.nyc"
type = "weather.current"
location = "New York, US"          # name / zip / "lat,lon" / {lat=…, lon=…}
interval = 1800                    # seconds; how often to refresh
format = "{temp_f}°F {condition}"  # optional; this is the default
# placeholder = "…"                # optional; shown until the first fetch
```

Then reference it anywhere text is drawn:

```toml
[[playlist.section]]
[[playlist.section.widget]]
type = "message"
text = "NYC: :weather.nyc:"        # -> "NYC: 72°F Clear", updating live
```

`WEATHERAPI_KEY` comes from your `.env` (never config). Available `format`
fields (current conditions): `temp_f`, `temp_c`, `condition`, `feelslike_f`,
`feelslike_c`, `humidity`, `wind_mph`, and `emoji`. The `emoji` field expands to
a condition icon — `format = "{temp_f}° {emoji}"` → `72° ☀`. The source polls
on its own `interval`, independently of the `weather.current` widget.

A full bigsign example that exercises the token (default format, the `{emoji}`
sprite, feels-like/humidity fields, and a resilience check) lives at
[`config/config.weather_smoketest.bigsign.toml`](config/config.weather_smoketest.bigsign.toml) —
edit the `location` fields and copy it to your `config.toml`.

## Development

This package lives in the [led-ticker-plugins](https://github.com/JamesAwesome/led-ticker-plugins) monorepo. Run tooling from the repo root:

```bash
uv sync --extra dev
uv run pytest plugins/weather
uv run ruff check plugins/weather
```
