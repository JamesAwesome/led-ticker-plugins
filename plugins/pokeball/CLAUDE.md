# CLAUDE.md — led-ticker-pokeball

Pokeball/Pikachu sprite-trail transitions (`src/led_ticker_pokeball/pokeball.py`): `Pokeball` / `PokeballReverse` / `PokeballAlternating`, registered in `__init__.py` as `forward` / `reverse` / `alternating` → namespace `pokeball`. Also registers the `:pokeball.ball:` emoji (lo-res + hi-res) from `src/led_ticker_pokeball/emoji.py` via `api.emoji("ball", …)` + `api.hires_emoji("ball", …)`. Three sprites bundled under `sprites/` (`pokeball.gif`, `pokeball-pikachu.gif`, `pikachu-run-transparent.gif`).

- Imports ONLY from `led_ticker.plugin` (public surface) — enforced by `tests/test_import_purity.py`.
- The bundled sprite presence is enforced by `tests/test_packaging.py`.
- Dep: `led-ticker` only.
- Lint/test from the monorepo root: `make lint` / `uv run pytest plugins/pokeball`. CI is the root path-filtered matrix.
- No `from __future__ import annotations` (PEP 649 / Python 3.14 rule).
