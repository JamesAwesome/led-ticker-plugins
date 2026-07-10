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

## Exceptions (holidays & special hours)

Override specific dates — or a date that recurs every year — without touching the weekly `[storefront.schedule]`:

```toml
[storefront.exceptions]
"12-25"      = "closed"          # recurring: every Christmas
"2026-11-26" = "closed"          # one-off
"12-24"      = "09:00-13:00"     # recurring short day
"2026-12-31" = "20:00-02:00"     # special hours; wraps allowed
```

Keys are `"MM-DD"` (recurring, matches that date every year) or `"YYYY-MM-DD"` (one specific
date); values reuse the same day-string grammar as the weekly schedule (`"closed"`, a single
range, comma-separated multiple ranges, `00:00-24:00`). Precedence is **specific date >
recurring date > weekly day** — a matching exception REPLACES the day's hours outright, it
never merges with the weekly schedule underneath it.

The overnight-wrap rule applies to exception days too: a range whose end wraps past midnight
still belongs to its **start** day, even when the following calendar day is itself an
exception. Friday `18:00-02:00` + Saturday `"closed"` → Saturday 00:30 still reads OPEN;
adjust Friday's hours for a hard midnight cutoff.

Every open/closed flip logs an enriched line naming the next change, e.g.:

```text
storefront: OPEN (matched mon 09:00-17:00; closes 17:00; now 12:30 America/New_York)
storefront: CLOSED (no matching range; opens 09:00 tomorrow; now 20:15 America/New_York)
```

## Caveats

- **Timezone / NTP dependency** — a wrong clock (bad `timezone`, no NTP sync, a DST edge) shows the wrong badge; the startup log always states the time the plugin thinks it is.
- **No `led-ticker validate` coverage** — overlay config isn't covered by the widget-only `validate` command. A malformed `[storefront]` block is caught at startup instead: logged, the badge disabled, the panel keeps running.
- **Not covered by config hot-reload** — `[storefront]` is read once at startup, not on every reload. Editing the block (schedule, badge text/color, corner, font, etc.) while the display is running has no effect until the process restarts; core's hot-reload machinery flags this as a restart-required change. Restart (`docker compose restart`, or your process manager's equivalent) to apply.

## Development

This package lives in the [led-ticker-plugins](https://github.com/JamesAwesome/led-ticker-plugins) monorepo. Run tooling from the repo root:

```bash
uv sync --extra dev
uv run pytest plugins/storefront
uv run ruff check plugins/storefront
```
