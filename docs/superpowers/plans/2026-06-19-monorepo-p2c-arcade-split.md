# Monorepo P2c — arcade split → nyancat / pokeball / pacman / sailor_moon Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the `led-ticker-arcade` plugin into four independent monorepo packages — one per sprite-trail family — history-preserving, applying the finalized breaking renames (`<family>.forward` / `.reverse` / `.alternating`, plus `:pokeball.ball:`).

**Architecture:** arcade has zero cross-family imports — each family file (`nyancat.py`, `pokeball.py`, `pacman.py`, `sailor_moon.py`, plus `emoji.py`) imports only stdlib + `led_ticker.plugin`. Sprites load via `Path(__file__).resolve().parent / "sprites" / ...`, so moving a family's sprites into its own package's `sprites/` dir needs no path-code change. Each family becomes a self-contained package via one `git filter-repo` pass (prune to that family's files + sprites + tests, rename the package dir, drop under `plugins/<name>/`), then fresh scaffolding + per-package `test_packaging.py`. No engine change; deps are just `led-ticker`.

**Tech Stack:** Python 3.14, uv workspace, hatchling, pytest, ruff, pyright, `git filter-repo`.

**Scope:** P2c only — the arcade split (the last split; completes the 10-package set). P3 (engine catalog/hints/CLI/docs PR + archive the old repos incl. `led-ticker-arcade` + flip the requirements example) and P4 (hardware smoke) follow. Breaking renames stay invisible to deployed signs until P3 flips the engine catalog. See `docs/superpowers/specs/2026-06-19-led-ticker-plugins-monorepo-design.md`.

**Working repo:** `/Users/james/projects/github/jamesawesome/led-ticker-plugins`, branch `feat/monorepo-p2c-arcade-split` off `main` (has P1+P2a+P2b merged). All work on that branch, never `main`. Source: `/Users/james/projects/github/jamesawesome/led-ticker-arcade`. `git filter-repo` is installed.

---

## Per-family parameters (the source of truth for all four tasks)

| family | package dir / import pkg | family `.py` | sprite files | family test files | transition classes | sprites? |
|---|---|---|---|---|---|---|
| nyancat | `nyancat` / `led_ticker_nyancat` | `nyancat.py` | `sprites/nyancat.webp` | `test_nyancat.py` | `NyanCat`, `NyanCatReverse`, `NyanCatAlternating` | yes (1) |
| pokeball | `pokeball` / `led_ticker_pokeball` | `pokeball.py` + `emoji.py` | `sprites/pokeball.gif`, `sprites/pokeball-pikachu.gif`, `sprites/pikachu-run-transparent.gif` | `test_pokeball.py` + `test_emoji.py` | `Pokeball`, `PokeballReverse`, `PokeballAlternating` | yes (3) + emoji |
| pacman | `pacman` / `led_ticker_pacman` | `pacman.py` | — | `test_pacman.py` | `Pacman`, `PacmanReverse`, `PacmanAlternating` | no |
| sailor_moon | `sailor_moon` / `led_ticker_sailor_moon` | `sailor_moon.py` | — | `test_sailor_moon.py` | `SailorMoon`, `SailorMoonReverse`, `SailorMoonAlternating` | no |

Shared scaffolding tests copied into EVERY package: `tests/conftest.py`, `tests/test_import_purity.py`, `tests/test_smoke.py`. `tests/test_packaging.py` (asserts sprite presence) is **split**: nyancat keeps its `nyancat.webp` assertion; pokeball keeps its three gif assertions; pacman + sailor_moon DROP it (no sprites). All packages: version `0.1.0`, deps `["led-ticker"]`.

Registered names after rename: base transition class → `api.transition("forward")`, `*Reverse` → `api.transition("reverse")`, `*Alternating` → `api.transition("alternating")`. Pokeball additionally: `api.emoji("ball", POKEBALL)` + `api.hires_emoji("ball", POKEBALL_HIRES)`.

---

### Task 1: Split out `pacman` (simplest — no sprites; establishes the pattern)

**Files:** Create `plugins/pacman/**`.

- [ ] **Step 1: Create the branch (first task only)**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-plugins
git checkout main && git pull --ff-only origin main
git checkout -b feat/monorepo-p2c-arcade-split
git branch --show-current   # MUST be feat/monorepo-p2c-arcade-split — if main, STOP
```

- [ ] **Step 2: filter-repo the pacman slice (prune + rename package), then subdir it**

```bash
cd /Users/james/projects/github/jamesawesome
rm -rf /tmp/pacman-fr
git clone led-ticker-arcade /tmp/pacman-fr
cd /tmp/pacman-fr
git filter-repo --force \
  --path src/led_ticker_arcade/__init__.py \
  --path src/led_ticker_arcade/pacman.py \
  --path tests/test_pacman.py \
  --path tests/test_import_purity.py \
  --path tests/test_smoke.py \
  --path tests/conftest.py \
  --path-rename src/led_ticker_arcade/:src/led_ticker_pacman/
git filter-repo --force --to-subdirectory-filter plugins/pacman
git log --oneline -- plugins/pacman/src/led_ticker_pacman/pacman.py | tail -2   # ORIGINAL arcade commits
```

- [ ] **Step 3: Merge into the monorepo**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-plugins
git remote add pacman-fr /tmp/pacman-fr
git fetch pacman-fr
git merge --allow-unrelated-histories --no-edit pacman-fr/main
git remote remove pacman-fr
find plugins/pacman -name '__pycache__' -type d -prune -exec rm -rf {} +
```

- [ ] **Step 4: Overwrite `plugins/pacman/src/led_ticker_pacman/__init__.py`**

```python
"""led-ticker-pacman: Pac-Man sprite-trail transitions contributed via the
``led_ticker.plugins`` entry point.

The entry-point name ``pacman`` is the plugin namespace, so transitions are
referenced in config.toml as ``transition = "pacman.forward"`` etc.
"""

from led_ticker_pacman.pacman import Pacman, PacmanAlternating, PacmanReverse


def register(api):
    api.transition("forward")(Pacman)
    api.transition("reverse")(PacmanReverse)
    api.transition("alternating")(PacmanAlternating)
```

- [ ] **Step 5: Create `plugins/pacman/pyproject.toml`**

```toml
[project]
name = "led-ticker-pacman"
version = "0.1.0"
description = "Pac-Man sprite-trail transitions for led-ticker (pacman.forward/.reverse/.alternating)."
readme = "README.md"
requires-python = ">=3.14"
authors = [{ name = "James Awesome", email = "james@morelli.nyc" }]
dependencies = [
    "led-ticker",
]

# Entry-point NAME ("pacman") is the plugin namespace -> TOML `transition = "pacman.forward"`.
[project.entry-points."led_ticker.plugins"]
pacman = "led_ticker_pacman:register"

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-cov>=5.0",
    "pre-commit>=4.0",
    "ruff>=0.4",
    "pyright>=1.1",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/led_ticker_pacman"]

[tool.ruff]
target-version = "py314"
src = ["src"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]

[tool.coverage.report]
fail_under = 90
```

- [ ] **Step 6: Fix test imports + package-path references (`led_ticker_arcade` → `led_ticker_pacman`)**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-plugins
grep -rl 'led_ticker_arcade' plugins/pacman | xargs sed -i '' 's/led_ticker_arcade/led_ticker_pacman/g'
grep -rn 'led_ticker_arcade\|arcade\.' plugins/pacman/   # MUST return nothing (except none)
```
`test_import_purity.py` builds a path `... / "src" / "led_ticker_arcade"` → now `led_ticker_pacman`; confirm it still passes (it asserts the family imports only from `led_ticker.plugin`).

- [ ] **Step 7: Write `plugins/pacman/README.md` + `CLAUDE.md`**

`README.md`:
```markdown
# led-ticker-pacman

Pac-Man sprite-trail transitions for [led-ticker](https://github.com/JamesAwesome/led-ticker) — `pacman.forward` / `pacman.reverse` / `pacman.alternating`.

Part of the [led-ticker-plugins](https://github.com/JamesAwesome/led-ticker-plugins) monorepo. Install:

```bash
pip install "git+https://github.com/JamesAwesome/led-ticker-plugins.git@pacman-v0.1.0#subdirectory=plugins/pacman"
```

Split out of the former `led-ticker-arcade` plugin (was `arcade.pacman*`).
```

`CLAUDE.md`:
```markdown
# CLAUDE.md — led-ticker-pacman

Pac-Man sprite-trail transitions (`src/led_ticker_pacman/pacman.py`): `Pacman` / `PacmanReverse` / `PacmanAlternating`, registered in `__init__.py` as `forward` / `reverse` / `alternating` → namespace `pacman`. No hi-res variant; sprites are drawn programmatically.

- Imports ONLY from `led_ticker.plugin` (public surface) — enforced by `tests/test_import_purity.py`.
- Dep: `led-ticker` only.
- Lint/test from the monorepo root: `make lint` / `uv run pytest plugins/pacman`. CI is the root path-filtered matrix.
- No `from __future__ import annotations` (PEP 649 / Python 3.14 rule).
```

- [ ] **Step 8: Sync + verify green from root**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-plugins
uv sync --extra dev
uv run pytest plugins/pacman -v
uv run ruff format plugins/pacman && uv run ruff check plugins/pacman && uv run ruff format --check plugins/pacman
uv run pyright plugins/pacman/src
uv run python -c "
import led_ticker._plugin_loader as L
from led_ticker.transitions import _TRANSITION_REGISTRY
L.load_plugins(None)
need={'pacman.forward','pacman.reverse','pacman.alternating'}
assert need <= set(_TRANSITION_REGISTRY), sorted(k for k in _TRANSITION_REGISTRY if k.startswith('pacman.'))
print('pacman transitions OK')
"
```
All must pass.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "feat(pacman): split led-ticker-arcade pacman family into the pacman package (arcade.pacman* -> pacman.forward/.reverse/.alternating)"
```

---

### Task 2: Split out `sailor_moon` (same shape as pacman — no sprites)

**Files:** Create `plugins/sailor_moon/**`.

- [ ] **Step 1: Branch check**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-plugins
git branch --show-current   # MUST be feat/monorepo-p2c-arcade-split — if main, STOP
```

- [ ] **Step 2: filter-repo the sailor_moon slice**

```bash
cd /Users/james/projects/github/jamesawesome
rm -rf /tmp/sailor_moon-fr
git clone led-ticker-arcade /tmp/sailor_moon-fr
cd /tmp/sailor_moon-fr
git filter-repo --force \
  --path src/led_ticker_arcade/__init__.py \
  --path src/led_ticker_arcade/sailor_moon.py \
  --path tests/test_sailor_moon.py \
  --path tests/test_import_purity.py \
  --path tests/test_smoke.py \
  --path tests/conftest.py \
  --path-rename src/led_ticker_arcade/:src/led_ticker_sailor_moon/
git filter-repo --force --to-subdirectory-filter plugins/sailor_moon
git log --oneline -- plugins/sailor_moon/src/led_ticker_sailor_moon/sailor_moon.py | tail -2
```

- [ ] **Step 3: Merge**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-plugins
git remote add sailor_moon-fr /tmp/sailor_moon-fr
git fetch sailor_moon-fr
git merge --allow-unrelated-histories --no-edit sailor_moon-fr/main
git remote remove sailor_moon-fr
find plugins/sailor_moon -name '__pycache__' -type d -prune -exec rm -rf {} +
```

- [ ] **Step 4: Overwrite `plugins/sailor_moon/src/led_ticker_sailor_moon/__init__.py`**

```python
"""led-ticker-sailor-moon: Sailor Moon sprite-trail transitions contributed via
the ``led_ticker.plugins`` entry point.

The entry-point name ``sailor_moon`` is the plugin namespace, so transitions are
referenced in config.toml as ``transition = "sailor_moon.forward"`` etc.
"""

from led_ticker_sailor_moon.sailor_moon import (
    SailorMoon,
    SailorMoonAlternating,
    SailorMoonReverse,
)


def register(api):
    api.transition("forward")(SailorMoon)
    api.transition("reverse")(SailorMoonReverse)
    api.transition("alternating")(SailorMoonAlternating)
```

- [ ] **Step 5: Create `plugins/sailor_moon/pyproject.toml`** (same as pacman's, substituting):
  - `name = "led-ticker-sailor-moon"`
  - `description = "Sailor Moon sprite-trail transitions for led-ticker (sailor_moon.forward/.reverse/.alternating)."`
  - entry: `sailor_moon = "led_ticker_sailor_moon:register"`
  - wheel `packages = ["src/led_ticker_sailor_moon"]`
  - `version = "0.1.0"`, `dependencies = ["led-ticker"]`, same dev/build/ruff/coverage tables.

- [ ] **Step 6: Fix references**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-plugins
grep -rl 'led_ticker_arcade' plugins/sailor_moon | xargs sed -i '' 's/led_ticker_arcade/led_ticker_sailor_moon/g'
grep -rn 'led_ticker_arcade' plugins/sailor_moon/   # MUST return nothing
```

- [ ] **Step 7: README + CLAUDE** for sailor_moon (mirror pacman's, substituting the family name, transitions `sailor_moon.forward/.reverse/.alternating`, install `@sailor_moon-v0.1.0`, "split out of led-ticker-arcade (was arcade.sailor_moon*)"). No "gun"/"footgun" metaphors.

- [ ] **Step 8: Sync + verify**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-plugins
uv sync --extra dev
uv run pytest plugins/sailor_moon -v
uv run ruff format plugins/sailor_moon && uv run ruff check plugins/sailor_moon && uv run ruff format --check plugins/sailor_moon
uv run pyright plugins/sailor_moon/src
uv run python -c "
import led_ticker._plugin_loader as L
from led_ticker.transitions import _TRANSITION_REGISTRY
L.load_plugins(None)
need={'sailor_moon.forward','sailor_moon.reverse','sailor_moon.alternating'}
assert need <= set(_TRANSITION_REGISTRY), sorted(k for k in _TRANSITION_REGISTRY if k.startswith('sailor_moon.'))
print('sailor_moon transitions OK')
"
```

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "feat(sailor_moon): split led-ticker-arcade sailor_moon family into the sailor_moon package (arcade.sailor_moon* -> sailor_moon.forward/.reverse/.alternating)"
```

---

### Task 3: Split out `nyancat` (1 hi-res sprite)

**Files:** Create `plugins/nyancat/**` (incl. `sprites/nyancat.webp`).

- [ ] **Step 1: Branch check** — `git branch --show-current` = feat/monorepo-p2c-arcade-split.

- [ ] **Step 2: filter-repo the nyancat slice (INCLUDE the sprite + its packaging test)**

```bash
cd /Users/james/projects/github/jamesawesome
rm -rf /tmp/nyancat-fr
git clone led-ticker-arcade /tmp/nyancat-fr
cd /tmp/nyancat-fr
git filter-repo --force \
  --path src/led_ticker_arcade/__init__.py \
  --path src/led_ticker_arcade/nyancat.py \
  --path src/led_ticker_arcade/sprites/nyancat.webp \
  --path tests/test_nyancat.py \
  --path tests/test_packaging.py \
  --path tests/test_import_purity.py \
  --path tests/test_smoke.py \
  --path tests/conftest.py \
  --path-rename src/led_ticker_arcade/:src/led_ticker_nyancat/
git filter-repo --force --to-subdirectory-filter plugins/nyancat
ls plugins/nyancat/src/led_ticker_nyancat/sprites/   # nyancat.webp present
git log --oneline -- plugins/nyancat/src/led_ticker_nyancat/nyancat.py | tail -2
```

- [ ] **Step 3: Merge**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-plugins
git remote add nyancat-fr /tmp/nyancat-fr
git fetch nyancat-fr
git merge --allow-unrelated-histories --no-edit nyancat-fr/main
git remote remove nyancat-fr
find plugins/nyancat -name '__pycache__' -type d -prune -exec rm -rf {} +
```

- [ ] **Step 4: Overwrite `plugins/nyancat/src/led_ticker_nyancat/__init__.py`**

```python
"""led-ticker-nyancat: Nyan Cat sprite-trail transitions contributed via the
``led_ticker.plugins`` entry point.

The entry-point name ``nyancat`` is the plugin namespace, so transitions are
referenced in config.toml as ``transition = "nyancat.forward"`` etc.
"""

from led_ticker_nyancat.nyancat import NyanCat, NyanCatAlternating, NyanCatReverse


def register(api):
    api.transition("forward")(NyanCat)
    api.transition("reverse")(NyanCatReverse)
    api.transition("alternating")(NyanCatAlternating)
```

- [ ] **Step 5: Create `plugins/nyancat/pyproject.toml`** (same as pacman's, substituting):
  - `name = "led-ticker-nyancat"`
  - `description = "Nyan Cat sprite-trail transitions for led-ticker (nyancat.forward/.reverse/.alternating)."`
  - entry: `nyancat = "led_ticker_nyancat:register"`
  - wheel `packages = ["src/led_ticker_nyancat"]`
  - `version = "0.1.0"`, `dependencies = ["led-ticker"]`, same dev/build/ruff/coverage tables.

> Sprite bundling: `nyancat.webp` lives inside `src/led_ticker_nyancat/sprites/`, so hatchling includes it in the wheel by default (same as the source arcade package). No `force-include` needed.

- [ ] **Step 6: Fix references; trim `test_packaging.py` to nyancat-only**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-plugins
grep -rl 'led_ticker_arcade' plugins/nyancat | xargs sed -i '' 's/led_ticker_arcade/led_ticker_nyancat/g'
```
Then edit `plugins/nyancat/tests/test_packaging.py`: keep ONLY the `nyancat.webp` presence test (the `_sprites_dir()` helper + `test_nyancat_sprite_present`). DELETE the `pikachu` / `pokeball` sprite tests (those sprites are not in this package). Confirm: `grep -rn 'led_ticker_arcade\|pokeball\|pikachu' plugins/nyancat/` returns nothing.

- [ ] **Step 7: README + CLAUDE** for nyancat (mirror pacman's; note it HAS a hi-res sprite `sprites/nyancat.webp`; transitions `nyancat.forward/.reverse/.alternating`; install `@nyancat-v0.1.0`; "split out of led-ticker-arcade (was arcade.nyancat*)").

- [ ] **Step 8: Sync + verify (incl. sprite bundling)**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-plugins
uv sync --extra dev
uv run pytest plugins/nyancat -v        # incl. test_packaging sprite-present
uv run ruff format plugins/nyancat && uv run ruff check plugins/nyancat && uv run ruff format --check plugins/nyancat
uv run pyright plugins/nyancat/src
uv run python -c "
import led_ticker._plugin_loader as L
from led_ticker.transitions import _TRANSITION_REGISTRY
L.load_plugins(None)
need={'nyancat.forward','nyancat.reverse','nyancat.alternating'}
assert need <= set(_TRANSITION_REGISTRY), sorted(k for k in _TRANSITION_REGISTRY if k.startswith('nyancat.'))
print('nyancat transitions OK')
"
```

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "feat(nyancat): split led-ticker-arcade nyancat family into the nyancat package (arcade.nyancat* -> nyancat.forward/.reverse/.alternating)"
```

---

### Task 4: Split out `pokeball` (3 sprites + the `:pokeball.ball:` emoji)

**Files:** Create `plugins/pokeball/**` (incl. `emoji.py` + `sprites/{pokeball.gif,pokeball-pikachu.gif,pikachu-run-transparent.gif}`).

- [ ] **Step 1: Branch check** — `git branch --show-current` = feat/monorepo-p2c-arcade-split.

- [ ] **Step 2: filter-repo the pokeball slice (family + emoji + 3 sprites + 2 tests)**

```bash
cd /Users/james/projects/github/jamesawesome
rm -rf /tmp/pokeball-fr
git clone led-ticker-arcade /tmp/pokeball-fr
cd /tmp/pokeball-fr
git filter-repo --force \
  --path src/led_ticker_arcade/__init__.py \
  --path src/led_ticker_arcade/pokeball.py \
  --path src/led_ticker_arcade/emoji.py \
  --path src/led_ticker_arcade/sprites/pokeball.gif \
  --path src/led_ticker_arcade/sprites/pokeball-pikachu.gif \
  --path src/led_ticker_arcade/sprites/pikachu-run-transparent.gif \
  --path tests/test_pokeball.py \
  --path tests/test_emoji.py \
  --path tests/test_packaging.py \
  --path tests/test_import_purity.py \
  --path tests/test_smoke.py \
  --path tests/conftest.py \
  --path-rename src/led_ticker_arcade/:src/led_ticker_pokeball/
git filter-repo --force --to-subdirectory-filter plugins/pokeball
ls plugins/pokeball/src/led_ticker_pokeball/sprites/   # 3 sprites present
git log --oneline -- plugins/pokeball/src/led_ticker_pokeball/pokeball.py | tail -2
```

- [ ] **Step 3: Merge**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-plugins
git remote add pokeball-fr /tmp/pokeball-fr
git fetch pokeball-fr
git merge --allow-unrelated-histories --no-edit pokeball-fr/main
git remote remove pokeball-fr
find plugins/pokeball -name '__pycache__' -type d -prune -exec rm -rf {} +
```

- [ ] **Step 4: Overwrite `plugins/pokeball/src/led_ticker_pokeball/__init__.py`** (transitions + emoji, slug `ball`)

```python
"""led-ticker-pokeball: Pokeball/Pikachu sprite-trail transitions + the
``:pokeball.ball:`` emoji, contributed via the ``led_ticker.plugins`` entry
point.

The entry-point name ``pokeball`` is the plugin namespace, so transitions are
``transition = "pokeball.forward"`` etc. and the emoji is ``:pokeball.ball:``.
"""

from led_ticker_pokeball.emoji import POKEBALL, POKEBALL_HIRES
from led_ticker_pokeball.pokeball import Pokeball, PokeballAlternating, PokeballReverse


def register(api):
    api.transition("forward")(Pokeball)
    api.transition("reverse")(PokeballReverse)
    api.transition("alternating")(PokeballAlternating)
    api.emoji("ball", POKEBALL)
    api.hires_emoji("ball", POKEBALL_HIRES)
```

- [ ] **Step 5: Create `plugins/pokeball/pyproject.toml`** (same as pacman's, substituting):
  - `name = "led-ticker-pokeball"`
  - `description = "Pokeball/Pikachu sprite-trail transitions + :pokeball.ball: emoji for led-ticker."`
  - entry: `pokeball = "led_ticker_pokeball:register"`
  - wheel `packages = ["src/led_ticker_pokeball"]`
  - `version = "0.1.0"`, `dependencies = ["led-ticker"]`, same dev/build/ruff/coverage tables.

- [ ] **Step 6: Fix references; update `emoji.py` slug docstring; trim `test_packaging.py` to pokeball sprites; fix `test_emoji.py` expected slug**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-plugins
grep -rl 'led_ticker_arcade' plugins/pokeball | xargs sed -i '' 's/led_ticker_arcade/led_ticker_pokeball/g'
```
- Edit `plugins/pokeball/tests/test_packaging.py`: keep ONLY the three pokeball/pikachu sprite-present tests; DELETE the `nyancat.webp` test.
- `emoji.py` module docstring says "Pokeball emoji (arcade.pokeball)" — update to `pokeball.ball`.
- `test_emoji.py`: if it asserts the registered slug name (was `pokeball` / `arcade.pokeball`), update the expectation to `ball` (the slug) / `pokeball.ball` (qualified). The emoji is registered via `api.emoji("ball", ...)`. Confirm what the test checks and align it to the new slug; do NOT weaken an assertion — match the real new name.
- Confirm: `grep -rn 'led_ticker_arcade\|arcade\.\|"pokeball")' plugins/pokeball/` shows no stale `arcade` refs and no `api.*("pokeball")` (slug is now `ball`).

- [ ] **Step 7: README + CLAUDE** for pokeball (mirror pacman's; note 3 bundled sprites + the `:pokeball.ball:` emoji lo+hi-res; transitions `pokeball.forward/.reverse/.alternating`; install `@pokeball-v0.1.0`; "split out of led-ticker-arcade (was arcade.pokeball* + :arcade.pokeball:)").

- [ ] **Step 8: Sync + verify (transitions + emoji + sprites)**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-plugins
uv sync --extra dev
uv run pytest plugins/pokeball -v
uv run ruff format plugins/pokeball && uv run ruff check plugins/pokeball && uv run ruff format --check plugins/pokeball
uv run pyright plugins/pokeball/src
uv run python -c "
import led_ticker._plugin_loader as L
from led_ticker.transitions import _TRANSITION_REGISTRY
from led_ticker.pixel_emoji import EMOJI_REGISTRY, HIRES_REGISTRY
L.load_plugins(None)
need={'pokeball.forward','pokeball.reverse','pokeball.alternating'}
assert need <= set(_TRANSITION_REGISTRY), sorted(k for k in _TRANSITION_REGISTRY if k.startswith('pokeball.'))
assert 'pokeball.ball' in EMOJI_REGISTRY and 'pokeball.ball' in HIRES_REGISTRY, 'emoji missing'
print('pokeball transitions + :pokeball.ball: OK')
"
```

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "feat(pokeball): split led-ticker-arcade pokeball family into the pokeball package (arcade.pokeball* -> pokeball.forward/.reverse/.alternating, :arcade.pokeball: -> :pokeball.ball:)"
```

---

### Task 5: Verify the full 10-member workspace + open PR

**Files:** none.

- [ ] **Step 1: Member count + whole-workspace green**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-plugins
ls -d plugins/*/ | sed 's#plugins/##; s#/##'   # 10: baseball calendar crypto nyancat pacman pokeball pool rss sailor_moon weather
make test
make lint
make format-check
```
Expected: **10 members**, all green, coverage ≥90.

- [ ] **Step 2: No stale `arcade.*` types; all four families + emoji resolve**

```bash
uv run python -c "
import led_ticker._plugin_loader as L
from led_ticker.transitions import _TRANSITION_REGISTRY
from led_ticker.pixel_emoji import EMOJI_REGISTRY, HIRES_REGISTRY
L.load_plugins(None)
trans = {k for k in _TRANSITION_REGISTRY if '.' in k}
for fam in ('nyancat','pokeball','pacman','sailor_moon'):
    for v in ('forward','reverse','alternating'):
        assert f'{fam}.{v}' in trans, f'missing {fam}.{v}'
assert not any(k.startswith('arcade.') for k in trans), 'stale arcade.* transition'
assert 'pokeball.ball' in EMOJI_REGISTRY and 'pokeball.ball' in HIRES_REGISTRY
assert not any(k.startswith('arcade.') for k in EMOJI_REGISTRY) and not any(k.startswith('arcade.') for k in HIRES_REGISTRY)
print('all 4 families + :pokeball.ball: present, no arcade.* remaining')
"
```

- [ ] **Step 3: Push + open PR (no merge without consent)**

```bash
git push -u origin feat/monorepo-p2c-arcade-split
gh pr create --repo JamesAwesome/led-ticker-plugins --base main --head feat/monorepo-p2c-arcade-split \
  --title "P2c: split arcade into nyancat/pokeball/pacman/sailor_moon (breaking renames)" \
  --body "Splits led-ticker-arcade into four independent packages, history-preserving, completing the 10-package set. BREAKING renames (finalized): arcade.<fam>{,_reverse,_alternating} -> <fam>.forward/.reverse/.alternating; :arcade.pokeball: -> :pokeball.ball:. nyancat + pokeball carry their hi-res sprites; pacman + sailor_moon have none. Invisible to deployed signs until P3; led-ticker-arcade is archived in P3. Do NOT merge without consent; tags <fam>-v0.1.0 come after merge."
```

- [ ] **Step 4: Confirm CI green**

```bash
gh pr checks <PR#> --repo JamesAwesome/led-ticker-plugins
```
Expected: `check (nyancat|pokeball|pacman|sailor_moon)` (the four new members) green; `ci-passed` green.

---

### Task 6: (CONSENT-GATED) Merge + cut 4 tags + verify a tagged install

> Do NOT perform any step until the user explicitly approves the merge.

- [ ] **Step 1: Merge with a MERGE COMMIT (preserve history — never squash)**

```bash
gh pr merge <PR#> --repo JamesAwesome/led-ticker-plugins --merge --delete-branch
git checkout main && git pull --ff-only origin main
git log --oneline -- plugins/pokeball/src/led_ticker_pokeball/pokeball.py | tail -2   # original arcade history present
```

- [ ] **Step 2: Cut the four namespaced tags**

```bash
git tag nyancat-v0.1.0 && git tag pokeball-v0.1.0 && git tag pacman-v0.1.0 && git tag sailor_moon-v0.1.0
git push origin nyancat-v0.1.0 pokeball-v0.1.0 pacman-v0.1.0 sailor_moon-v0.1.0
```

- [ ] **Step 3: Verify a tagged install (pokeball — the richest: sprites + emoji)**

```bash
cd /tmp && rm -rf p2c-verify && python3.14 -m venv p2c-verify && . /tmp/p2c-verify/bin/activate
pip install -q -e /Users/james/projects/github/jamesawesome/led-ticker
pip list --format=freeze > /tmp/constraints-core.txt
pip install -c /tmp/constraints-core.txt \
  "git+https://github.com/JamesAwesome/led-ticker-plugins.git@pokeball-v0.1.0#subdirectory=plugins/pokeball"
python -c "
from importlib.metadata import entry_points, version
from pathlib import Path
import led_ticker_pokeball
assert any(e.name=='pokeball' for e in entry_points(group='led_ticker.plugins')), 'pokeball missing'
spr = Path(led_ticker_pokeball.__file__).parent / 'sprites'
assert (spr/'pokeball.gif').is_file(), 'sprite not bundled in wheel'
print('led-ticker pinned at', version('led-ticker'), '| pokeball registers + sprite bundled at tag')
"
deactivate; rm -rf /tmp/p2c-verify /tmp/constraints-core.txt
```
Expected: install succeeds with plain `pip` under constraint; led-ticker stays pinned; pokeball registers AND its sprite ships in the wheel.

---

## Self-review

**Spec coverage (P2c slice):**
- arcade → 4 family packages, history-preserving, with the finalized renames → Tasks 1–4. ✓
- `:arcade.pokeball:` → `:pokeball.ball:` (lo + hi-res) → Task 4. ✓
- Sprite assets travel with their family + ship in the wheel → Tasks 3–4 (incl. tagged-install sprite check, Task 6). ✓
- Per-plugin namespaced tags → Task 6. ✓
- No `arcade.*` types remain; all 4 families resolve → Task 5 Step 2. ✓
- led-ticker-arcade archival + engine catalog flip → out of scope (P3). ✓

**Placeholder scan:** No TBD/TODO. Tasks 2 and 5/6 reference pacman's pyproject/README as the exact template with the precise substitutions enumerated (name/description/entry/wheel/version/deps) — that's a parameter list, not a "similar to Task N" hand-wave. `<PR#>` is a runtime value. ✓

**Type/name consistency:** package dirs / import packages / register names / tags are listed once in the parameter table and reused identically; the four `__init__.py` blocks use the exact class names confirmed from the source (`NyanCat*`/`Pokeball*`/`Pacman*`/`SailorMoon*`); transition names are uniformly `forward`/`reverse`/`alternating`; the emoji slug is `ball` (→ `pokeball.ball`) everywhere. ✓

**Pitfalls flagged inline:** filter-repo fresh-clone + two passes per family; the moved `__init__.py` is the all-4-families arcade one and MUST be overwritten to register only its family; sprites must be in the `--path` list (nyancat, pokeball) or they won't travel; `test_packaging.py` must be trimmed per package (no cross-family sprite assertions); `test_emoji.py` slug expectation updated to `ball`; `sed -i ''` macOS form; merge with `--merge`; plain `pip`; never main; no merge/tag without consent.
