# Vendored test stubs

## `rgbmatrix/`

A verbatim copy of the led-ticker engine's `rgbmatrix` test stub
(`__init__.py`, `graphics.py`), vendored from:

    led-ticker/tests/stubs/rgbmatrix/

### Why it's here

Plugin tests import `rgbmatrix` (and `rgbmatrix.graphics`) the same way the
engine's tests do. The real C extension only exists on a Raspberry Pi, so the
test suite relies on a pure-Python stub. Vendoring the stub lets this
workspace's tests run from the repo root **without** a sibling `led-ticker`
checkout on the import path. The root `pyproject.toml` puts `tests/stubs` on
`pythonpath` (pytest) and `extraPaths` (pyright).

### Interim status — remove when led-ticker#233 lands

This is a temporary bridge. led-ticker#233 ships `led_ticker.testkit`, which
will expose the stub as an installable, importable module. When it lands:

1. Delete this `tests/stubs/rgbmatrix/` directory.
2. Drop `pythonpath = ["tests/stubs"]` from `[tool.pytest.ini_options]` and
   `extraPaths = ["tests/stubs"]` from `[tool.pyright]` in the root
   `pyproject.toml` (replace with the `led_ticker.testkit` import path the
   issue specifies).

### Keep this copy in lockstep

Until #233 ships, do **not** let this copy diverge from the engine's stub. If
the engine's stub changes, re-copy both files here. A divergent stub would let
plugin tests pass against behavior the real engine no longer has.
