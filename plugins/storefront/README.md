# led-ticker-storefront

An always-visible **OPEN**/**CLOSED** business-hours badge **overlay** plugin for [led-ticker](https://github.com/JamesAwesome/led-ticker). It paints on top of whatever the sign is showing, flipped by a weekly schedule and the Pi's clock — no external service, works offline. It's the sibling of core's [busy light](https://docs.ledticker.dev/concepts/busy-light/) overlay: same mechanism, richer content.

**Full documentation** — the config reference, schedule syntax (including the overnight-wrap rule), layout notes, and caveats — lives on the docs site: **<https://docs.ledticker.dev/plugins/storefront/>**.

## Prerequisites

- A working [led-ticker](https://github.com/JamesAwesome/led-ticker) install.
- No API keys or internet access needed — the badge is driven entirely by the local clock and a schedule you write in `config.toml`.

## Install

The overlay auto-registers via the `led_ticker.plugins` entry point — once the package is installed, no `[plugins]` config change is needed.

**Into a containerized led-ticker (recommended):** add this package to `config/requirements-plugins.txt` (copy it from `config/requirements-plugins.example.txt`), then restart:

```text
led-ticker-storefront
```

```bash
# in your led-ticker checkout
docker compose restart
```

**Standalone (a venv that already has led-ticker):**

```bash
pip install led-ticker-storefront
```

See the led-ticker [Plugins docs](https://docs.ledticker.dev/plugins/) for the constraint-based install the Docker image uses.

## Configuration

Unlike a widget, storefront isn't added to a playlist section — it's a top-level `[storefront]` block:

```toml
[storefront]
corner = "top_right"

[storefront.open]
text = "OPEN"
color = [0, 255, 0]

[storefront.closed]
text = "CLOSED"
color = [255, 0, 0]

[storefront.schedule]
mon = "09:00-17:00"
tue = "09:00-17:00"
wed = "09:00-17:00"
thu = "09:00-17:00"
fri = "18:00-02:00"   # overnight wrap: belongs to Friday, still OPEN at Sat 00:30
sat = "10:00-14:00"
# sun omitted = closed all day
```

See the [docs page](https://docs.ledticker.dev/plugins/storefront/) for the full field reference (background, padding, font/font_size, timezone, corner, orientation, per-state overrides), the complete schedule grammar (multi-range, `closed`, `00:00-24:00`, the overnight-wrap rule), hi-res-font/vertical-badge sizing notes, and the "neon glow" animated-color recipe.

Two bigsign smoke fixtures (forced-OPEN and forced-CLOSED) live in [`examples/`](examples/) — they're render-demo GIF fixtures, not a hardware wiring reference; see `config/config.bigsign.example.toml` in the core repo for the real 8-panel chain config.

## Caveats

- **Timezone / NTP dependency** — a wrong clock (bad `timezone`, no NTP sync, a DST edge) shows the wrong badge; the startup log always states the time the plugin thinks it is.
- **No `led-ticker validate` coverage** — overlay config isn't covered by the widget-only `validate` command. A malformed `[storefront]` block is caught at startup instead: logged, the badge disabled, the panel keeps running.

## Development

This package lives in the [led-ticker-plugins](https://github.com/JamesAwesome/led-ticker-plugins) monorepo. Run tooling from the repo root:

```bash
uv sync --extra dev
uv run pytest plugins/storefront
uv run ruff check plugins/storefront
```
