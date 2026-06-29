# Design: hatch-vcs versioning for led-ticker-plugins + telnet release (Spec 2)

**Date:** 2026-06-28
**Status:** Approved for planning
**Context:** Spec 2 of 2. Spec 1 (led-ticker-core hatch-vcs) shipped in led-ticker#296. This applies the same idea to the **plugins monorepo**, where the new twist is **per-plugin, tag-scoped** versioning (one repo, many independently-versioned packages), plus wiring the new `led-ticker-telnet` plugin for PyPI release.

## Motivation

Every plugin under `plugins/<name>/` carries a hand-bumped static `version`, kept in sync with its release tag (`<plugin>-vX.Y.Z`) by a guard in `scripts/check_release.py`. Deriving each plugin's version from its own tags makes the tag the single source of truth — no manual bump, no guard drift — and lets the new `telnet` plugin ship on the same automatic flow.

## Decisions (settled at brainstorm)

- **Scope:** all 8 plugins migrate to hatch-vcs at once (uniform end state; the shared publish machinery simplifies cleanly). The other 7 are **not** re-released — they keep deriving dev versions until their own next `<plugin>-v*` tag.
- **telnet:** first release is `telnet-v0.1.0` (matches its current static version); added to the publish allowlist (PyPI auth already prepared).
- **Per-plugin tag-scoping** (verified working): each plugin's hatch-vcs config differs only in `--match <plugin>-v*`.
- Spec 1 learnings carried over: `fallback_version`, **no** version-file hook, `fetch-depth: 0` on CI/publish, a tag-match publish guard.

## Components

### A. Per-plugin VCS version (each `plugins/<name>/pyproject.toml`)

Verified empirically (pool → `0.1.2.dev2` from `pool-v0.1.1`; crypto → `0.2.2.dev2` from `crypto-v0.2.1`; untagged telnet → `0.0.1.dev<N>`, and `0.1.0` once `telnet-v0.1.0` is tagged):

```toml
[build-system]
requires = ["hatchling", "hatch-vcs"]
build-backend = "hatchling.build"

[project]
dynamic = ["version"]            # remove the static `version = "..."`

[tool.hatch.version]
source = "vcs"

[tool.hatch.version.raw-options]
root = "../.."                                                  # plugins/<name> -> monorepo .git
git_describe_command = ["git", "describe", "--dirty", "--tags", "--long", "--match", "<name>-v*"]
tag_regex = "^(?:.+-v)(?P<version>[0-9].*)$"
fallback_version = "0.0.0"
```

- `<name>` is the plugin's short name (`pool`, `baseball`, `crypto`, `calendar`, `rss`, `weather`, `flair`, `telnet`). It appears **only** in the `--match` glob — `tag_regex` and the rest are identical across plugins.
- **No version-file hook** (it would write `src/<pkg>/_version.py`, which breaks any build where `src/` isn't present, e.g. an sdist build or the telnet `Dockerfile.smoke` `pip install`). No plugin currently hardcodes `__version__`; none needs to add one. If one ever does, it reads `importlib.metadata.version("led-ticker-<name>")`.
- `fallback_version = "0.0.0"` covers a true no-git build (sdist install, no `.git`); with git present the real per-plugin version resolves.

### B. Shared publish machinery

- **`scripts/check_release.py`** — drop the static tag-vs-`pyproject`-version check (the tag is the version now). `resolve(tag)` keeps: parse `<plugin>-vX.Y.Z` → confirm `plugin` in `PUBLISHABLE_PLUGINS` → return the plugin dir. **Add `"telnet"` to `PUBLISHABLE_PLUGINS`.** Its test (`tests/test_check_release.py`) drops the version-mismatch case and adds a telnet-resolves case.
- **`.github/workflows/publish.yml`** — the checkout gains `fetch-depth: 0` (so hatch-vcs resolves the tag on the runner). After `cd plugins/<dir> && uv build`, add a guard asserting the built wheel's version equals the tag's `X.Y.Z` (fail-before-upload; the build derives from the tag so this is belt-and-suspenders against a mis-scoped match). Trusted Publishing + the `release` gate are unchanged.

### C. CI

- **`.github/workflows/ci.yml`** — the per-member job that runs `uv sync` (the workspace editable install triggers every plugin's hatch-vcs) gets `fetch-depth: 0`. (One checkout already has it; the `uv sync` job does not.) A shallow clone makes setuptools-scm error — the Spec-1 trap.

### D. telnet PyPI release (post-merge handoff)

After this merges: create tag **`telnet-v0.1.0`** + a GitHub Release → `publish.yml` resolves it (telnet now allowlisted), `uv build` derives `0.1.0` from the tag, Trusted Publishing uploads `led-ticker-telnet 0.1.0`. The other 7 plugins are untouched (no release).

## Data flow

```
git tag <plugin>-vX.Y.Z ──► hatch-vcs (git describe --match <plugin>-v*) ──► version X.Y.Z (that plugin only)
  CI:      uv sync (fetch-depth 0) ─► each plugin derives its own dev version
  release: <plugin>-vX.Y.Z + Release ─► check_release.py (allowlist+dir) ─► cd plugins/<p> && uv build ─► PyPI
```

## Scope / non-goals

- **IN:** A (per-plugin tag-scoped hatch-vcs, static versions removed), B (`check_release.py` simplification + telnet allowlisted + publish guard + fetch-depth), C (CI fetch-depth), tests. telnet's tag/Release is the post-merge handoff (D).
- **OUT:** plugin code/behavior changes; re-releasing the other 7 plugins (they publish at their own next tag); the orphaned homage tags (`nyancat-v*`, `pacman-v*`, `pokeball-v*`, `sailor_moon-v*` — pre-flair-consolidation) are harmless and left as-is; any non-PEP-440 scheme.

## Testing

- **Per-plugin version resolves, scoped:** a test parametrized over the 8 plugins asserting each derives `^\d+\.\d+` from its own tag (not `0.0.0` when git is present); explicitly assert pool ≠ crypto scoping (a plugin doesn't pick up another's tag).
- **telnet allowlisted:** `check_release.py` resolves `telnet-v0.1.0` → `plugins/telnet`.
- **No static version left:** no `plugins/*/pyproject.toml` has a `version = "..."` line; each has `dynamic = ["version"]` + the vcs config.
- **Workflows:** `publish.yml` + the `uv sync` CI job have `fetch-depth: 0`; `check_release.py` no longer compares against a static pyproject version.
- **No regression:** `make dev`, `make test`, `make lint` green across the workspace.

## Risks

- **Shallow-clone fallback** (CI/publish) → `fetch-depth: 0` on the building jobs (C, B).
- **`--match` typo → a plugin silently versions from the wrong/no tag** (→ `0.0.x.dev<huge>` from root) → the parametrized scoping test + the publish tag-match guard catch it.
- **Untagged plugin reads `0.0.1.dev<N>`** (telnet pre-release) — cosmetic; resolves to `0.1.0` at its first tag.
- **`root = "../.."` depends on the `plugins/<name>/` depth** — uniform across the monorepo; a test builds/imports each plugin's version to confirm resolution.
