# P0 spike — install model

Findings for the led-ticker-plugins monorepo P0 spike (issue led-ticker#235).

## Deploy key scope

**Conclusion: `LED_TICKER_DEPLOY_KEY` is a read-only checkout credential for the
`JamesAwesome/led-ticker` engine repo. It does not push, publish, or deploy.**

The value of the secret is unreadable by design, so scope is inferred from how the key
is *used* in plugin CI and from the deploy keys registered on the engine repo.

### Evidence

**The secret exists on the monorepo repo.** `gh secret list --repo
JamesAwesome/led-ticker-plugins`:

```
LED_TICKER_DEPLOY_KEY	2026-06-18T21:11:48Z
```

**A matching read-only deploy key exists on `led-ticker`.** Every deploy key on the
engine repo is `read-only`, including the one minted for the monorepo
(`led-ticker-plugins (readonly)`, created 2026-06-18, same day as the secret above).
`gh api repos/JamesAwesome/led-ticker/keys`:

```
moonbunny                          read-only
led-ticker-pool CI (read-only)     read-only
led-ticker-baseball CI (read-only) read-only
led-ticker-crypto-ci               read-only
longboi                            read-only
led-ticker-calendar                read-only
led-ticker-feeds (read only)       read-only
led-ticker-arcade (read-only)      read-only
led-ticker-plugins (readonly)      read-only
```

The `read_only` flag is enforced by GitHub on the deploy key itself — it caps what the
private key can do regardless of how a workflow invokes it. A read-only deploy key can
clone/fetch; it cannot push.

**Existing plugin CI uses the key only as a sibling checkout `ssh-key`.** In both
`led-ticker-crypto` and `led-ticker-baseball`, the key appears exactly three times each
(once per job: lint, typecheck, test), always as the `ssh-key` input to
`actions/checkout` for the `JamesAwesome/led-ticker` repository — never in a push,
release, or publish step. From `led-ticker-crypto/.github/workflows/ci.yml`:

```yaml
# led-ticker is private and not on PyPI; check it out as a sibling so
# [tool.uv.sources] resolves and its tests/stubs are available. Uses a
# read-only deploy key scoped to that repo.
- name: Checkout led-ticker (sibling dependency)
  uses: actions/checkout@v6.0.3
  with:
    repository: JamesAwesome/led-ticker
    path: led-ticker
    ssh-key: ${{ secrets.LED_TICKER_DEPLOY_KEY }}
```

The engine resolves via `[tool.uv.sources] led-ticker = { path = "../led-ticker",
editable = true }`, and the engine's `tests/stubs` (rgbmatrix shim) must be on the
pytest path — so CI clones `led-ticker` next to the plugin checkout purely to satisfy
the build/test, then runs only `uv sync` / `ruff` / `pyright` / `pytest`.

### Implications for the consolidated monorepo CI

- The consolidated CI uses the key the **same way**: a read-only sibling checkout of
  `led-ticker` so `[tool.uv.sources]` resolves and the rgbmatrix stub is importable
  headless. No change in scope.
- Publish/deploy is **out of this key's scope.** Any future CI leg that publishes to
  PyPI or pushes to a Pi needs a **different** credential (a PyPI token / trusted
  publisher, or a separate push-capable key). Do not attempt to extend
  `LED_TICKER_DEPLOY_KEY` to cover those — it is read-only at the GitHub level and
  cannot be widened in place.

### How to re-verify

```bash
gh secret list --repo JamesAwesome/led-ticker-plugins
gh api repos/JamesAwesome/led-ticker/keys --jq '.[] | {title, read_only}'
grep -rn 'LED_TICKER_DEPLOY_KEY' <plugin>/.github
```

## P0 install-model spike — GO/NO-GO

The other half of the P0 gate: can a plugin install cleanly from a git
**subdirectory** of this monorepo, under the engine's frozen constraints file, and
auto-register via its entry point — mirroring the Docker layer-2b model (engine
installed first → `constraints-core.txt` frozen → plugins installed with
`pip install -c constraints-core.txt`).

**Date:** 2026-06-19
**SPIKE_SHA:** `39a2a11f228b7dcca9a7c57d700c6bafee88a572` (throwaway branch
`spike/install-model`, pushed then deleted — do not look for it)
**Python:** 3.14.4 (`python3.14`, the engine's required `>=3.14`)
**Plugin under test:** crypto (`led-ticker-crypto`, package `led_ticker_crypto`,
namespace `crypto`, entry point `crypto = led_ticker_crypto:register`) — the smallest
plugin. A throwaway copy was placed at `plugins/crypto/` on the spike branch. Its
`pyproject.toml` declares `dependencies = ["led-ticker", "aiohttp"]` and a
`[tool.uv.sources]` table pointing `led-ticker` at a local editable path — the exact
uv-only metadata we need pip to ignore.

### Verdict: **GO**

The constraint-pinned `#subdirectory=` install works end to end. pip ignored the
plugin's `[tool.uv.sources]` (uv-only metadata), resolved `led-ticker` against the
already-installed, constraint-pinned engine (`2.0.0`), built the plugin wheel, and the
entry point auto-registered.

### Commands run

```bash
# Step 1 — push throwaway crypto copy to a disposable branch
cd /Users/james/projects/github/jamesawesome/led-ticker-plugins
git checkout main && git checkout -b spike/install-model
mkdir -p plugins
cp -R ../led-ticker-crypto plugins/crypto
rm -rf plugins/crypto/.git plugins/crypto/.github plugins/crypto/uv.lock
find plugins/crypto -name '__pycache__' -type d -prune -exec rm -rf {} +
git add plugins/crypto && git commit -m "spike: throwaway crypto copy ..."
git push -u origin spike/install-model
# SPIKE_SHA=39a2a11f228b7dcca9a7c57d700c6bafee88a572

# Step 2 — clean env mimicking production (engine pre-installed + constraints)
cd /tmp && rm -rf spike-venv && python3.14 -m venv spike-venv && . spike-venv/bin/activate
pip install -q --upgrade pip
pip install -q -e /Users/james/projects/github/jamesawesome/led-ticker
pip list --format=freeze > /tmp/constraints-core.txt   # -> led-ticker==2.0.0

# Step 3 — install crypto from the git subdirectory UNDER the constraint
pip install -c /tmp/constraints-core.txt \
  "git+https://github.com/JamesAwesome/led-ticker-plugins.git@spike/install-model#subdirectory=plugins/crypto"

# Step 4 — verify entry-point auto-registration
python -c "from importlib.metadata import entry_points; \
  eps=[e for e in entry_points(group='led_ticker.plugins')]; \
  print(eps); assert any(e.name=='crypto' for e in eps)"
led-ticker plugin list
```

### Actual output

**Step 3 (install) — exit 0, success.** Key lines:

```
Resolved https://github.com/JamesAwesome/led-ticker-plugins.git to commit 39a2a11f228b7dcca9a7c57d700c6bafee88a572
Requirement already satisfied: aiohttp ... (from led-ticker-crypto==0.1.0) (3.14.1)
Requirement already satisfied: led-ticker ... (from led-ticker-crypto==0.1.0) (2.0.0)
Building wheel for led-ticker-crypto (pyproject.toml): finished with status 'done'
Successfully built led-ticker-crypto
Successfully installed led-ticker-crypto-0.1.0
```

After install, `led-ticker` remained pinned (`Version: 2.0.0`,
`Location: /private/tmp/spike-venv/.../site-packages`) — the constraint held; the
`[tool.uv.sources]` local-path override was correctly ignored by pip.

**Step 4 (entry point) — exit 0, assert passed:**

```
entry points: [('crypto', 'led_ticker_crypto:register')]
ASSERT PASSED: crypto entry point present
```

`led-ticker plugin list` (optional, but ran cleanly) confirmed full registration:

```
crypto  [installed] — CoinGecko cryptocurrency price ticker.
    provides: crypto.coingecko
```

### Notes / sharp edges

- The `[tool.uv.sources]` `led-ticker = { path = "../led-ticker", editable = true }`
  entry in the plugin's `pyproject.toml` is **uv-only metadata** — pip does not read it.
  This is exactly what we want: pip falls back to the plain
  `dependencies = ["led-ticker", ...]` requirement and the constraint file satisfies it
  from the pre-installed engine. If a future build ever runs the plugin install through
  `uv pip` instead of `pip`, revisit this — uv WOULD honor that local path and could try
  to re-resolve the engine.
- This spike proves the model in a venv where the engine is installed editable from a
  local checkout. Production installs the engine from the same source; the
  constraint-satisfaction mechanism is identical (pip sees `led-ticker` already present
  and pinned), so the result carries over.
- A stray `plugins/crypto/.coverage` artifact leaked into the spike copy (the source
  repo's `.gitignore` did not cover the disposable copy's path). Harmless here — the
  branch is deleted — but the real migration's copy/`git mv` step should scrub build
  artifacts.

### Cleanup performed

- `/tmp/spike-venv` and `/tmp/constraints-core.txt` removed.
- `spike/install-model` deleted on the **remote** (`git push origin --delete`) and
  **locally** (`git branch -D`). No spike branches remain.
- This verdict was committed on `spec/monorepo-consolidation`.
