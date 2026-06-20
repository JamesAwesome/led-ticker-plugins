# Monorepo P2a — Mechanical Fold-ins (pool, baseball, calendar) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fold the three namespace-preserving plugins — `pool`, `baseball`, `calendar` — into the `led-ticker-plugins` monorepo as workspace members under `plugins/<name>/`, history-preserving, with NO type renames, extending the CI matrix to 4 members.

**Architecture:** Each fold-in repeats the proven P1 crypto pattern: `git filter-repo --to-subdirectory-filter plugins/<name>` → merge with `--allow-unrelated-histories` → scrub per-repo `uv.lock`/`.github`/caches → strip the three member pyproject tables the workspace root now owns (`[tool.uv.sources]`, `[tool.pytest.ini_options]`, `[tool.pyright]`) → `uv sync` → tests/lint/typecheck green from the repo root. The single path-filtered CI matrix auto-discovers new `plugins/*` members, so no workflow change is needed.

**Tech Stack:** Python 3.14, uv workspace, hatchling, pytest, ruff, pyright, `git filter-repo`, GitHub Actions.

**Scope:** P2a only — the three 1:1 fold-ins with no renames. The renaming splits are separate plans: **P2b** (feeds → `rss` + `weather`) and **P2c** (arcade → `nyancat`/`pokeball`/`pacman`/`sailor_moon`). P3 (distribution + engine PR + archival) and P4 (hardware smoke) follow. See `docs/superpowers/specs/2026-06-19-led-ticker-plugins-monorepo-design.md`.

**Working repo:** `/Users/james/projects/github/jamesawesome/led-ticker-plugins`, branch `feat/monorepo-p2a-foldins` (already created off main + the naming-finalization commit). All work on that branch, never `main`. Sibling source repos at `/Users/james/projects/github/jamesawesome/led-ticker-{pool,baseball,calendar}`.

**Precondition:** `git filter-repo` is installed (P1 used `uv tool install git-filter-repo`). If missing, install it first.

---

## File structure

Per member `<name>` ∈ {pool, baseball, calendar}:
- Create: `plugins/<name>/**` — moved from `led-ticker-<name>` with preserved history.
- Modify: `plugins/<name>/pyproject.toml` — strip the three root-owned tables.
- No change to `.github/workflows/ci.yml` (matrix auto-discovers members), root `pyproject.toml`, or `tests/stubs/`.

Expected member surfaces (must survive the move, unchanged):
- `pool` → `pool.monitor`
- `baseball` → `baseball.{scores,standings,promotions,statcast,attendance}`, transitions `baseball.{roll,roll_reverse,roll_alternating}`, emoji `:baseball.ball:` (lo + hi-res)
- `calendar` → `calendar.events`

---

### Task 1: Fold in `pool`

**Files:**
- Create: `plugins/pool/**`
- Modify: `plugins/pool/pyproject.toml`

- [ ] **Step 1: Branch check**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-plugins
git branch --show-current   # MUST be feat/monorepo-p2a-foldins — if main, STOP
```

- [ ] **Step 2: History-preserving subdirectory rewrite**

```bash
cd /Users/james/projects/github/jamesawesome
rm -rf /tmp/pool-fr
git clone led-ticker-pool /tmp/pool-fr
cd /tmp/pool-fr
git filter-repo --to-subdirectory-filter plugins/pool --force
git log --oneline | tail -2   # original pool commits, now under plugins/pool/
```

- [ ] **Step 3: Merge into the monorepo**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-plugins
git remote add pool-fr /tmp/pool-fr
git fetch pool-fr
git merge --allow-unrelated-histories --no-edit pool-fr/main
git remote remove pool-fr
ls plugins/pool/src/led_ticker_pool/   # package present
git log --oneline -- plugins/pool | tail -3   # ORIGINAL pool commit messages preserved
```
Expected: pool files under `plugins/pool/`, original history present.

- [ ] **Step 4: Scrub per-repo artifacts**

```bash
rm -f plugins/pool/uv.lock
rm -rf plugins/pool/.github
find plugins/pool -name '__pycache__' -type d -prune -exec rm -rf {} +
find plugins/pool -name '*.pyc' -delete
find plugins/pool -name '.coverage*' -delete
git add -A
git commit -m "chore(pool): drop per-repo uv.lock + ci + caches (workspace owns these now)"
```

- [ ] **Step 5: Strip the three root-owned tables from the member pyproject**

Edit `/Users/james/projects/github/jamesawesome/led-ticker-plugins/plugins/pool/pyproject.toml`: delete the entire `[tool.uv.sources]` table, the entire `[tool.pytest.ini_options]` table (its `pythonpath = ["../led-ticker/tests/stubs"]` is now root-owned; the root sets `asyncio_mode = "auto"` and the stub path), and the entire `[tool.pyright]` table (`extraPaths = ["../led-ticker/tests/stubs"]`, root-owned). KEEP `[project]`, `[project.entry-points."led_ticker.plugins"]`, `[project.optional-dependencies]`, `[build-system]`, `[tool.hatch.build.targets.wheel]`, the `[tool.ruff*]` tables, and `[tool.coverage.report]`.

If the member's `[tool.pytest.ini_options]` contains a setting OTHER than `pythonpath` / `asyncio_mode` (e.g. a custom marker or addopts), do NOT silently drop it — keep that table with only the non-root setting and report it as a concern.

- [ ] **Step 6: Sync + verify green from the repo root**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-plugins
uv sync --extra dev
uv run pytest plugins/pool -v
uv run ruff check plugins/pool
uv run ruff format --check plugins/pool
uv run pyright plugins/pool/src
```
Expected: all pool tests PASS (stub resolves via root `pythonpath=tests/stubs`, no test edits), ruff + pyright clean. If a test fails on the stub import, investigate — it should resolve from the vendored copy; report rather than rewriting tests.

- [ ] **Step 7: Confirm the entry point still registers as `pool.monitor`**

```bash
uv run python -c "
from importlib.metadata import entry_points
assert any(e.name=='pool' for e in entry_points(group='led_ticker.plugins')), 'pool entry point missing'
print('pool entry point OK')
"
```

- [ ] **Step 8: Commit**

```bash
git add plugins/pool/pyproject.toml uv.lock
git commit -m "build(pool): inherit stub/led-ticker/test config from workspace root"
```

---

### Task 2: Fold in `baseball`

> Same mechanism as Task 1, but baseball is the richest surface (5 widgets + 3 `roll*` transitions + the `:baseball.ball:` emoji in lo- and hi-res). Verify ALL of them survive and register.

**Files:**
- Create: `plugins/baseball/**`
- Modify: `plugins/baseball/pyproject.toml`

- [ ] **Step 1: Branch check**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-plugins
git branch --show-current   # MUST be feat/monorepo-p2a-foldins — if main, STOP
```

- [ ] **Step 2: History-preserving subdirectory rewrite**

```bash
cd /Users/james/projects/github/jamesawesome
rm -rf /tmp/baseball-fr
git clone led-ticker-baseball /tmp/baseball-fr
cd /tmp/baseball-fr
git filter-repo --to-subdirectory-filter plugins/baseball --force
git log --oneline | tail -2
```

- [ ] **Step 3: Merge into the monorepo**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-plugins
git remote add baseball-fr /tmp/baseball-fr
git fetch baseball-fr
git merge --allow-unrelated-histories --no-edit baseball-fr/main
git remote remove baseball-fr
ls plugins/baseball/src/led_ticker_baseball/
git log --oneline -- plugins/baseball | tail -3   # ORIGINAL baseball commits
```

- [ ] **Step 4: Scrub per-repo artifacts**

```bash
rm -f plugins/baseball/uv.lock
rm -rf plugins/baseball/.github
find plugins/baseball -name '__pycache__' -type d -prune -exec rm -rf {} +
find plugins/baseball -name '*.pyc' -delete
find plugins/baseball -name '.coverage*' -delete
git add -A
git commit -m "chore(baseball): drop per-repo uv.lock + ci + caches (workspace owns these now)"
```

- [ ] **Step 5: Strip the three root-owned tables from the member pyproject**

Edit `/Users/james/projects/github/jamesawesome/led-ticker-plugins/plugins/baseball/pyproject.toml`: delete the entire `[tool.uv.sources]`, `[tool.pytest.ini_options]`, and `[tool.pyright]` tables (all three root-owned, same as pool). KEEP `[project]` (incl. its `dependencies` — baseball may pull extra deps like an MLB API client; leave them), `[project.entry-points."led_ticker.plugins"]`, `[project.optional-dependencies]`, `[build-system]`, `[tool.hatch.build.targets.wheel]`, `[tool.ruff*]`, `[tool.coverage.report]`. Same caveat as Task 1 Step 5 for any non-root pytest setting.

- [ ] **Step 6: Sync + verify green from the repo root**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-plugins
uv sync --extra dev
uv run pytest plugins/baseball -v
uv run ruff check plugins/baseball
uv run ruff format --check plugins/baseball
uv run pyright plugins/baseball/src
```
Expected: all baseball tests PASS, ruff + pyright clean.

- [ ] **Step 7: Confirm the FULL baseball surface registers (widgets + transitions + emoji)**

```bash
uv run python -c "
import led_ticker._plugin_loader as L
from led_ticker.widgets import _WIDGET_REGISTRY
from led_ticker.transitions import _TRANSITION_REGISTRY
from led_ticker.pixel_emoji import EMOJI_REGISTRY, HIRES_REGISTRY
L.load_plugins()
widgets = {k for k in _WIDGET_REGISTRY if k.startswith('baseball.')}
trans = {k for k in _TRANSITION_REGISTRY if k.startswith('baseball.')}
print('widgets:', sorted(widgets)); print('transitions:', sorted(trans))
assert widgets >= {'baseball.scores','baseball.standings','baseball.promotions','baseball.statcast','baseball.attendance'}, widgets
assert trans >= {'baseball.roll','baseball.roll_reverse','baseball.roll_alternating'}, trans
assert 'baseball.ball' in EMOJI_REGISTRY, 'lo-res emoji missing'
assert 'baseball.ball' in HIRES_REGISTRY, 'hi-res emoji missing'
print('baseball full surface OK')
"
```
Expected: prints the widget/transition lists and `baseball full surface OK`. If `load_plugins()` needs an installed entry point, ensure `uv sync` installed the member editable first (it does). If the registry import paths differ, adapt minimally and report.

- [ ] **Step 8: Commit**

```bash
git add plugins/baseball/pyproject.toml uv.lock
git commit -m "build(baseball): inherit stub/led-ticker/test config from workspace root"
```

---

### Task 3: Fold in `calendar`

**Files:**
- Create: `plugins/calendar/**`
- Modify: `plugins/calendar/pyproject.toml`

- [ ] **Step 1: Branch check**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-plugins
git branch --show-current   # MUST be feat/monorepo-p2a-foldins — if main, STOP
```

- [ ] **Step 2: History-preserving subdirectory rewrite**

```bash
cd /Users/james/projects/github/jamesawesome
rm -rf /tmp/calendar-fr
git clone led-ticker-calendar /tmp/calendar-fr
cd /tmp/calendar-fr
git filter-repo --to-subdirectory-filter plugins/calendar --force
git log --oneline | tail -2
```

- [ ] **Step 3: Merge into the monorepo**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-plugins
git remote add calendar-fr /tmp/calendar-fr
git fetch calendar-fr
git merge --allow-unrelated-histories --no-edit calendar-fr/main
git remote remove calendar-fr
ls plugins/calendar/src/led_ticker_calendar/
git log --oneline -- plugins/calendar | tail -3   # ORIGINAL calendar commits
```

> Note: `led-ticker-calendar` has a top-level `config/` dir. If `git filter-repo` brought it in under `plugins/calendar/config/`, that's fine (it's the plugin's example config). Leave it.

- [ ] **Step 4: Scrub per-repo artifacts**

```bash
rm -f plugins/calendar/uv.lock
rm -rf plugins/calendar/.github
find plugins/calendar -name '__pycache__' -type d -prune -exec rm -rf {} +
find plugins/calendar -name '*.pyc' -delete
find plugins/calendar -name '.coverage*' -delete
git add -A
git commit -m "chore(calendar): drop per-repo uv.lock + ci + caches (workspace owns these now)"
```

- [ ] **Step 5: Strip the three root-owned tables from the member pyproject**

Edit `/Users/james/projects/github/jamesawesome/led-ticker-plugins/plugins/calendar/pyproject.toml`: delete the entire `[tool.uv.sources]`, `[tool.pytest.ini_options]`, and `[tool.pyright]` tables. KEEP the same blocks as Task 1 Step 5. Same caveat for any non-root pytest setting.

- [ ] **Step 6: Sync + verify green from the repo root**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-plugins
uv sync --extra dev
uv run pytest plugins/calendar -v
uv run ruff check plugins/calendar
uv run ruff format --check plugins/calendar
uv run pyright plugins/calendar/src
```
Expected: all calendar tests PASS, ruff + pyright clean.

- [ ] **Step 7: Confirm the entry point still registers as `calendar.events`**

```bash
uv run python -c "
from importlib.metadata import entry_points
assert any(e.name=='calendar' for e in entry_points(group='led_ticker.plugins')), 'calendar entry point missing'
print('calendar entry point OK')
"
```

- [ ] **Step 8: Commit**

```bash
git add plugins/calendar/pyproject.toml uv.lock
git commit -m "build(calendar): inherit stub/led-ticker/test config from workspace root"
```

---

### Task 4: Verify the 4-member workspace + CI matrix, then push & PR

**Files:** none (verification + PR).

- [ ] **Step 1: Whole-workspace green + member count**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-plugins
ls -d plugins/*/ | sed 's#plugins/##; s#/##'   # crypto, pool, baseball, calendar (4)
make test    # pytest across all members with per-member coverage; ALL pass, each >=90%
make lint    # ruff + pyright across all members, clean
make format-check
```
Expected: 4 members, all green. (crypto was P1; pool/baseball/calendar are new.)

- [ ] **Step 2: Sanity-check the CI matrix logic picks up all 4 on a root-level change**

The matrix job emits ALL members when a root/tests/workflow path changes. Simulate the membership computation locally:
```bash
ALL=$(ls -d plugins/*/ | sed 's#plugins/##; s#/##' | jq -R . | jq -cs .)
echo "matrix would run: $ALL"   # ["baseball","calendar","crypto","pool"]
```
Expected: all four listed.

- [ ] **Step 3: Push and open the PR (no merge without consent)**

```bash
git push -u origin feat/monorepo-p2a-foldins
gh pr create --repo JamesAwesome/led-ticker-plugins --base main --head feat/monorepo-p2a-foldins \
  --title "P2a: fold pool, baseball, calendar into the monorepo (mechanical, no renames)" \
  --body "Folds the three namespace-preserving plugins in, history-preserving, mirroring the P1 crypto pilot. No type renames (pool.monitor / baseball.* / calendar.events unchanged). Also finalizes the split type names in the spec (rides in from the branch base). CI matrix extends to 4 members. Do NOT merge without explicit consent; namespaced tags (pool-v0.1.0, baseball-v0.1.0, calendar-v0.1.0) come after merge."
```
Expected: CI runs the matrix with members baseball/calendar/crypto/pool, all green.

- [ ] **Step 4: Confirm CI green**

```bash
gh pr checks <PR#> --repo JamesAwesome/led-ticker-plugins
```
Expected: `matrix` pass; `check (baseball)`, `check (calendar)`, `check (crypto)`, `check (pool)` all pass; `ci-passed` pass.

---

### Task 5: (CONSENT-GATED) Merge + cut namespaced tags + verify one tagged install

> Do NOT perform any step here until the user explicitly approves the merge.

- [ ] **Step 1: Merge with a MERGE COMMIT (preserve history — never squash)**

```bash
gh pr merge <PR#> --repo JamesAwesome/led-ticker-plugins --merge --delete-branch
git checkout main && git pull --ff-only origin main
git log --oneline -- plugins/baseball | tail -3   # original baseball history present on main
```

- [ ] **Step 2: Cut the three namespaced tags**

```bash
git tag pool-v0.1.0
git tag baseball-v0.1.0
git tag calendar-v0.1.0
git push origin pool-v0.1.0 baseball-v0.1.0 calendar-v0.1.0
```
(Each version matches the member pyproject `version = "0.1.0"`. If any differs, use the member's actual version.)

- [ ] **Step 3: Verify a tagged production-style install (baseball — the richest)**

```bash
cd /tmp && rm -rf p2a-verify && python3.14 -m venv p2a-verify && . /tmp/p2a-verify/bin/activate
pip install -q -e /Users/james/projects/github/jamesawesome/led-ticker
pip list --format=freeze > /tmp/constraints-core.txt
pip install -c /tmp/constraints-core.txt \
  "git+https://github.com/JamesAwesome/led-ticker-plugins.git@baseball-v0.1.0#subdirectory=plugins/baseball"
python -c "
from importlib.metadata import entry_points, version
assert any(e.name=='baseball' for e in entry_points(group='led_ticker.plugins')), 'baseball missing'
print('led-ticker pinned at', version('led-ticker'), '; baseball registers at tag baseball-v0.1.0')
"
deactivate; rm -rf /tmp/p2a-verify /tmp/constraints-core.txt
```
Expected: install succeeds with plain `pip` under the constraint; led-ticker stays pinned; baseball registers.

---

## Self-review

**Spec coverage (P2a slice):**
- "P2 bulk fold-in" for the three non-split plugins → Tasks 1–3 (history-preserving, no renames). ✓
- CI matrix extends without a workflow edit → Task 4 (auto-discovery verified). ✓
- Per-plugin namespaced tags → Task 5. ✓
- The feeds/arcade splits, P3 distribution/engine-PR/archival, P4 hardware → explicitly out of scope (P2b/P2c and later plans). ✓

**Placeholder scan:** No TBD/TODO; every step has exact commands. The `<PR#>` token in Tasks 4–5 is a runtime value the executor fills from the `gh pr create` output, not a placeholder for missing content. ✓

**Type/name consistency:** member names `pool`/`baseball`/`calendar`, namespaces unchanged, tags `<name>-v0.1.0`, and the strip-three-tables operation are identical across Tasks 1–3 and match the P1 crypto precedent. The baseball surface assertion in Task 2 Step 7 lists the exact 5 widgets / 3 transitions / 1 emoji confirmed present in the source repo. ✓

**Pitfalls flagged inline:** filter-repo needs a fresh clone; merge with `--merge` not squash (preserve history); strip only root-owned pytest settings (keep + report any unique one); plain `pip` for the tagged install (uv would honor the local path); never commit on main; no merge/tag without consent.
