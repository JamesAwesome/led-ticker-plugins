# CLAUDE.md — led-ticker-flair

One wheel, five plugin namespaces: four sprite-trail families (`nyancat`, `pokeball`, `pacman`, `sailor_moon`) plus `flair` (the wheel's own name, for text animations). Each sprite family lives under `src/led_ticker_flair/<family>/`, registered in `src/led_ticker_flair/<family>/__init__.py` as `forward` / `reverse` / `alternating`. The `flair` namespace registers animations (e.g. `flair.propeller`).

## Invariants

- **One wheel / five entry points** — `pyproject.toml` declares all five `led_ticker.plugins` entry points (`nyancat`, `pokeball`, `pacman`, `sailor_moon`, `flair`). The entry-point NAME is the plugin namespace; transition type strings are `<namespace>.<variant>`, animation type strings are `<namespace>.<name>`.
- **`flair` namespace naming exception** — unlike the four sprite families, the `flair` namespace is named after the wheel itself, not a sprite character. This is an intentional exception to the namespace-per-sprite-family pattern. It registers animations, not transitions, and has no `sprites/` directory.
- **Sprites load via `Path(__file__).parent / "sprites"`** — sprites live beside the family module file (e.g. `src/led_ticker_flair/nyancat/sprites/nyancat.webp`). Moving a family submodule without moving its `sprites/` directory breaks sprite loading. The `flair` submodule has no sprites and is not subject to this invariant.
- **Imports only from `led_ticker.plugin`** — enforced per-family by `tests/test_import_purity.py`.
- **No `from __future__ import annotations`** (PEP 649 / Python 3.14 rule).
- Dep: `led-ticker` only.
- Lint/test from the monorepo root: `make lint` / `uv run pytest plugins/flair`. CI is the root path-filtered matrix.
- **Co-dev against an unreleased core:** the `led-ticker-core>=4.3` floor won't
  resolve against an editable pre-release core (hatch-vcs reports e.g.
  `4.2.2.devN`); install with `uv pip install --no-deps -e plugins/flair` and
  run everything via `uv run --no-sync ...` until core 4.3.0 ships.
