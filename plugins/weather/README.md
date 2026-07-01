# led-ticker-weather

A current-conditions weather **plugin** for [led-ticker](https://github.com/JamesAwesome/led-ticker), backed by [WeatherAPI.com](https://www.weatherapi.com/). It contributes a single `weather.current` widget that shows the location label, current temperature, and a condition icon.

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
[[sections]]
[[sections.widgets]]
type = "weather.current"
location = "London"
```

The widget polls WeatherAPI.com in the background and renders the label, temperature, and a condition icon. Conditions map to icon slugs via `_match_condition` (sun / cloud / rain / snow / thunder / fog).

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
[[sections]]
[[sections.widgets]]
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
