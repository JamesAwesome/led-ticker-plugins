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

## Development

This package lives in the [led-ticker-plugins](https://github.com/JamesAwesome/led-ticker-plugins) monorepo. Run tooling from the repo root:

```bash
uv sync --extra dev
uv run pytest plugins/weather
uv run ruff check plugins/weather
```
