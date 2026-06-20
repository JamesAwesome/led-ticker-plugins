# CLAUDE.md — led-ticker-sailor-moon

Sailor Moon sprite-trail transitions (`src/led_ticker_sailor_moon/sailor_moon.py`): `SailorMoon` / `SailorMoonReverse` / `SailorMoonAlternating`, registered in `__init__.py` as `forward` / `reverse` / `alternating` → namespace `sailor_moon`. No hi-res variant; sprites are drawn programmatically.

- Imports ONLY from `led_ticker.plugin` (public surface) — enforced by `tests/test_import_purity.py`.
- Dep: `led-ticker` only.
- Lint/test from the monorepo root: `make lint` / `uv run pytest plugins/sailor_moon`. CI is the root path-filtered matrix.
- No `from __future__ import annotations` (PEP 649 / Python 3.14 rule).
