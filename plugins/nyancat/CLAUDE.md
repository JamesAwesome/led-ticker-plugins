# CLAUDE.md — led-ticker-nyancat

Nyan Cat sprite-trail transitions (`src/led_ticker_nyancat/nyancat.py`): `NyanCat` / `NyanCatReverse` / `NyanCatAlternating`, registered in `__init__.py` as `forward` / `reverse` / `alternating` → namespace `nyancat`. Has a hi-res variant backed by `sprites/nyancat.webp` (bundled in the wheel via hatchling because it lives under the package dir).

- Imports ONLY from `led_ticker.plugin` (public surface) — enforced by `tests/test_import_purity.py`.
- The bundled sprite presence is enforced by `tests/test_packaging.py`.
- Dep: `led-ticker` only.
- Lint/test from the monorepo root: `make lint` / `uv run pytest plugins/nyancat`. CI is the root path-filtered matrix.
- No `from __future__ import annotations` (PEP 649 / Python 3.14 rule).
