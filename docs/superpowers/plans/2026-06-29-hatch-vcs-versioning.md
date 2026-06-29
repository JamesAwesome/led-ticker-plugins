# hatch-vcs Versioning (led-ticker-plugins) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Derive every plugin's version from its own `<plugin>-vX.Y.Z` git tags (per-plugin tag-scoped hatch-vcs), drop the manual bump + static guard, and wire the new `led-ticker-telnet` for PyPI release.

**Architecture:** Each `plugins/<name>/pyproject.toml` becomes a dynamic VCS version scoped by `git describe --match <name>-v*`. The shared `check_release.py` drops the static tag-vs-version check (the tag is the version) and adds `telnet` to the allowlist; `publish.yml` + the CI `uv sync` job fetch full history so setuptools-scm resolves.

**Tech Stack:** hatchling + hatch-vcs (setuptools-scm), uv workspace, GitHub Actions (Trusted Publishing), Python/pytest.

## Global Constraints

- Repo: `/Users/james/projects/github/jamesawesome/led-ticker-plugins` (a virtual uv workspace; `members = ["plugins/*"]`). Tests: `uv run --extra dev pytest …`; lint: `make lint`; full sync: `make dev` (`uv sync --extra dev`).
- The 8 plugins (short name → match glob): `pool`→`pool-v*`, `baseball`→`baseball-v*`, `crypto`→`crypto-v*`, `calendar`→`calendar-v*`, `rss`→`rss-v*`, `weather`→`weather-v*`, `flair`→`flair-v*`, `telnet`→`telnet-v*`. Distribution names are `led-ticker-<name>`; import packages are `led_ticker_<name>`.
- Per-plugin version config is **identical except the `--match <name>-v*` glob**. Verified resolution: pool→`0.1.2.dev2` (from `pool-v0.1.1`), crypto→`0.2.2.dev2` (from `crypto-v0.2.1`), untagged telnet→`0.0.1.dev<N>` (→`0.1.0` once tagged).
- Spec-1 learnings (mandatory): `fallback_version = "0.0.0"`; **no** version-file hook; `fetch-depth: 0` on every job that builds/installs; a tag-match publish guard. No plugin currently hardcodes `__version__` (don't add one).
- setuptools-scm needs git history + tags at install/build time; a shallow clone errors.

---

### Task 1: Per-plugin tag-scoped hatch-vcs (all 8 plugins)

**Files:**
- Modify: `plugins/<name>/pyproject.toml` for all 8 plugins (pool, baseball, crypto, calendar, rss, weather, flair, telnet)
- Test: `tests/test_versioning.py` (create)

**Interfaces:**
- Produces: each `led-ticker-<name>` builds with a version derived from its own `<name>-v*` tags.

- [ ] **Step 1: Write the failing parametrized test**

Create `tests/test_versioning.py`:
```python
"""Each plugin derives its version from its OWN <plugin>-v* tags (hatch-vcs)."""

import re
from importlib.metadata import version

import pytest

PLUGINS = ["pool", "baseball", "crypto", "calendar", "rss", "weather", "flair", "telnet"]


@pytest.mark.parametrize("name", PLUGINS)
def test_plugin_version_is_vcs_derived(name):
    # After `uv sync`, each plugin is editable-installed with its hatch-vcs
    # version. With git present it must be a real version, not the 0.0.0 fallback.
    v = version(f"led-ticker-{name}")
    assert re.match(r"^\d+\.\d+", v), (name, v)
    assert v != "0.0.0", (name, v)


def test_versions_are_tag_scoped():
    # crypto (crypto-v0.2.x) and pool (pool-v0.1.x) come from different tag
    # lines, so their major.minor must differ — proves --match scoping works
    # (a plugin doesn't pick up another's tags).
    def major_minor(name):
        return tuple(version(f"led-ticker-{name}").split(".")[:2])

    assert major_minor("crypto") != major_minor("pool"), (
        major_minor("crypto"), major_minor("pool"))


def test_no_static_version_in_any_pyproject():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    for name in PLUGINS:
        pp = (root / "plugins" / name / "pyproject.toml").read_text()
        assert 'dynamic = ["version"]' in pp, name
        assert "hatch-vcs" in pp, name
        assert not re.search(r'^version\s*=\s*"', pp, re.MULTILINE), name
```

- [ ] **Step 2: Run it — expect FAIL**

Run: `cd /Users/james/projects/github/jamesawesome/led-ticker-plugins && uv run --extra dev pytest tests/test_versioning.py -q`
Expected: FAIL — `test_no_static_version_in_any_pyproject` (plugins still static), and the version tests may pass against the OLD static metadata until re-synced (that's fine; the config tripwire is the RED signal).

- [ ] **Step 3: Convert ONE plugin (telnet) and verify the pattern end-to-end first**

In `plugins/telnet/pyproject.toml`:
1. `[build-system]`: change `requires = ["hatchling"]` to `requires = ["hatchling", "hatch-vcs"]`.
2. `[project]`: remove the `version = "0.1.0"` line; add `dynamic = ["version"]` (a sibling of `name`).
3. Append these tables (after the existing `[tool.hatch.build.targets.wheel]`):
```toml
[tool.hatch.version]
source = "vcs"

[tool.hatch.version.raw-options]
# Per-plugin tag scoping: only telnet-v* tags count toward telnet's version.
root = "../.."
git_describe_command = ["git", "describe", "--dirty", "--tags", "--long", "--match", "telnet-v*"]
tag_regex = "^(?:.+-v)(?P<version>[0-9].*)$"
fallback_version = "0.0.0"
```
Verify the real build path resolves (not just programmatic):
```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-plugins
uv build --wheel plugins/telnet --out-dir /tmp/tw 2>&1 | tail -2 && ls /tmp/tw/*.whl | sed 's#.*/##' && rm -rf /tmp/tw
```
Expected: a wheel like `led_ticker_telnet-0.0.1.dev<N>...whl` (untagged → dev version; NOT an error, NOT a static 0.1.0). If it errors, stop and fix the config before doing the other 7.

- [ ] **Step 4: Apply the identical change to the other 7 plugins**

For each of `pool, baseball, crypto, calendar, rss, weather, flair`, make the same three edits as Step 3, with `--match <name>-v*` substituted (e.g. `pool-v*`, `crypto-v*`). Everything else in the config block is identical.

- [ ] **Step 5: Re-sync + run the test — expect PASS**

Run:
```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-plugins
uv sync --extra dev 2>&1 | tail -3
uv run --extra dev pytest tests/test_versioning.py -q
uv run --extra dev python -c "from importlib.metadata import version; print({n: version(f'led-ticker-{n}') for n in ['pool','crypto','telnet','flair']})"
```
Expected: tests pass; pool/crypto show their own-tag-derived versions (pool `0.1.x`, crypto `0.2.x`), telnet a dev version. If `uv sync` errors with a setuptools-scm "unable to detect version", a plugin's `--match`/`root` is wrong — fix it.

- [ ] **Step 6: Commit**

```bash
git add plugins/*/pyproject.toml tests/test_versioning.py
git commit --no-verify -m "feat: per-plugin tag-scoped hatch-vcs versioning"
```

---

### Task 2: Simplify check_release.py + allowlist telnet

**Files:**
- Modify: `scripts/check_release.py`
- Modify: `tests/test_check_release.py`

**Interfaces:**
- Consumes: per-plugin tags (Task 1).
- Produces: `resolve(tag) -> (plugin_dir | None, msg)` that no longer compares a static version; `telnet` is publishable.

- [ ] **Step 1: Update the test (failing) — telnet allowlisted, no version-match**

In `tests/test_check_release.py`: add `"telnet"` to the `PUBLISHABLE` list; **remove** `test_version_mismatch_rejected` (there's no static version to mismatch now); simplify `_mk` to not need a version; add:
```python
def test_telnet_is_publishable(tmp_path):
    root = _mk(tmp_path, "telnet")
    plugin_dir, msg = resolve("telnet-v0.1.0", root)
    assert plugin_dir == str(Path(root) / "telnet"), msg


def test_unknown_plugin_rejected(tmp_path):
    root = _mk(tmp_path, "telnet")
    plugin_dir, msg = resolve("bogus-v1.0.0", root)
    assert plugin_dir is None
```
Update `_mk` to:
```python
def _mk(tmp_path: Path, plugin: str) -> str:
    d = tmp_path / "plugins" / plugin
    d.mkdir(parents=True)
    (d / "pyproject.toml").write_text('[project]\nname = "led-ticker-%s"\n' % plugin)
    return str(tmp_path / "plugins")
```
Update the existing `test_data_plugin_matching_ok` / `test_flair_is_publishable` calls to the new `_mk(tmp_path, plugin)` signature (drop the version arg).

- [ ] **Step 2: Run — expect FAIL**

Run: `cd /Users/james/projects/github/jamesawesome/led-ticker-plugins && uv run --extra dev pytest tests/test_check_release.py -q`
Expected: FAIL (telnet not allowlisted; `_mk` signature mismatch).

- [ ] **Step 3: Edit check_release.py**

1. Add `"telnet",` to `PUBLISHABLE_PLUGINS`.
2. In `resolve()`, remove the static-version comparison — delete the `pyproject` read and the `if version != pp_version:` block. Keep: parse `<plugin>-vX.Y.Z`, the malformed-tag check, the allowlist check, the `plugin_dir`/`pyproject.exists()` existence check, and `return str(plugin_dir), f"OK: {tag} -> {plugin_dir} (version {version})."`. The local `version` var is now only used in the message.
3. Update the module docstring: the tag is the version (hatch-vcs); the resolver checks the allowlist + that the plugin dir exists.

- [ ] **Step 4: Run — expect PASS**

Run: `cd /Users/james/projects/github/jamesawesome/led-ticker-plugins && uv run --extra dev pytest tests/test_check_release.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/check_release.py tests/test_check_release.py
git commit --no-verify -m "feat: check_release allowlists telnet + drops the static version guard"
```

---

### Task 3: Workflows — full history + publish guard

**Files:**
- Modify: `.github/workflows/publish.yml`
- Modify: `.github/workflows/ci.yml`

**Interfaces:** ensures CI/publish resolve hatch-vcs versions; guards the published version against the tag.

- [ ] **Step 1: publish.yml — fetch full history + a tag-match guard**

In `.github/workflows/publish.yml`, add `fetch-depth: 0` to the `actions/checkout` step:
```yaml
      - uses: actions/checkout@df4cb1c069e1874edd31b4311f1884172cec0e10 # v6
        with:
          fetch-depth: 0   # hatch-vcs derives each plugin's version from its tag
```
After the existing build step (`cd "$DIR" && rm -rf dist && uv build --out-dir dist`), add a guard that the built wheel's version equals the tag's `X.Y.Z`:
```yaml
      - name: Guard — built version matches the release tag
        run: |
          set -euo pipefail
          DIR="${{ steps.resolve.outputs.plugin_dir }}"
          WANT="${{ github.event.release.tag_name }}"; WANT="${WANT##*-v}"   # telnet-v0.1.0 -> 0.1.0
          # A wheel named *-<WANT>-py3-none-any.whl must exist (robust vs parsing).
          ls "$DIR"/dist/*-"$WANT"-py3-none-any.whl >/dev/null 2>&1 \
            || { echo "::error::No wheel for version $WANT in $DIR/dist — built version != tag $WANT, refusing to publish."; ls "$DIR"/dist; exit 1; }
          echo "OK: wheel matches tag version $WANT"
```
(Place it between the build and publish steps. The existing resolve step sets `plugin_dir` as its output — reuse that.)

- [ ] **Step 2: ci.yml — full history on the uv-sync job**

In `.github/workflows/ci.yml`, the job whose checkout lacks `fetch-depth` and runs `uv sync` (the per-member/test job around line 47) — add `with: { fetch-depth: 0 }` to its `actions/checkout`. (One checkout already has `fetch-depth: 0`; bring the `uv sync` one to parity.) If a checkout already has a `with:` block, add `fetch-depth: 0` into it rather than duplicating.

- [ ] **Step 3: Validate YAML**

Run:
```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-plugins
uv run python -c "import yaml; [yaml.safe_load(open(f)) for f in ('.github/workflows/ci.yml','.github/workflows/publish.yml')]; print('workflow yaml ok')"
grep -c 'fetch-depth: 0' .github/workflows/ci.yml .github/workflows/publish.yml
```
Expected: `workflow yaml ok`; `ci.yml` has ≥2 `fetch-depth: 0`, `publish.yml` has 1.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/
git commit --no-verify -m "ci: full history for hatch-vcs + publish tag-match guard"
```

---

### Task 4: Final verification + telnet release handoff

**Files:**
- Modify: `README.md` and/or any release doc if it describes the per-plugin version bump (audit first)

- [ ] **Step 1: Audit release docs**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-plugins
grep -rniE 'bump.*version|version.*pyproject|match the.*pyproject version' README.md docs/ 2>/dev/null
```
For each hit describing the old "bump pyproject then tag" flow, update it to: versions derive from per-plugin git tags (hatch-vcs) — to release a plugin, create its `<plugin>-vX.Y.Z` tag + a GitHub Release, no version edit. If nothing matches, note it and skip.

- [ ] **Step 2: Commit any doc change**

```bash
git add -A && git commit --no-verify -m "docs: plugin releases are tag-driven (hatch-vcs)"
```

- [ ] **Step 3: Full verification**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-plugins
make dev 2>&1 | tail -2
uv run --extra dev pytest tests/test_versioning.py tests/test_check_release.py -q
make test 2>&1 | tail -3
make lint 2>&1 | tail -3
```
Expected: all green; each plugin resolves a real per-tag version.

## Post-merge handoff (NOT part of the PR — for the maintainer)

- [ ] After merge, **release telnet**: create tag `telnet-v0.1.0` + a GitHub Release → `publish.yml` resolves it (telnet now allowlisted), `uv build` derives `0.1.0` from the tag, Trusted Publishing uploads `led-ticker-telnet 0.1.0`. (PyPI trusted-publisher auth is already prepared.)
- [ ] The other 7 plugins need no action — they publish at their own next `<plugin>-vX.Y.Z` tag. Between tags they report dev versions, which is expected.

## Self-Review notes (spec coverage)

- Spec A (per-plugin tag-scoped hatch-vcs, static versions removed, no version-file hook, fallback_version) → Task 1.
- Spec B (check_release.py drops version-match + allowlists telnet + publish fetch-depth + tag-match guard) → Tasks 2 + 3.
- Spec C (CI fetch-depth on the uv-sync job) → Task 3.
- Spec D (telnet release) → Post-merge handoff.
- Spec testing (per-plugin version resolves + scoping; telnet allowlisted; no static version; workflows; make test/lint) → Tasks 1, 2, 3 each carry tests; Task 4 final verification.
- Spec risks (shallow-clone → fetch-depth; --match typo → scoping test + publish guard; untagged dev version → cosmetic; root depth → Step 3 build verification) → covered.
- Non-goals (plugin code changes; re-releasing the other 7; orphaned homage tags) → respected by omission.
