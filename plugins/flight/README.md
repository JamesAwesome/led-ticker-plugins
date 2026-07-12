# led-ticker-flight

A planes-overhead ADS-B flight tracker **plugin** for [led-ticker](https://github.com/JamesAwesome/led-ticker). It contributes a single `flight.overhead` widget that shows nearby aircraft — callsign, aircraft type, altitude + climb/descend cue, ground speed, track, and distance/bearing — pulled from the free, keyless [adsb.lol](https://adsb.lol/) API, in the visual language of an airport departures board.

The widget renders in one of three layouts depending on sign shape — a scrolling single-line crawl on a scale-1 sign, or a hi-res single-flight hero / wide multi-column dashboard on a scale-4 sign — chosen automatically or pinned explicitly. See `design/README.md` for the normative visual spec (palette, airline tail-fin marks, exact layout geometry) this widget faithfully reproduces. Several deliberate divergences from the prototype are documented in code: ticker back-fill for seamless looping, the empty-state label's fit-fallback, and a procedural 7×3 level bar in place of a glyph (each chosen where the prototype's own behavior contradicted its design prose or the hi-res charset it draws from); the prototype's blinking live-refresh pulse dot is dropped entirely (no other led-ticker widget carries an unexplained status indicator, and poll health is already visible in the web UI's Status tab); and `hero`/`dashboard` fade the whole card through black for 200ms at each end of a flight's dwell window when 2+ flights are tracked (a hardware-review finding — a hard cut between rotating flights read as a glitch on the physical panel; see Layouts below).

## Prerequisites

- A working [led-ticker](https://github.com/JamesAwesome/led-ticker) install.
- Internet access on the Pi (the widget polls the adsb.lol API — no API key required).
- The latitude/longitude of your receiver (or antenna/home location) — or set `demo = true` to preview with a bundled sample feed instead.

## Install

The widget auto-registers via the `led_ticker.plugins` entry point — once the package is installed, no `[plugins]` config change is needed.

**Into a containerized led-ticker (recommended):** add this package to `config/requirements-plugins.txt` (copy it from `config/requirements-plugins.example.txt`), then rebuild:

```text
led-ticker-flight
```

```bash
# in your led-ticker checkout
docker compose up -d --build
```

**Standalone (a venv that already has led-ticker):**

```bash
pip install led-ticker-flight
```

See the led-ticker [Plugins docs](https://docs.ledticker.dev/plugins/) for the constraint-based install the Docker image uses.

## Configuration

```toml
[[playlist.section]]
[[playlist.section.widget]]
type = "flight.overhead"
latitude = 40.7128
longitude = -74.0060
radius_km = 30
```

A complete, runnable example (with every field commented) lives at [`examples/flight.toml`](examples/flight.toml).

### Field reference

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `latitude` | float | **required** (unless `demo = true`) | Receiver location, -90 to 90. |
| `longitude` | float | **required** (unless `demo = true`) | Receiver location, -180 to 180. |
| `radius_km` | int | `30` | Search radius in kilometers, 2-460. Converted to nautical miles for the adsb.lol call. |
| `layout` | string | `"auto"` | `"auto"` \| `"ticker"` \| `"hero"` \| `"dashboard"`. `auto` picks by sign shape (see Layouts below). An explicit `"hero"`/`"dashboard"` on a scale-1 sign falls back to `ticker` — hi-res is impossible there. |
| `max_aircraft` | int | `4` | Cap on tracked aircraft, 1-8. The closest N (by distance) are kept. |
| `interval` | float | `10.0` | Seconds between adsb.lol polls, 5-3600. |
| `demo` | bool | `false` | Render the bundled 4-flight sample feed instead of calling the network. No coordinates needed. |

No font/color knobs — the design handoff pins them (see `design/README.md`); the semantic palette (ident white, altitude amber, speed green, track cyan, distance magenta, climb/descend cues) and airline tail-fin colors are fixed across every layout and sign.

## Layouts

- **`ticker`** — a single-line, continuously-scrolling BDF crawl through every tracked aircraft's full field set, dot-separated. Targets scale-1 signs (smallsign) where hi-res drawing isn't available.
- **`hero`** — one flight at a time, shown large: a swept tail-fin, a hi-res callsign, an airline-name/type line, a metrics line (vertical-rate cue, altitude, speed, track, distance), and paging dots. Rotates through the tracked flights on a fixed dwell. Targets narrower hi-res signs (scale > 1, < 400 physical px — e.g. bigsign).
- **`dashboard`** — the widescreen layout: hero ident on the left, four labelled metric columns (altitude, speed, track, distance) filling the rest of the width. Targets wide hi-res signs (scale > 1, >= 400 physical px — e.g. longboi).

`layout = "auto"` (the default) resolves at draw time from the canvas's scale and physical width, so the same config works unmodified across smallsign/bigsign/longboi deploys.

With 2 or more tracked flights, `hero`/`dashboard` fade the entire card through black for 200ms at the start and end of each flight's dwell window (0.4s total spent near/at black per rotation) instead of cutting straight to the next flight. A single tracked flight is just held — it never fades.

## Data source

Aircraft come from [adsb.lol](https://adsb.lol/)'s `/v2/point/{lat}/{lon}/{radius}` endpoint — free, public, no API key. Be a good citizen of the shared endpoint: the default 10s `interval` is already frequent for a keyless public API; don't lower it without reason. Aircraft missing a callsign, altitude, or position are dropped; the remaining set is sorted by distance and capped at `max_aircraft`.

## Development

This package lives in the [led-ticker-plugins](https://github.com/JamesAwesome/led-ticker-plugins) monorepo. Run tooling from the repo root:

```bash
uv sync --extra dev
uv run pytest plugins/flight
uv run ruff check plugins/flight
uv run pyright plugins/flight/src
```
