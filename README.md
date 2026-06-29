# led-ticker-plugins

[![CI](https://github.com/JamesAwesome/led-ticker-plugins/actions/workflows/ci.yml/badge.svg)](https://github.com/JamesAwesome/led-ticker-plugins/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

The official first-party plugin pack for [led-ticker](https://github.com/JamesAwesome/led-ticker) — the
asyncio toolkit that drives Adafruit RGB Matrix HAT / HUB75 LED panels from a Raspberry Pi.
These plugins add live data and effects to your sign: current **weather**, **RSS/Atom**
headlines, **cryptocurrency** prices, **calendar** agendas, **MLB** scores, **pool**
water-temperature, and homage **sprite-trail transitions**. Developed together in one uv
workspace and **distributed per-plugin** so you install only what you want.

## Install a plugin

All first-party plugins are published to PyPI — install only the ones you want:

```bash
pip install led-ticker-<name>   # e.g. pip install led-ticker-weather
```

### What's included

| Plugin | PyPI package | Widget / transition types | Data source |
|--------|--------------|---------------------------|-------------|
| Weather | `led-ticker-weather` | `weather.current` | [WeatherAPI.com](https://www.weatherapi.com/) |
| RSS / Atom | `led-ticker-rss` | `rss.feed` | any RSS or Atom feed |
| Crypto | `led-ticker-crypto` | `crypto.coingecko` | [CoinGecko](https://www.coingecko.com/) |
| Calendar | `led-ticker-calendar` | `calendar.events` | iCalendar (`.ics`) URL |
| Baseball / MLB | `led-ticker-baseball` | `baseball.scores`, `.standings`, `.promotions`, `.statcast`, `.attendance` | MLB Stats API |
| Pool | `led-ticker-pool` | `pool.monitor` | InfluxDB v2 |
| Flair | `led-ticker-flair` | sprite-trail transitions `nyancat.*`, `pokeball.*`, `pacman.*`, `sailor_moon.*` (+ `:pokeball.ball:` emoji) | bundled sprite artwork |

## Develop

```bash
make dev    # uv sync the whole workspace (led-ticker-core from PyPI)
make test   # pytest every member
make lint   # ruff + pyright
```

Each plugin lives under `plugins/<name>/` with its own `pyproject.toml`,
`CLAUDE.md`, and `README.md` (versions derive from per-plugin git tags via hatch-vcs — no manual bump needed). See
`docs/superpowers/specs/2026-06-19-led-ticker-plugins-monorepo-design.md`.

## Contributing

This is the curated first-party pack. **New plugins belong in your own repo** — the [authoring guide](https://docs.ledticker.dev/plugins/authoring/01-scaffold/) shows how, no fork needed. Fixes and improvements to the *existing* plugins here are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Third-party homages

The `led-ticker-flair` pack (`nyancat`, `pokeball`, `pacman`, `sailor_moon`)
contains **unofficial fan homages** — the character names/designs and any bundled
sprite artwork belong to their respective owners and are **not** covered by this
project's license. See [NOTICE.md](NOTICE.md) for details. The data plugins
(`pool`, `baseball`, `crypto`, `calendar`, `rss`, `weather`) are original
works.

## License

[MIT](LICENSE) © James Awesome — applies to the plugin **code**. The third-party
characters/artwork referenced by the sprite-trail homage plugins are **not**
covered by it; see [NOTICE.md](NOTICE.md).
