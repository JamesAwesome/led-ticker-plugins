# Plugins Monorepo — P0 Spike + P1 Crypto Pilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove the constraint-based `#subdirectory=` install + entry-point registration works (P0 gate), then fold `crypto` into the `led-ticker-plugins` uv-workspace monorepo end-to-end (P1 pilot) so the entire pipeline — workspace, vendored test stub, single CI matrix, namespaced-tag release, real install — is validated on the smallest plugin before the bulk fold-in.

**Architecture:** `led-ticker-plugins` becomes a uv **virtual workspace** (root has `[tool.uv.workspace]`, no `[build-system]`) whose members live under `plugins/*`. The engine (`led-ticker`) stays a sibling checkout, sourced once at the workspace root via `[tool.uv.sources]`. The rgbmatrix test stub is **vendored** into `tests/stubs/` (interim, until led-ticker#233 ships `led_ticker.testkit`). One root `ci.yml` runs a path-filtered per-member matrix. Plugin history is preserved via `git filter-repo --to-subdirectory-filter`.

**Tech Stack:** Python 3.14, uv workspaces, hatchling, pytest + pytest-asyncio, ruff, pyright, `git filter-repo`, GitHub Actions.

**Scope:** This plan covers **P0 and P1 only**. P2 (bulk fold-in + feeds/arcade splits), P3 (distribution + engine PR + archival), and P4 (hardware smoke) are deferred to follow-up plans written *after* the P0 gate clears and the naming brainstorm finalizes split names. See `docs/superpowers/specs/2026-06-19-led-ticker-plugins-monorepo-design.md`.

**Working repo:** `/Users/james/projects/github/jamesawesome/led-ticker-plugins`. All work on a branch, never `main`. Tasks assume a sibling `../led-ticker` checkout exists.

---

## File structure (created/modified across P1)

- `pyproject.toml` (root) — uv virtual workspace + `led-ticker` source + ruff/pyright/pytest config. **Create.**
- `tests/stubs/rgbmatrix/__init__.py`, `tests/stubs/rgbmatrix/graphics.py` — vendored stub. **Create (copied).**
- `tests/stubs/README.md` — provenance + #233 swap note. **Create.**
- `plugins/crypto/**` — crypto package, moved with history. **Create (via filter-repo).**
- `plugins/crypto/pyproject.toml` — drop per-member stub path + `[tool.uv.sources]`; inherit from root. **Modify.**
- `.github/workflows/ci.yml` — single path-filtered matrix. **Create.**
- `Makefile` (root) — `dev` / `test` / `lint` / `format` targets. **Create.**
- `README.md` (root) — monorepo overview. **Modify.**
- `docs/spike/p0-install-model.md` — spike results + GO/NO-GO record. **Create.**

---

## P0 — Install-model spike (HARD GATE)

> Outcome gates everything. If any P0 step fails, STOP and report — do not start P1.

### Task 0.1: Confirm `LED_TICKER_DEPLOY_KEY` scope

**Files:**
- Create: `docs/spike/p0-install-model.md`

- [ ] **Step 1: Inspect what the deploy key authorizes**

The secret value is unreadable by design. Determine scope from how it's *used* and what deploy keys exist on the engine repo.

Run:
```bash
gh secret list --repo JamesAwesome/led-ticker-plugins
gh repo deploy-key list --repo JamesAwesome/led-ticker 2>/dev/null || \
  gh api repos/JamesAwesome/led-ticker/keys --jq '.[].title,.[].read_only'
grep -rn 'LED_TICKER_DEPLOY_KEY' ../led-ticker-crypto/.github ../led-ticker-baseball/.github
```
Expected: the secret exists on `led-ticker-plugins`; a read-only deploy key titled for plugin CI exists on `led-ticker`; existing plugin CI uses the key only to **checkout `led-ticker` as a sibling** (read-only). It does NOT push or publish.

- [ ] **Step 2: Record findings**

Write to `docs/spike/p0-install-model.md` a "Deploy key scope" section stating: read-only checkout of `led-ticker`; the consolidated CI uses it the same way; publish/deploy is out of its scope (so any future PyPI/Pi-push leg needs a different credential). Commit:
```bash
git add docs/spike/p0-install-model.md
git commit -m "docs(spike): record LED_TICKER_DEPLOY_KEY scope (read-only led-ticker checkout)"
```

### Task 0.2: Prove constraint-based `#subdirectory=` install + entry-point registration

**Files:**
- Modify: `docs/spike/p0-install-model.md`

- [ ] **Step 1: Push a throwaway crypto copy to a spike branch**

A real install needs the package reachable at `plugins/crypto/` on a pushed ref. Use a disposable branch (deleted after the spike; P1 does the real history-preserving move).
```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-plugins
git checkout -b spike/install-model
mkdir -p plugins
cp -R ../led-ticker-crypto plugins/crypto
rm -rf plugins/crypto/.git plugins/crypto/.github plugins/crypto/uv.lock plugins/crypto/**/__pycache__
git add plugins/crypto
git commit -m "spike: throwaway crypto copy for install-model test (do not merge)"
git push -u origin spike/install-model
SPIKE_SHA=$(git rev-parse HEAD); echo "$SPIKE_SHA"
```
Expected: branch pushed; `$SPIKE_SHA` printed.

- [ ] **Step 2: Build a clean env that mimics production (led-ticker pre-installed + constraints)**

```bash
cd /tmp && rm -rf spike-venv && python3.14 -m venv spike-venv && . spike-venv/bin/activate
pip install -q --upgrade pip
# Engine installed first (as in Docker Layer 2), then frozen to a constraints file (Layer 2b).
pip install -q -e /Users/james/projects/github/jamesawesome/led-ticker
pip list --format=freeze > /tmp/constraints-core.txt
```
Expected: `led-ticker` installed; `/tmp/constraints-core.txt` written.

- [ ] **Step 3: Install crypto from the git subdirectory under the constraint (the actual test)**

```bash
pip install -c /tmp/constraints-core.txt \
  "git+https://github.com/JamesAwesome/led-ticker-plugins.git@spike/install-model#subdirectory=plugins/crypto"
```
Expected: install succeeds; pip does NOT try to move led-ticker off its pinned version (the constraint holds); crypto's `[tool.uv.sources]` is ignored by pip (uv-only metadata) and `led-ticker` resolves to the already-installed engine.
If it fails because pip cannot satisfy `led-ticker` (private, not on an index): record the exact error — the fix is that production always pre-installs led-ticker, which this step reproduces, so a failure here is a real finding.

- [ ] **Step 4: Verify entry-point auto-registration**

```bash
python -c "
from importlib.metadata import entry_points
eps = [e for e in entry_points(group='led_ticker.plugins')]
print('entry points:', [(e.name, e.value) for e in eps])
assert any(e.name == 'crypto' for e in eps), 'crypto entry point missing'
"
led-ticker plugin list 2>/dev/null || echo "(CLI list optional — entry point assert above is the gate)"
```
Expected: `crypto = led_ticker_crypto:register` present; assert passes.

- [ ] **Step 5: Record GO/NO-GO and clean up the spike branch**

Append a "GO/NO-GO" verdict + the exact commands/outputs to `docs/spike/p0-install-model.md`. Then:
```bash
deactivate; rm -rf /tmp/spike-venv /tmp/constraints-core.txt
cd /Users/james/projects/github/jamesawesome/led-ticker-plugins
git push origin --delete spike/install-model
git checkout main && git branch -D spike/install-model
git checkout spec/monorepo-consolidation  # or the P1 branch once created
git add docs/spike/p0-install-model.md && git commit -m "docs(spike): record P0 install-model GO/NO-GO verdict"
```
Expected: spike branch gone; verdict committed.

> **GATE:** Proceed to P1 only if Step 3 + Step 4 both succeeded. Otherwise STOP and report the finding.

---

## P1 — Crypto pilot (full pipeline on one plugin)

> Create the P1 work branch first:
> ```bash
> cd /Users/james/projects/github/jamesawesome/led-ticker-plugins
> git checkout main && git checkout -b feat/monorepo-p1-crypto-pilot
> git branch --show-current   # MUST print feat/monorepo-p1-crypto-pilot, never main
> ```

### Task 1.1: Vendor the rgbmatrix stub

**Files:**
- Create: `tests/stubs/rgbmatrix/__init__.py`, `tests/stubs/rgbmatrix/graphics.py`, `tests/stubs/README.md`

- [ ] **Step 1: Copy the stub from the engine**

```bash
mkdir -p tests/stubs/rgbmatrix
cp ../led-ticker/tests/stubs/rgbmatrix/__init__.py tests/stubs/rgbmatrix/__init__.py
cp ../led-ticker/tests/stubs/rgbmatrix/graphics.py  tests/stubs/rgbmatrix/graphics.py
```
Expected: two files copied.

- [ ] **Step 2: Document provenance + the #233 swap**

Create `tests/stubs/README.md`:
```markdown
# Vendored rgbmatrix test stub

Copied verbatim from `led-ticker/tests/stubs/rgbmatrix/` so this repo's tests
run without a sibling `../led-ticker` checkout on the test path.

**Interim.** When led-ticker#233 ships `led_ticker.testkit`, delete this
directory and import the stub from the installed package instead (update the
root `pyproject.toml` pytest `pythonpath` / pyright `extraPaths`). Tracked in
`docs/superpowers/specs/2026-06-19-led-ticker-plugins-monorepo-design.md`.

Do not edit this copy to diverge from the engine's stub.
```

- [ ] **Step 3: Commit**

```bash
git add tests/stubs
git commit -m "test: vendor rgbmatrix stub (interim, pre-#233 testkit)"
```

### Task 1.2: Create the uv virtual workspace root

**Files:**
- Create: `pyproject.toml` (root)

- [ ] **Step 1: Write the root `pyproject.toml`**

```toml
# Virtual workspace root: no [build-system], so uv treats this as a
# non-package workspace whose real packages live under plugins/*.
[tool.uv.workspace]
members = ["plugins/*"]

# The engine is a sibling checkout, sourced once here for the whole workspace.
# pip/git installs ignore this (uv-only metadata) and resolve led-ticker from
# the pre-installed, constraint-pinned engine — see docs/spike/p0-install-model.md.
[tool.uv.sources]
led-ticker = { path = "../led-ticker", editable = true }

[tool.ruff]
target-version = "py314"
src = ["plugins"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]

[tool.pyright]
pythonPlatform = "All"
pythonVersion = "3.14"
extraPaths = ["tests/stubs"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
# Vendored stub on the import path; run pytest from the repo root.
pythonpath = ["tests/stubs"]

[tool.coverage.report]
fail_under = 90
```

- [ ] **Step 2: Commit**

```bash
git add pyproject.toml
git commit -m "build: uv virtual workspace root (members=plugins/*, led-ticker sibling source)"
```

### Task 1.3: Fold crypto in, history-preserving

**Files:**
- Create: `plugins/crypto/**` (moved from `led-ticker-crypto` with history)

- [ ] **Step 1: Produce a history-rewritten clone of crypto under `plugins/crypto/`**

`git filter-repo` requires a fresh clone (refuses to run on a repo with a remote/working changes).
```bash
cd /Users/james/projects/github/jamesawesome
git clone led-ticker-crypto /tmp/crypto-fr
cd /tmp/crypto-fr
git filter-repo --to-subdirectory-filter plugins/crypto --force
git log --oneline -1 -- plugins/crypto   # history now rooted under plugins/crypto/
```
Expected: every crypto path is now prefixed `plugins/crypto/`.

- [ ] **Step 2: Merge crypto's rewritten history into the monorepo**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-plugins
git remote add crypto-fr /tmp/crypto-fr
git fetch crypto-fr
git merge --allow-unrelated-histories --no-edit crypto-fr/main
git remote remove crypto-fr
ls plugins/crypto/src/led_ticker_crypto/   # coingecko.py, _colors.py, _ticker_render.py, __init__.py
git log --oneline -- plugins/crypto | tail -3   # original crypto commits present
```
Expected: crypto files under `plugins/crypto/`, original commit messages preserved.

- [ ] **Step 3: Remove artifacts that don't belong in a workspace member**

```bash
rm -f plugins/crypto/uv.lock
rm -rf plugins/crypto/.github
find plugins/crypto -name '__pycache__' -type d -prune -exec rm -rf {} +
git add -A
git commit -m "chore(crypto): drop per-repo uv.lock + ci (workspace owns these now)"
```

### Task 1.4: Re-point crypto's pyproject at the workspace

**Files:**
- Modify: `plugins/crypto/pyproject.toml`

- [ ] **Step 1: Remove the per-member sibling-stub path and `[tool.uv.sources]`**

Delete these blocks from `plugins/crypto/pyproject.toml` (the root now owns the stub path, the led-ticker source, ruff/pyright/pytest config):
```toml
[tool.uv.sources]
led-ticker = { path = "../led-ticker", editable = true }

[tool.pytest.ini_options]
asyncio_mode = "auto"
pythonpath = ["../led-ticker/tests/stubs"]

[tool.pyright]
pythonPlatform = "All"
pythonVersion = "3.14"
extraPaths = ["../led-ticker/tests/stubs"]
```
Keep `[project]`, `[project.entry-points."led_ticker.plugins"]`, `[project.optional-dependencies]`, `[build-system]`, `[tool.hatch.build.targets.wheel]`, `[tool.ruff*]`, `[tool.coverage.report]`.

- [ ] **Step 2: Sync the workspace**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-plugins
uv sync --extra dev
```
Expected: one root `uv.lock` written; `led_ticker_crypto` resolved as a workspace member; `led-ticker` resolved editable from `../led-ticker`.

- [ ] **Step 3: Run crypto's tests from the repo root against the vendored stub**

```bash
uv run pytest plugins/crypto -v
```
Expected: all crypto tests PASS (they imported the rgbmatrix stub via the root `pythonpath = ["tests/stubs"]`). If a test imported the stub by a sibling path, it now resolves from the vendored copy — no test edit should be needed.

- [ ] **Step 4: Lint + typecheck from root**

```bash
uv run ruff check plugins/crypto
uv run ruff format --check plugins/crypto
uv run pyright plugins/crypto/src
```
Expected: all clean.

- [ ] **Step 5: Commit**

```bash
git add plugins/crypto/pyproject.toml uv.lock
git commit -m "build(crypto): inherit stub/led-ticker/test config from workspace root"
```

### Task 1.5: Single path-filtered CI workflow

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Write the consolidated workflow**

This generalizes the crypto CI: detect which `plugins/*` changed, run lint+type+test per changed member (or all on a shared-root change), checking out `led-ticker` as a sibling with `LED_TICKER_DEPLOY_KEY`.
```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  # Compute the member matrix from changed paths. A change under tests/, the
  # root pyproject, or the workflow runs ALL members; otherwise only the
  # plugins/<name> dirs that changed.
  matrix:
    runs-on: ubuntu-latest
    outputs:
      members: ${{ steps.set.outputs.members }}
    steps:
      - uses: actions/checkout@v6.0.3
        with:
          fetch-depth: 0
          path: led-ticker-plugins
      - id: set
        working-directory: led-ticker-plugins
        run: |
          ALL=$(ls -d plugins/*/ | sed 's#plugins/##; s#/##' | jq -R . | jq -cs .)
          BASE="${{ github.event.pull_request.base.sha || github.event.before }}"
          if [ -z "$BASE" ] || ! git cat-file -e "$BASE" 2>/dev/null; then
            echo "members=$ALL" >> "$GITHUB_OUTPUT"; exit 0
          fi
          CHANGED=$(git diff --name-only "$BASE" HEAD)
          if echo "$CHANGED" | grep -qE '^(pyproject.toml|tests/|.github/workflows/ci.yml)'; then
            echo "members=$ALL" >> "$GITHUB_OUTPUT"
          else
            M=$(echo "$CHANGED" | grep -oE '^plugins/[^/]+/' | sed 's#plugins/##; s#/##' | sort -u | jq -R . | jq -cs .)
            [ "$M" = "[]" ] && M="$ALL"
            echo "members=$M" >> "$GITHUB_OUTPUT"
          fi

  check:
    needs: matrix
    if: needs.matrix.outputs.members != '[]'
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        member: ${{ fromJson(needs.matrix.outputs.members) }}
    steps:
      - uses: actions/checkout@v6.0.3
        with:
          path: led-ticker-plugins
      # Sibling engine checkout (private; read-only deploy key) so the
      # workspace led-ticker source resolves and the vendored stub matches.
      - uses: actions/checkout@v6.0.3
        with:
          repository: JamesAwesome/led-ticker
          path: led-ticker
          ssh-key: ${{ secrets.LED_TICKER_DEPLOY_KEY }}
      - uses: astral-sh/setup-uv@v8.2.0
        with:
          python-version: "3.14"
      - name: Sync workspace
        working-directory: led-ticker-plugins
        run: uv sync --extra dev
      - name: Ruff check
        working-directory: led-ticker-plugins
        run: uv run ruff check plugins/${{ matrix.member }}
      - name: Ruff format check
        working-directory: led-ticker-plugins
        run: uv run ruff format --check plugins/${{ matrix.member }}
      - name: Pyright
        working-directory: led-ticker-plugins
        run: uv run pyright plugins/${{ matrix.member }}/src
      - name: Test
        working-directory: led-ticker-plugins
        run: uv run pytest plugins/${{ matrix.member }} --cov=plugins/${{ matrix.member }}/src --cov-report=term-missing

  ci-passed:
    needs: check
    if: always()
    runs-on: ubuntu-latest
    steps:
      - run: |
          if [ "${{ needs.check.result }}" != "success" ]; then
            echo "matrix check did not succeed: ${{ needs.check.result }}"; exit 1
          fi
          echo "all member checks passed"
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: single path-filtered per-member matrix (uses LED_TICKER_DEPLOY_KEY for sibling led-ticker)"
```

### Task 1.6: Root Makefile + README

**Files:**
- Create: `Makefile` (root)
- Modify: `README.md` (root)

- [ ] **Step 1: Write the root `Makefile`**

```makefile
.PHONY: dev test lint format

dev:
	uv sync --extra dev

test:
	uv run pytest plugins --cov-report=term-missing

lint:
	uv run ruff check plugins
	uv run pyright plugins/*/src

format:
	uv run ruff format plugins
```

- [ ] **Step 2: Replace the seed README**

```markdown
# led-ticker-plugins

The official first-party plugin pack for [led-ticker](https://github.com/JamesAwesome/led-ticker),
developed together in one uv workspace and **distributed per-plugin** so you
install only what you want.

## Install one plugin

```bash
pip install "git+https://github.com/JamesAwesome/led-ticker-plugins.git@<plugin>-vX.Y.Z#subdirectory=plugins/<plugin>"
```

## Develop

```bash
make dev    # uv sync the whole workspace (needs a sibling ../led-ticker checkout)
make test   # pytest every member
make lint   # ruff + pyright
```

Each plugin lives under `plugins/<name>/` with its own `pyproject.toml`,
version, `CLAUDE.md`, and `README.md`. See
`docs/superpowers/specs/2026-06-19-led-ticker-plugins-monorepo-design.md`.
```

- [ ] **Step 3: Commit**

```bash
git add Makefile README.md
git commit -m "docs: root Makefile + monorepo README"
```

### Task 1.7: Tag crypto + verify the real install end-to-end

**Files:**
- Modify: `docs/spike/p0-install-model.md` (append P1 install verification)

- [ ] **Step 1: Push the branch and open a PR (no merge without consent)**

```bash
git push -u origin feat/monorepo-p1-crypto-pilot
gh pr create --repo JamesAwesome/led-ticker-plugins \
  --title "P1: fold crypto into the monorepo (pilot)" \
  --body "Pilot per the monorepo spec. Proves workspace + vendored stub + path-filtered CI + namespaced-tag install on crypto before the bulk fold-in. Do not merge without explicit consent."
```
Expected: CI runs the matrix with a single `crypto` member and goes green.

- [ ] **Step 2: After merge consent + merge, cut the namespaced tag**

> Only after the user explicitly approves the merge.
```bash
git checkout main && git pull
git tag crypto-v0.1.0
git push origin crypto-v0.1.0
```
Expected: tag `crypto-v0.1.0` pushed.

- [ ] **Step 3: Verify a tagged production-style install**

```bash
cd /tmp && rm -rf p1-venv && python3.14 -m venv p1-venv && . p1-venv/bin/activate
pip install -q -e /Users/james/projects/github/jamesawesome/led-ticker
pip list --format=freeze > /tmp/constraints-core.txt
pip install -c /tmp/constraints-core.txt \
  "git+https://github.com/JamesAwesome/led-ticker-plugins.git@crypto-v0.1.0#subdirectory=plugins/crypto"
python -c "
from importlib.metadata import entry_points
assert any(e.name=='crypto' for e in entry_points(group='led_ticker.plugins')), 'crypto missing'
print('crypto entry point OK at tag crypto-v0.1.0')
"
deactivate; rm -rf /tmp/p1-venv /tmp/constraints-core.txt
```
Expected: install + entry-point assert pass against the **tag** (not a branch).

- [ ] **Step 4: Record the P1 verification + commit on a docs branch**

Append the tagged-install result to `docs/spike/p0-install-model.md`. Commit on a fresh branch and PR (no main edits):
```bash
git checkout -b docs/p1-install-verified
git add docs/spike/p0-install-model.md
git commit -m "docs(spike): P1 tagged-install verified (crypto-v0.1.0)"
```

- [ ] **Step 5: Hardware smoke (optional but recommended for the pilot)**

On a sign (smallsign or bigsign), add the tagged crypto line to its `requirements-plugins.txt`, redeploy, and confirm `led-ticker plugin list` shows `crypto` and a `crypto.coingecko` widget renders. Record pass/fail in the same doc. (Pi-side; cannot be run from CI.)

---

## Self-review

**Spec coverage (P0+P1 slice):**
- P0 install-model spike → Tasks 0.1–0.2 (deploy-key scope + constraint `#subdirectory=` install + entry-point reg + GATE). ✓
- P1 pilot: filter-repo crypto → 1.3; workspace → 1.2/1.4; vendored stub (#233 bridge) → 1.1; single path-filtered CI w/ `LED_TICKER_DEPLOY_KEY` → 1.5; namespaced tag → 1.7; real hardware install → 1.7 step 5. ✓
- P2–P4, feeds/arcade splits, naming, engine PR, archival, core rss/weather removal → explicitly **out of scope** of this plan (deferred follow-up plans). ✓

**Placeholder scan:** No TBD/TODO; every code/command step shows actual content. The only deferral (`led-ticker plugin list` CLI being optional) has the entry-point assert as the hard check. ✓

**Type/name consistency:** `plugins/crypto` member name, `crypto` entry-point/namespace, `crypto-v0.1.0` tag, and `tests/stubs` path are used identically across Tasks 1.1–1.7 and the root `pyproject.toml`. ✓

**Pitfalls flagged inline:** filter-repo needs a fresh clone; pip ignores `[tool.uv.sources]` (led-ticker must be pre-installed + constrained); run pytest from the repo root so the vendored-stub `pythonpath` applies; never edit `main` directly; no merge/tag without explicit consent.
