# Monorepo P2b — feeds split → `rss` + `weather` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the `led-ticker-feeds` plugin into two independent monorepo packages — `rss` (`rss.feed`) and `weather` (`weather.current`) — history-preserving, applying the finalized breaking renames.

**Architecture:** `feeds` has zero shared local code (`rss.py` and `weather.py` import only stdlib + their own third-party deps + `led_ticker.plugin`; `__init__.py` just registers both). So each widget becomes a fully self-contained workspace member. History is preserved by running `git filter-repo` once per target package: prune the source clone to that widget's files, rename the package dir (`led_ticker_feeds` → `led_ticker_rss` / `led_ticker_weather`), drop it under `plugins/<name>/`, merge into the monorepo, then write fresh scaffolding (`__init__.py` register, `pyproject.toml`, README/CLAUDE) and fix test imports.

**Tech Stack:** Python 3.14, uv workspace, hatchling, pytest, ruff, pyright, `git filter-repo`.

**Scope:** P2b only — the feeds split. Arcade (P2c) and P3/P4 are separate. The breaking renames (`feeds.rss`→`rss.feed`, `feeds.weather`→`weather.current`) stay invisible to deployed signs until P3 flips the engine catalog, so landing them now is safe. The old `led-ticker-feeds` repo is archived in P3, not here. See `docs/superpowers/specs/2026-06-19-led-ticker-plugins-monorepo-design.md`.

**Working repo:** `/Users/james/projects/github/jamesawesome/led-ticker-plugins`. Create branch `feat/monorepo-p2b-feeds-split` off `main` (which now has P1+P2a merged). All work on that branch, never `main`. Source repo: `/Users/james/projects/github/jamesawesome/led-ticker-feeds`. `git filter-repo` is installed.

**Rename map (finalized 2026-06-19):**
| old | new package | import package | new type | register call |
|---|---|---|---|---|
| `feeds.rss` (RSSFeedMonitor) | `rss` | `led_ticker_rss` | `rss.feed` | `api.widget("feed")` |
| `feeds.weather` (WeatherWidget) | `weather` | `led_ticker_weather` | `weather.current` | `api.widget("current")` |

Dependency split: `rss` → `led-ticker`, `aiohttp`, `feedparser>=6.0`. `weather` → `led-ticker`, `aiohttp` (no feedparser). Both packages keep version `0.2.0` (inherited code maturity from feeds v0.2.0).

---

## File structure

```
plugins/rss/
  pyproject.toml                       # new: led-ticker-rss, entry rss=led_ticker_rss:register
  src/led_ticker_rss/__init__.py       # new: registers rss.feed
  src/led_ticker_rss/rss.py            # moved from feeds (history preserved)
  tests/{test_rss,test_import_purity,test_smoke,conftest}.py   # moved, imports fixed
  README.md / CLAUDE.md                # new (rss-specific)
plugins/weather/
  pyproject.toml                       # new: led-ticker-weather, entry weather=led_ticker_weather:register
  src/led_ticker_weather/__init__.py   # new: registers weather.current
  src/led_ticker_weather/weather.py    # moved from feeds (history preserved)
  tests/{test_weather,test_weather_icons,test_import_purity,test_smoke,conftest}.py  # moved, imports fixed
  README.md / CLAUDE.md                # new (weather-specific)
```
No change to root `pyproject.toml`, `ci.yml` (matrix auto-discovers), or `tests/stubs/`.

---

### Task 1: Split out the `rss` package

**Files:** Create `plugins/rss/**` (rss.py + tests moved with history; new scaffolding).

- [ ] **Step 1: Create the branch (first task only)**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-plugins
git checkout main && git pull --ff-only origin main
git checkout -b feat/monorepo-p2b-feeds-split
git branch --show-current   # MUST be feat/monorepo-p2b-feeds-split — if main, STOP
```

- [ ] **Step 2: filter-repo the rss slice (prune + rename package), then subdir it**

```bash
cd /Users/james/projects/github/jamesawesome
rm -rf /tmp/rss-fr
git clone led-ticker-feeds /tmp/rss-fr
cd /tmp/rss-fr
git filter-repo --force \
  --path src/led_ticker_feeds/__init__.py \
  --path src/led_ticker_feeds/rss.py \
  --path tests/test_rss.py \
  --path tests/test_import_purity.py \
  --path tests/test_smoke.py \
  --path tests/conftest.py \
  --path-rename src/led_ticker_feeds/:src/led_ticker_rss/
git filter-repo --force --to-subdirectory-filter plugins/rss
git log --oneline -- plugins/rss/src/led_ticker_rss/rss.py | tail -2   # ORIGINAL feeds commits touching rss.py
```
Expected: only the rss-relevant files remain, under `plugins/rss/`, with the package dir renamed to `led_ticker_rss`, history preserved for `rss.py`.

- [ ] **Step 3: Merge into the monorepo**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-plugins
git remote add rss-fr /tmp/rss-fr
git fetch rss-fr
git merge --allow-unrelated-histories --no-edit rss-fr/main
git remote remove rss-fr
ls plugins/rss/src/led_ticker_rss/   # __init__.py, rss.py
find plugins/rss -name '__pycache__' -type d -prune -exec rm -rf {} +
```

- [ ] **Step 4: Write the rss `__init__.py` (register `rss.feed`)**

Overwrite `/Users/james/projects/github/jamesawesome/led-ticker-plugins/plugins/rss/src/led_ticker_rss/__init__.py`:
```python
"""led-ticker-rss: RSS/Atom headline widget (rss.feed) contributed via the
``led_ticker.plugins`` entry point.

The entry-point name ``rss`` is the plugin namespace, so the widget is
referenced in config.toml as ``type = "rss.feed"``.
"""

from led_ticker_rss.rss import RSSFeedMonitor


def register(api):
    api.widget("feed")(RSSFeedMonitor)
```

- [ ] **Step 5: Write the rss `pyproject.toml`**

Create `/Users/james/projects/github/jamesawesome/led-ticker-plugins/plugins/rss/pyproject.toml`:
```toml
[project]
name = "led-ticker-rss"
version = "0.2.0"
description = "RSS/Atom headline widget for led-ticker (rss.feed)."
readme = "README.md"
requires-python = ">=3.14"
authors = [{ name = "James Awesome", email = "james@morelli.nyc" }]
dependencies = [
    "led-ticker",
    "aiohttp",
    "feedparser>=6.0",
]

# Entry-point NAME ("rss") is the plugin namespace -> TOML `type = "rss.feed"`.
[project.entry-points."led_ticker.plugins"]
rss = "led_ticker_rss:register"

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
packages = ["src/led_ticker_rss"]

[tool.ruff]
target-version = "py314"
src = ["src"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]

[tool.coverage.report]
fail_under = 90
```
(No `[tool.uv.sources]` / `[tool.pytest.ini_options]` / `[tool.pyright]` — the workspace root owns those.)

- [ ] **Step 6: Fix test imports (`led_ticker_feeds` → `led_ticker_rss`)**

In each of `plugins/rss/tests/test_rss.py`, `tests/conftest.py`, `tests/test_import_purity.py`, `tests/test_smoke.py`, replace every `led_ticker_feeds` with `led_ticker_rss`:
```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-plugins
grep -rl 'led_ticker_feeds' plugins/rss/tests | xargs sed -i '' 's/led_ticker_feeds/led_ticker_rss/g'
grep -rn 'led_ticker_feeds' plugins/rss/   # MUST return nothing
```
(`sed -i ''` is the BSD/macOS form. On Linux use `sed -i`.) `test_import_purity.py` likely asserts the package imports only from `led_ticker.plugin` — confirm it now references `led_ticker_rss` and still passes.

- [ ] **Step 7: Write a minimal rss `README.md` + `CLAUDE.md`**

`plugins/rss/README.md`:
```markdown
# led-ticker-rss

RSS/Atom headline widget for [led-ticker](https://github.com/JamesAwesome/led-ticker) — `type = "rss.feed"`.

Part of the [led-ticker-plugins](https://github.com/JamesAwesome/led-ticker-plugins) monorepo. Install:

```bash
pip install "git+https://github.com/JamesAwesome/led-ticker-plugins.git@rss-v0.2.0#subdirectory=plugins/rss"
```

Split out of the former `led-ticker-feeds` plugin (was `feeds.rss`).
```

`plugins/rss/CLAUDE.md`:
```markdown
# CLAUDE.md — led-ticker-rss

`rss.feed`: an `RSSFeedMonitor` (`src/led_ticker_rss/rss.py`) that fetches an RSS/Atom feed and expands stories into scrolling messages. Registered via `register(api)` in `__init__.py` as `api.widget("feed")` → namespace `rss`.

- Imports ONLY from `led_ticker.plugin` (public surface) — enforced by `tests/test_import_purity.py`.
- Deps: `aiohttp`, `feedparser`.
- Lint/test from the monorepo root: `make lint` / `uv run pytest plugins/rss`. CI is the root path-filtered matrix.
- No `from __future__ import annotations` (PEP 649 / Python 3.14 rule).
```

- [ ] **Step 8: Sync + verify green from the repo root**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-plugins
uv sync --extra dev
uv run pytest plugins/rss -v
uv run ruff check plugins/rss
uv run ruff format --check plugins/rss
uv run pyright plugins/rss/src
```
Expected: all rss tests PASS, ruff + pyright clean. If `ruff format --check` flags the new files, run `uv run ruff format plugins/rss` and re-check.

- [ ] **Step 9: Confirm it registers as `rss.feed`**

```bash
uv run python -c "
import led_ticker._plugin_loader as L
from led_ticker.widgets import _WIDGET_REGISTRY
L.load_plugins(None)
assert 'rss.feed' in _WIDGET_REGISTRY, sorted(k for k in _WIDGET_REGISTRY if 'rss' in k or 'feed' in k)
print('rss.feed registered OK')
"
```

- [ ] **Step 10: Commit**

```bash
git add -A
git commit -m "feat(rss): split led-ticker-feeds rss widget into the rss package (feeds.rss -> rss.feed)"
```

---

### Task 2: Split out the `weather` package

**Files:** Create `plugins/weather/**` (weather.py + tests moved with history; new scaffolding).

- [ ] **Step 1: Branch check**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-plugins
git branch --show-current   # MUST be feat/monorepo-p2b-feeds-split — if main, STOP
```

- [ ] **Step 2: filter-repo the weather slice (prune + rename package), then subdir it**

```bash
cd /Users/james/projects/github/jamesawesome
rm -rf /tmp/weather-fr
git clone led-ticker-feeds /tmp/weather-fr
cd /tmp/weather-fr
git filter-repo --force \
  --path src/led_ticker_feeds/__init__.py \
  --path src/led_ticker_feeds/weather.py \
  --path tests/test_weather.py \
  --path tests/test_weather_icons.py \
  --path tests/test_import_purity.py \
  --path tests/test_smoke.py \
  --path tests/conftest.py \
  --path-rename src/led_ticker_feeds/:src/led_ticker_weather/
git filter-repo --force --to-subdirectory-filter plugins/weather
git log --oneline -- plugins/weather/src/led_ticker_weather/weather.py | tail -2   # ORIGINAL feeds commits
```

- [ ] **Step 3: Merge into the monorepo**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-plugins
git remote add weather-fr /tmp/weather-fr
git fetch weather-fr
git merge --allow-unrelated-histories --no-edit weather-fr/main
git remote remove weather-fr
ls plugins/weather/src/led_ticker_weather/   # __init__.py, weather.py
find plugins/weather -name '__pycache__' -type d -prune -exec rm -rf {} +
```

- [ ] **Step 4: Write the weather `__init__.py` (register `weather.current`)**

Overwrite `/Users/james/projects/github/jamesawesome/led-ticker-plugins/plugins/weather/src/led_ticker_weather/__init__.py`:
```python
"""led-ticker-weather: current-conditions widget (weather.current) contributed
via the ``led_ticker.plugins`` entry point.

The entry-point name ``weather`` is the plugin namespace, so the widget is
referenced in config.toml as ``type = "weather.current"``.
"""

from led_ticker_weather.weather import WeatherWidget


def register(api):
    api.widget("current")(WeatherWidget)
```

- [ ] **Step 5: Write the weather `pyproject.toml`**

Create `/Users/james/projects/github/jamesawesome/led-ticker-plugins/plugins/weather/pyproject.toml`:
```toml
[project]
name = "led-ticker-weather"
version = "0.2.0"
description = "Current-conditions weather widget for led-ticker (weather.current)."
readme = "README.md"
requires-python = ">=3.14"
authors = [{ name = "James Awesome", email = "james@morelli.nyc" }]
dependencies = [
    "led-ticker",
    "aiohttp",
]

# Entry-point NAME ("weather") is the plugin namespace -> TOML `type = "weather.current"`.
[project.entry-points."led_ticker.plugins"]
weather = "led_ticker_weather:register"

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
packages = ["src/led_ticker_weather"]

[tool.ruff]
target-version = "py314"
src = ["src"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]

[tool.coverage.report]
fail_under = 90
```

- [ ] **Step 6: Fix test imports (`led_ticker_feeds` → `led_ticker_weather`)**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-plugins
grep -rl 'led_ticker_feeds' plugins/weather/tests | xargs sed -i '' 's/led_ticker_feeds/led_ticker_weather/g'
grep -rn 'led_ticker_feeds' plugins/weather/   # MUST return nothing
```
`test_weather_icons.py` imports `from led_ticker_feeds.weather import _match_condition` → now `from led_ticker_weather.weather import _match_condition`.

- [ ] **Step 7: Write a minimal weather `README.md` + `CLAUDE.md`**

`plugins/weather/README.md`:
```markdown
# led-ticker-weather

Current-conditions weather widget for [led-ticker](https://github.com/JamesAwesome/led-ticker) — `type = "weather.current"`. Uses WeatherAPI.com (set `WEATHERAPI_KEY`).

Part of the [led-ticker-plugins](https://github.com/JamesAwesome/led-ticker-plugins) monorepo. Install:

```bash
pip install "git+https://github.com/JamesAwesome/led-ticker-plugins.git@weather-v0.2.0#subdirectory=plugins/weather"
```

Split out of the former `led-ticker-feeds` plugin (was `feeds.weather`).
```

`plugins/weather/CLAUDE.md`:
```markdown
# CLAUDE.md — led-ticker-weather

`weather.current`: a `WeatherWidget` (`src/led_ticker_weather/weather.py`) that fetches current conditions from WeatherAPI.com (`WEATHERAPI_KEY` env var) and renders label + temperature with separate color providers. Registered in `__init__.py` as `api.widget("current")` → namespace `weather`.

- Imports ONLY from `led_ticker.plugin` (public surface) — enforced by `tests/test_import_purity.py`.
- Weather condition → icon mapping lives in `weather.py` (`_match_condition`); `tests/test_weather_icons.py` covers it.
- Tests set `WEATHERAPI_KEY` via fixture; deps: `aiohttp`.
- Lint/test from the monorepo root: `make lint` / `uv run pytest plugins/weather`. CI is the root path-filtered matrix.
- No `from __future__ import annotations` (PEP 649 / Python 3.14 rule).
```

- [ ] **Step 8: Sync + verify green from the repo root**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-plugins
uv sync --extra dev
uv run pytest plugins/weather -v
uv run ruff check plugins/weather
uv run ruff format --check plugins/weather
uv run pyright plugins/weather/src
```
Expected: all weather tests PASS. Weather tests need `WEATHERAPI_KEY` — if the moved `conftest.py` / a fixture sets it (it did in feeds), they pass as-is; if a test errors on a missing key, the fixture didn't come along — report it (do NOT hardcode a key). Run `uv run ruff format plugins/weather` if format-check flags the new files.

- [ ] **Step 9: Confirm it registers as `weather.current`**

```bash
uv run python -c "
import led_ticker._plugin_loader as L
from led_ticker.widgets import _WIDGET_REGISTRY
L.load_plugins(None)
assert 'weather.current' in _WIDGET_REGISTRY, sorted(k for k in _WIDGET_REGISTRY if 'weather' in k)
print('weather.current registered OK')
"
```

- [ ] **Step 10: Commit**

```bash
git add -A
git commit -m "feat(weather): split led-ticker-feeds weather widget into the weather package (feeds.weather -> weather.current)"
```

---

### Task 3: Verify 6-member workspace + open PR

**Files:** none (verification + PR).

- [ ] **Step 1: Whole-workspace green + member count**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-plugins
ls -d plugins/*/ | sed 's#plugins/##; s#/##'   # baseball calendar crypto pool rss weather (6)
make test     # all 6 members green, coverage >=90 combined
make lint
make format-check
```
Expected: 6 members, all green.

- [ ] **Step 2: Confirm no `feeds.*` types and both new types resolve**

```bash
uv run python -c "
import led_ticker._plugin_loader as L
from led_ticker.widgets import _WIDGET_REGISTRY
L.load_plugins(None)
keys = {k for k in _WIDGET_REGISTRY if '.' in k}
assert 'rss.feed' in keys and 'weather.current' in keys, sorted(keys)
assert not any(k.startswith('feeds.') for k in keys), 'stale feeds.* type still present'
print('split OK — rss.feed + weather.current present, no feeds.*')
"
```

- [ ] **Step 3: Push and open the PR (no merge without consent)**

```bash
git push -u origin feat/monorepo-p2b-feeds-split
gh pr create --repo JamesAwesome/led-ticker-plugins --base main --head feat/monorepo-p2b-feeds-split \
  --title "P2b: split feeds into rss + weather (breaking renames)" \
  --body "Splits led-ticker-feeds into two independent monorepo packages, history-preserving. BREAKING type renames (finalized 2026-06-19): feeds.rss -> rss.feed, feeds.weather -> weather.current. Invisible to deployed signs until P3 flips the engine catalog; the led-ticker-feeds repo is archived in P3. Do NOT merge without consent; tags rss-v0.2.0 / weather-v0.2.0 come after merge."
```

- [ ] **Step 4: Confirm CI green**

```bash
gh pr checks <PR#> --repo JamesAwesome/led-ticker-plugins
```
Expected: matrix runs all 6 members (root pyproject unchanged here, but new plugins/ dirs changed → at minimum rss + weather; a root change would run all). `check (rss)` + `check (weather)` green; `ci-passed` green.

---

### Task 4: (CONSENT-GATED) Merge + cut tags + verify a tagged install

> Do NOT perform any step until the user explicitly approves the merge.

- [ ] **Step 1: Merge with a MERGE COMMIT (preserve history — never squash)**

```bash
gh pr merge <PR#> --repo JamesAwesome/led-ticker-plugins --merge --delete-branch
git checkout main && git pull --ff-only origin main
git log --oneline -- plugins/rss/src/led_ticker_rss/rss.py | tail -2   # original feeds history present
```

- [ ] **Step 2: Cut the two namespaced tags**

```bash
git tag rss-v0.2.0
git tag weather-v0.2.0
git push origin rss-v0.2.0 weather-v0.2.0
```

- [ ] **Step 3: Verify tagged installs (both)**

```bash
cd /tmp && rm -rf p2b-verify && python3.14 -m venv p2b-verify && . /tmp/p2b-verify/bin/activate
pip install -q -e /Users/james/projects/github/jamesawesome/led-ticker
pip list --format=freeze > /tmp/constraints-core.txt
for pkg in rss weather; do
  pip install -c /tmp/constraints-core.txt \
    "git+https://github.com/JamesAwesome/led-ticker-plugins.git@$pkg-v0.2.0#subdirectory=plugins/$pkg"
done
python -c "
from importlib.metadata import entry_points, version
names = {e.name for e in entry_points(group='led_ticker.plugins')}
assert {'rss','weather'} <= names, names
print('led-ticker pinned at', version('led-ticker'), '| rss + weather register at their tags')
"
deactivate; rm -rf /tmp/p2b-verify /tmp/constraints-core.txt
```
Expected: both install with plain `pip` under the constraint; led-ticker stays pinned; rss + weather register.

---

## Self-review

**Spec coverage (P2b slice):**
- feeds → `rss` + `weather` split, history-preserving, with the finalized renames → Tasks 1–2. ✓
- Dependency split (feedparser → rss only) → Task 1 Step 5 / Task 2 Step 5. ✓
- Per-plugin namespaced tags → Task 4. ✓
- No `feeds.*` types remain; both new types resolve → Task 3 Step 2. ✓
- led-ticker-feeds repo archival + engine catalog flip → out of scope (P3). ✓

**Placeholder scan:** No TBD/TODO; every step has exact code/commands. `<PR#>` is a runtime value from `gh pr create` output. The README/CLAUDE bodies are complete, not sketches. ✓

**Type/name consistency:** `rss`/`weather` package names, `led_ticker_rss`/`led_ticker_weather` import packages, `rss.feed`/`weather.current` types, `api.widget("feed")`/`api.widget("current")` register calls, and `rss-v0.2.0`/`weather-v0.2.0` tags are used identically across Tasks 1–4. The dependency split (feedparser in rss only) matches the source-repo analysis. ✓

**Pitfalls flagged inline:** filter-repo needs a fresh clone per package and runs twice (prune+rename, then subdir); the moved `__init__.py` is the dual-register feeds one and MUST be overwritten; `sed -i ''` is macOS form; weather tests need the `WEATHERAPI_KEY` fixture to travel (report if not); merge with `--merge` not squash; plain `pip` for tagged install; never commit on main; no merge/tag without consent.
