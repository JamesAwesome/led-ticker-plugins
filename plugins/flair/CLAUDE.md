# CLAUDE.md — led-ticker-flair

One wheel, four plugin namespaces. Each family lives under `src/led_ticker_flair/<family>/`, registered in `src/led_ticker_flair/<family>/__init__.py` as `forward` / `reverse` / `alternating`.

## Invariants

- **One wheel / four entry points** — `pyproject.toml` declares all four `led_ticker.plugins` entry points (`nyancat`, `pokeball`, `pacman`, `sailor_moon`). The entry-point NAME is the plugin namespace; transition type strings are `<namespace>.<variant>`.
- **Sprites load via `Path(__file__).parent / "sprites"`** — sprites live beside the family module file (e.g. `src/led_ticker_flair/nyancat/sprites/nyancat.webp`). Moving a family submodule without moving its `sprites/` directory breaks sprite loading.
- **Imports only from `led_ticker.plugin`** — enforced per-family by `tests/test_import_purity.py`.
- **No `from __future__ import annotations`** (PEP 649 / Python 3.14 rule).
- Dep: `led-ticker` only.
- Lint/test from the monorepo root: `make lint` / `uv run pytest plugins/flair`. CI is the root path-filtered matrix.
