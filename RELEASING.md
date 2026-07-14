# Releasing led-ticker plugins to PyPI

Each plugin in this monorepo is its own PyPI package (`led-ticker-<name>`) and is
**tag-driven** (hatch-vcs): the git tag **is** the version — there is no
`pyproject.toml` version to edit. Publishing is per-plugin and gated by a manual
approval.

> **One-time setup** (PyPI account, Trusted Publishers for each package, the
> `release` GitHub environment) lives in the core repo's runbook —
> <https://github.com/JamesAwesome/led-ticker/blob/main/docs/RELEASING.md> — and
> is shared by both repos. Do that first; this page is only the per-release flow.

## Publishable plugins

`pool`, `baseball`, `crypto`, `calendar`, `rss`, `weather`, `flair`, `telnet`,
`storefront`, `flight` (the allowlist in `scripts/check_release.py`). A tag for
anything else is rejected.

## Cut a release

1. Pick the next version — higher than the plugin's latest `<plugin>-v*` tag.
2. **Releases → Draft a new release** (this repo):
   - **Tag:** `<plugin>-v<X.Y.Z>` using the SHORT name, e.g. `pool-v0.1.2`,
     `telnet-v0.1.0`. NOT the full `led-ticker-pool-v…` (rejected as unknown).
   - **Target:** the exact commit you're releasing (normally `main`'s tip).
   - **Title:** `led-ticker-<name> <X.Y.Z>`.
   - **Publish release.**
3. `publish.yml` resolves the tag → plugin dir (`check_release.py`), builds with
   `uv build` (hatch-vcs derives the version from the tag), and **pauses at the
   `release` environment gate**.
4. Approve via **Actions → the run → Review deployments → approve**.
5. Verify: `https://pypi.org/project/led-ticker-<name>/`.

## Rules the publish guard enforces (fail-before-upload, never a wrong upload)

- **Tag must be PEP 440-normalized `X.Y.Z`.** A non-normalized tag like
  `…-v0.2.01` builds `0.2.1`; the guard's wheel/sdist match then fails and
  refuses to publish.
- **Tag must sit on the released commit.** An off-tag Release derives a
  `.devN+local` version (PyPI rejects local segments); the guard blocks it
  before any upload.
- The guard asserts BOTH the wheel and the sdist carry the tag version.

## First publish of a NEW plugin

The package won't exist on PyPI yet. Register its **pending** Trusted Publisher
(core runbook, §A.2) **before** the first Release, or the upload 403s and the
project won't auto-create.

## Re-releases

PyPI forbids re-uploading a version. To fix a bad release, tag a higher version
(e.g. `pool-v0.1.3`) and Release that — no `pyproject.toml` edit. The `release`
gate is the place to catch mistakes before upload.

## Between releases

`main` (and any untagged commit) reports a dev version like
`0.1.2.dev3+g<sha>` per plugin — expected. Never hand-edit a plugin's version;
the tag is the source of truth.
