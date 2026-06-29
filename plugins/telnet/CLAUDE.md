# CLAUDE.md

Guidance for Claude Code when working in **led-ticker-telnet**, an external plugin for
[led-ticker](https://github.com/JamesAwesome/led-ticker).

`README.md` is the source of truth for the user-facing surface (install, backend selection,
env vars, connect instructions). This file keeps the **load-bearing invariants** a contributor
must respect, plus navigation aids. When a fact here and the README disagree about *how a
feature works*, the README wins; this file is the source of truth for *how to keep it working*.

## Overview

This plugin contributes, via the `led_ticker.plugins` entry point, a TCP/ANSI terminal
rendering backend:

- `telnet.telnet` — streams each frame as true-color ANSI escape sequences to all connected
  clients. Selected in TOML with `[display] backend = "telnet.telnet"`.

The entry-point name `telnet` is the plugin namespace, so the backend is `telnet.telnet`
(see `register()` in `__init__.py`).

## Commands

`led-ticker-core` resolves from PyPI (`>=2.2`) — no sibling checkout needed. To co-develop
against an unreleased engine, add it editable on top: `uv pip install -e ../led-ticker`.

```bash
uv sync --extra dev          # install deps (led-ticker-core from PyPI)
uv run pytest -q             # full suite (asyncio_mode = "auto")
uv run ruff check src tests  # lint — run before pushing
uv run pyright src           # type check
```

Python **3.14+** only.

## Package layout

```
src/led_ticker_telnet/
  __init__.py   # register(api) entry point — the only place names are registered
  backend.py    # TelnetBackend + render_ansi()
```

`register()` in `__init__.py`:

```python
def register(api):
    api.backend("telnet")(TelnetBackend)
```

## Load-bearing invariants

Each rule must hold when modifying the named area.

**Import only the public surface** — every `led_ticker` import MUST come from `led_ticker.plugin`,
never `led_ticker.<internal>`. Enforced by `tests/test_import_purity.py`, which AST-walks every
source file (catches `from`-imports and `import led_ticker.x` forms, not just a text grep).
If you need a core symbol that is not on `led_ticker.plugin.__all__`, that is a core API
change — raise it upstream; do not reach around the surface.

**Python 3.14 / PEP 649** — no `from __future__ import annotations` anywhere (same rule as
core). Bare `tuple[int, int, int]` annotations are fine.

**`swap()` must never block on a slow client** — the render loop calls `swap()` at panel cadence
(~20 fps). `swap()` writes to each client's TCP send buffer with `writer.write(data)` — no
`await writer.drain()`. A slow client's buffer fills and frames are dropped for that client;
the render loop and other clients are never delayed. Adding an `await drain()` call here would
freeze the panel on a single slow connection.

**Bind failure must degrade, not crash** — `_serve()` wraps `asyncio.start_server` in a
`try/except OSError` and logs a warning before returning. A port-in-use or permission error
leaves `_server = None`; the backend still creates canvases and calls `swap()` normally (no
clients, but no crash). Never propagate the `OSError` up to the render loop.

**No running event loop at `setup()` → degrade** — `setup()` catches `RuntimeError` from
`asyncio.get_running_loop()` (the sync-test path), logs a warning, and returns without
starting the server task. This keeps the plugin usable from unit tests that call `setup()`
in a non-async context.

**Two-buffer flip (constraint #8)** — `TelnetBackend` holds two `HeadlessCanvas` buffers.
`create_canvas()` returns `_buffers[_back]`. `swap()` flips `_back ^= 1` and returns the
OTHER buffer, so the caller always draws into a different object than the one last presented.
Never return the same buffer from `swap()` that was passed in.

**`render_ansi` reads via `get_pixel`** — the ANSI serializer reads pixel values through
`canvas.get_pixel(x, y)`, which is defined on `HeadlessCanvas` (the only canvas type this
backend creates). Do NOT call `canvas.get_pixel` on an rgbmatrix canvas — it does not exist
there (constraint #3 on the engine side bans `GetPixel`; the backend reading its own canvas
is explicitly allowed and the only correct path here).

**Canvas type isolation** — `TelnetBackend` only ever creates and handles `HeadlessCanvas`
objects. Do not accept or serialize a `ScaledCanvas` or an rgbmatrix canvas — the plugin
protocol guarantees that `create_canvas()` is the source for every canvas the engine draws
into.

**Namespacing** — the backend registers as `telnet.telnet`. The first component (`telnet`)
comes from the entry-point key in `pyproject.toml`; the second comes from
`api.backend("telnet")` in `register()`. These must stay in sync with the user-facing
`backend = "telnet.telnet"` TOML value documented in README.md. Renaming either without
updating the other breaks user configs.

## Sharp edges / Gotchas

**Odd canvas heights** — `render_ansi` pairs rows with `range(0, canvas.height, 2)`. If
`height` is odd, the last row has no partner; the bottom pixel color defaults to `(0, 0, 0)`
(black background). This is intentional and documented in the odd-height test.

**Terminal true-color support** — `render_ansi` always emits 24-bit ANSI sequences
(`38;2;r;g;b`). Terminals without true-color support (older xterm builds, some SSH clients)
will misrender — the colors will be wrong but the structure will display. This is an
intentional trade-off; dithering to 256-color is a future enhancement, not a correctness bug.

**Port/host are env-only** — plugin backends cannot currently read TOML `[display]` sub-keys.
`LED_TICKER_TELNET_PORT` and `LED_TICKER_TELNET_HOST` are the only configuration knobs.
A future led-ticker-core `[display.<backend>]` → `from_config` mechanism would close this.
Do NOT add a `from_config` classmethod without the corresponding core API — it would be
unreachable dead code.

## Tests / CI

`uv run pytest -q` runs the suite (`tests/`):

- `test_import_purity.py` — AST tripwire (public-surface-only). Treat a failure as a contract
  violation, not a test to relax.
- `test_telnet_backend.py` — backend conformance, buffer-flip, ANSI serialization, client
  lifecycle (connect / disconnect / slow / broken), server bind/failure, and register smoke.

CI (`.github/workflows/ci.yml`): checks out this repo, Python 3.14, `uv sync --extra dev`
(led-ticker-core from PyPI), then `ruff check src tests` and `pytest -q`.

## Adding to the plugin

Register the class in `register()` in `__init__.py` (`api.backend`); it becomes
`telnet.<name>`. Import any core dependency from `led_ticker.plugin` only, and keep the
import-purity test green.
