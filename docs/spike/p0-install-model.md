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
