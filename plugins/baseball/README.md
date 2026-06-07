# led-ticker-baseball

A [led-ticker](https://github.com/JamesAwesome/led-ticker) plugin that adds
baseball to your LED sign:

- **`baseball.scores`** — MLB scores widget (layouts: `ticker`, `scoreboard`, `two_row`)
- **`baseball.standings`** — MLB division standings widget
- **`:baseball.ball:`** — a pixel-art baseball emoji (lo-res 8×8 + hi-res)
- **`baseball.roll`** / **`baseball.roll_reverse`** / **`baseball.roll_alternating`** — a rolling-baseball transition (with hi-res variants on scaled panels)

> Status: scaffolding. Widgets, emoji, and transitions are being ported in.
> Full configuration docs land here once the port is complete.

## Install

The plugin is installed declaratively via led-ticker's
`config/requirements-plugins.txt` (see led-ticker's plugin docs). Entry points
auto-register at startup, so once installed the `baseball.*` widgets/transitions
and the `:baseball.ball:` emoji are available with no extra wiring.

## Development

led-ticker is not published to PyPI, so this plugin resolves it from a sibling
checkout. Clone both repos side by side:

```
~/projects/.../led-ticker
~/projects/.../led-ticker-baseball   ← you are here
```

Then:

```bash
uv sync --extra dev      # resolves led-ticker from ../led-ticker
uv run pytest -q         # uses ../led-ticker/tests/stubs for the rgbmatrix stub
uv run ruff check src tests
```

The plugin imports **only** from the public `led_ticker.plugin` surface — an AST
test (`tests/test_import_purity.py`) enforces this.
