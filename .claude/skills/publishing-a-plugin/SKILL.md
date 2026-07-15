---
name: publishing-a-plugin
description: Use when releasing or publishing a led-ticker plugin to PyPI (cutting a new <plugin>-vX.Y.Z version), or when checking that the plugins' pyproject metadata is consistent and release-ready. For the led-ticker-plugins monorepo.
---

# Publishing a led-ticker plugin

Guide a plugin release in the **led-ticker-plugins** monorepo (a uv workspace; each `plugins/<name>/` is its own PyPI package, versioned **only** by git tags via hatch-vcs — there is no version field to edit). Releases are **tag-driven and gated**: a GitHub Release fires `publish.yml`, which builds and **pauses at the `release` environment for a human approval** before uploading via Trusted Publishing.

**Core principle:** a release is also a metadata checkpoint. Never cut a tag without first running the **metadata gate** — the plugins drift, and a release freezes whatever is on PyPI's project page.

Two modes:

## Mode: `audit` (metadata drift check, no release)

Run the metadata gate across ALL plugins (or one) without releasing. Use it anytime, and always as step 1 of a `release`.

For each `plugins/<name>/pyproject.toml`, check `[project]` against `references/metadata-template.md` and **flag drift as fix-and-ask** (never silently rewrite — show the diff, cite the rule, let the user decide):
- `[project.urls]` has the 5 canonical entries.
- `classifiers` = the canonical 9 (Development Status MAY differ per real maturity — the one field allowed to vary).
- `keywords` start with the 5 common terms + real domain terms.
- `description` is one accurate line; `README.md` exists.

Quick machine check (every line should be `5 9`):
```bash
uv run python -c "import tomllib,glob; [print(f, len(tomllib.load(open(f,'rb'))['project']['urls']), len(tomllib.load(open(f,'rb'))['project']['classifiers'])) for f in sorted(glob.glob('plugins/*/pyproject.toml'))]"
```

## Mode: `release` (cut + publish one plugin)

1. **Metadata gate** — run `audit` on THIS plugin first. Fix drift (fix-and-ask) and merge that fix before tagging, so the release carries correct metadata.
2. **Pre-flight** (from repo root, on up-to-date `main`):
   - `git pull`; confirm the change is merged and `main`'s tip is what you want to ship; CI green on that commit (`gh run list --branch main`).
   - Plugin gate: `uv run pytest plugins/<name> --cov=plugins/<name>/src`, `uv run ruff check plugins/<name>`, `ruff format --check`, `uv run pyright plugins/<name>/src`.
   - `git tag -l "<name>-v*" | sort -V` → the latest tag; the new one must be strictly higher, PEP 440 `X.Y.Z` (patch/minor/major by the change).
   - The plugin MUST be in `scripts/check_release.py`'s `PUBLISHABLE_PLUGINS` (that file is the source of truth; RELEASING.md's prose list drifts). **New plugin?** add it there AND register a **pending** Trusted Publisher on PyPI first, or the first upload 403s.
3. **Cut the release** — tag on the exact commit, SHORT plugin name:
   ```bash
   gh release create <name>-vX.Y.Z --repo JamesAwesome/led-ticker-plugins \
     --target <main-tip-sha> --title "led-ticker-<name> X.Y.Z" --notes-file <notes.md>
   ```
   `publish.yml` runs `check_release.py` (tag→dir), `uv build` (hatch-vcs derives the version from the tag), a guard that asserts both wheel+sdist carry `X.Y.Z`, then pauses at the `release` gate.
4. **Approve the gate** (the human checkpoint — you may drive it via API):
   ```bash
   RID=$(gh run list --repo JamesAwesome/led-ticker-plugins --workflow publish.yml --limit 1 --json databaseId --jq '.[0].databaseId')
   ENVID=$(gh api /repos/JamesAwesome/led-ticker-plugins/actions/runs/$RID/pending_deployments --jq '.[0].environment.id')
   gh api -X POST /repos/JamesAwesome/led-ticker-plugins/actions/runs/$RID/pending_deployments \
     -F "environment_ids[]=$ENVID" -f state=approved -f comment="Approve <name>-vX.Y.Z"
   ```
5. **Verify** — `curl -s https://pypi.org/pypi/led-ticker-<name>/json | python3 -c "import sys,json;print(json.load(sys.stdin)['info']['version'])"` shows the new version. (The `/simple/` index updates fastest; the JSON API can lag a minute.)

## Gotchas (each has bitten a real release)

| Symptom | Cause | Fix |
|---|---|---|
| Publish job fails: `400 Invalid attestations … Failed to refresh TUF metadata` | Transient PyPI/Sigstore infra hiccup — NOT your config (build + auth succeeded) | The version wasn't consumed (upload was rejected). `gh run rerun <RID> --failed`, then re-approve the gate. |
| Tag rejected / `Unknown plugin` | Used the full `led-ticker-<name>-v…`, or the plugin isn't in the allowlist | Use the SHORT name `<name>-vX.Y.Z`; add to `scripts/check_release.py`. |
| Guard fails "wheel/sdist version mismatch" or `.devN+local` | Tag not PEP 440 `X.Y.Z`, or the tag doesn't sit on the released commit | Re-tag a clean `X.Y.Z` on the exact commit. |
| First upload of a new package 403s | No pending Trusted Publisher registered on PyPI | Register it (core runbook) before the first Release. |
| Bad release already on PyPI | PyPI forbids re-uploading a version | Bump to a higher `X.Y.Z` and re-release — never edit a version field (there isn't one). |

## Common mistakes
- Cutting a release without the metadata gate → the PyPI page ships stale/inconsistent metadata frozen at that version.
- Trusting RELEASING.md's plugin list — it drifts; `scripts/check_release.py` is authoritative.
- Waiting on the UI for the approval when `gh api pending_deployments` does it headless.
- Assuming a TUF-attestation failure means a real problem — it's transient; rerun.
