# led-ticker-rss

An RSS/Atom headline **plugin** for [led-ticker](https://github.com/JamesAwesome/led-ticker). It contributes a single `rss.feed` widget that polls a feed URL and scrolls each story headline across the panel as its own ticker message.

This package split out of `led-ticker-feeds` (its `feeds.rss` widget); the type is now `rss.feed`.

## Prerequisites

- A working [led-ticker](https://github.com/JamesAwesome/led-ticker) install.
- Internet access on the Pi (the widget fetches the feed URL).

## Install

The widget auto-registers via the `led_ticker.plugins` entry point — once the package is installed, no `[plugins]` config change is needed.

**Into a containerized led-ticker (recommended):** add this package to `config/requirements-plugins.txt` (copy it from `config/requirements-plugins.example.txt`), then rebuild:

```text
git+https://github.com/JamesAwesome/led-ticker-plugins.git@rss-v0.2.0#subdirectory=plugins/rss
```

```bash
# in your led-ticker checkout
docker compose up -d --build
```

**Standalone (a venv that already has led-ticker):**

```bash
pip install "git+https://github.com/JamesAwesome/led-ticker-plugins.git@rss-v0.2.0#subdirectory=plugins/rss"
```

led-ticker isn't on PyPI, so this path only works where led-ticker is already installed. See the led-ticker [Plugins docs](https://docs.ledticker.dev/plugins/) for the constraint-based install the Docker image uses.

## Configuration

```toml
[[sections]]
[[sections.widgets]]
type = "rss.feed"
url = "https://feeds.bbci.co.uk/news/rss.xml"
```

The widget is a Container: it pulls the feed in the background and expands each story into its own scrolling `TickerMessage`, so live updates surface within one display cycle.

## Development

This package lives in the [led-ticker-plugins](https://github.com/JamesAwesome/led-ticker-plugins) monorepo. Run tooling from the repo root:

```bash
uv sync --extra dev
uv run pytest plugins/rss
uv run ruff check plugins/rss
```
