# CLAUDE.md — led-ticker-pacman

Pac-Man sprite-trail transitions (`src/led_ticker_pacman/pacman.py`): `Pacman` / `PacmanReverse` / `PacmanAlternating`, registered in `__init__.py` as `forward` / `reverse` / `alternating` → namespace `pacman`. No hi-res variant; sprites are drawn programmatically.

- Imports ONLY from `led_ticker.plugin` (public surface) — enforced by `tests/test_import_purity.py`.
- Dep: `led-ticker` only.
- Lint/test from the monorepo root: `make lint` / `uv run pytest plugins/pacman`. CI is the root path-filtered matrix.
- No `from __future__ import annotations` (PEP 649 / Python 3.14 rule).
