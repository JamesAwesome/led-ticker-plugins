# Design: Consolidate first-party plugins into the `led-ticker-plugins` monorepo

**Date:** 2026-06-19
**Status:** Approved for planning
**Tracking issue:** [led-ticker#235](https://github.com/JamesAwesome/led-ticker/issues/235)

## Goal & boundary

Fold the first-party plugins into a single `led-ticker-plugins` uv-workspace
monorepo, **leaving the engine repo (`led-ticker`) structurally untouched** —
no change to its Docker layers, `deploy/install.sh`, or constraint-based
install flow. The only engine change is content, not structure:
`config/requirements-plugins.example.txt` URLs flip to monorepo subdirectories.

Third-party plugins still live in their own external repos; the "anyone can
build a plugin independently" goal is preserved. This keeps the spec out of the
riskiest part of a full monorepo (rewriting the engine deploy/install model +
hardware re-validation).

### What we get

- 6 CI configs → 1; 6 ruff/pyright/pytest setups → 1; one test harness instead
  of N copies of the `../led-ticker/tests/stubs` wiring.
- A public-API (`led_ticker.plugin`) change drops from "engine + N plugin
  repos" to "engine + 1 plugins repo".
- Removing repo-sprawl friction lets us split bundled plugins into finer
  cherry-pickable packages (see "Plugin splits").

### Accepted non-goals

- **No atomic engine+plugin PRs.** A core-API change still needs an engine PR
  plus a plugins-repo PR — they can't verify in one CI pass. Accepted; the
  coordination reduction (many repos → 2) captures most of the relief.
- **No full monorepo.** The engine stays its own repo.

## Scope correction (verified against the repos on 2026-06-19)

The issue's premise was checked against the actual checkouts. Two corrections:

1. **All plugin repos are real and populated** — an earlier "feeds is empty"
   reading was a stale local checkout. `led-ticker-feeds` (v0.2.0) ships
   `rss.py` + `weather.py` under entry point `feeds = led_ticker_feeds:register`.
2. **Core rss/weather removal never happened.** `led-ticker`'s
   `widgets/__init__.py` still imports and registers `rss_feed` (88-line
   `@register("rss_feed")`) and `weather` (237-line `@register("weather")`).
   The feeds *plugin* was built but core's "Phase 3 removal" was skipped, so the
   widgets currently exist in **both** places. This removal is **still needed**
   but is tracked out-of-scope (see "Out of scope / tracked loose ends").

## Plugin splits

Because the monorepo removes the per-repo overhead, two bundled plugins split
into finer packages so users cherry-pick exactly what they want.

### The loader constraint that forces renames

`led_ticker/_plugin_loader.py` binds **one namespace per package** (the
entry-point name) and **rejects a namespace already claimed by another package**
(`"namespace already claimed by another plugin"`, the second is skipped). There
is therefore no way to split into separate installable packages while keeping
the old `feeds.*` / `arcade.*` config names. **Splitting is a breaking config
rename.** Accepted: these are recent first-party plugins with minimal field
deployment; cost is a migration note + new names.

### Split mapping

`feeds` → 2 packages:

| old type | new package | new (working) type |
|---|---|---|
| `feeds.rss` | `rss` | `rss.feed` |
| `feeds.weather` | `weather` | `weather.current` |

`arcade` → 4 packages (each: base + reverse + alternating). All four split out,
including `pacman` / `sailor_moon` which carry no hires variant:

| old | new package | new (working) types |
|---|---|---|
| `arcade.nyancat*` | `nyancat` | `nyancat.forward` / `.reverse` / `.alternating` |
| `arcade.pokeball*` + `:arcade.pokeball:` | `pokeball` | `pokeball.forward` / `.reverse` / `.alternating` + `:pokeball.ball:` |
| `arcade.pacman*` | `pacman` | `pacman.forward` / `.reverse` / `.alternating` |
| `arcade.sailor_moon*` | `sailor_moon` | `sailor_moon.forward` / `.reverse` / `.alternating` |

The `forward` variant suffix avoids the redundant `nyancat.nyancat`;
`:pokeball.ball:` mirrors the existing `:baseball.ball:` convention.

> **Names are a WORKING proposal.** The variant-suffix scheme is the default,
> but the exact final type/slug names are to be **finalized in a follow-up
> naming brainstorm** before P2 implements them. The split granularity (10
> packages) and the variant-suffix *style* are locked; the literal strings are
> not.

### Resulting package set (10 members)

`pool` · `baseball` · `crypto` · `calendar` · `rss` · `weather` ·
`nyancat` · `pokeball` · `pacman` · `sailor_moon`

## Monorepo layout

```
led-ticker-plugins/
  pyproject.toml            # [tool.uv.workspace] members = ["plugins/*"]
  uv.lock                   # single shared lockfile
  conftest.py               # single test harness (stub source: see "Test harness")
  ruff.toml / pyright cfg   # one shared config
  tests/stubs/              # vendored rgbmatrix stub (interim; see "Test harness")
  .github/workflows/ci.yml  # one path-filtered per-package matrix
  Makefile                  # root targets (collapse per-repo Makefiles)
  plugins/
    crypto/    pyproject.toml  src/led_ticker_crypto/    tests/  CLAUDE.md  README.md  docs/
    pool/      ...
    baseball/  ...
    calendar/  ...
    rss/       ...   (from feeds)
    weather/   ...   (from feeds)
    nyancat/   ...   (from arcade)
    pokeball/  ...   (from arcade)
    pacman/    ...   (from arcade)
    sailor_moon/ ... (from arcade)
```

Each member keeps its own `pyproject.toml` + independent `version`, and its
`CLAUDE.md` / `README.md` / `docs/` move in per-directory. The per-repo
`uv.lock`s collapse into one root lockfile; per-repo `Makefile`s collapse into
root targets.

## Test harness (the #233 bridge)

The single root `conftest.py` needs the rgbmatrix stub before
[led-ticker#233](https://github.com/JamesAwesome/led-ticker/issues/233) ships
`led_ticker.testkit`.

- **Interim (now):** vendor a copy of the stub into the monorepo at
  `tests/stubs/`, rather than depend on the brittle `../led-ticker/tests/stubs`
  sibling path. A vendored copy makes the monorepo clone-anywhere from day one.
- **When #233 lands:** delete the vendored copy and import the stub from the
  installed `led_ticker.testkit`. One swap, isolated to `conftest.py` + the
  pytest/pyright path config.

## CI

One workflow (`ci.yml`), **path-filtered per-package matrix**: a change under
`plugins/baseball/**` runs only baseball's lint/type/test job; a shared-root
change runs all members. Each job: `uv sync` the workspace, then ruff + pyright
+ pytest for that member against the vendored stub.

The publish/deploy leg references the existing **`LED_TICKER_DEPLOY_KEY`**
secret already seeded on the repo. **P0 must confirm what that key authorizes**
(push to this repo? PyPI? Pi deploy?) so the workflow uses it correctly and
never logs it.

## Distribution & release tags

- Install is **per-subdirectory** so users cherry-pick exactly the plugins they
  want — never a single all-or-nothing install:
  `pip install "git+https://…/led-ticker-plugins.git@<ref>#subdirectory=plugins/<name>"`.
- **Per-plugin namespaced tags**: `crypto-v0.1.0`, `baseball-v1.2.0`, etc. Each
  package releases on its own cadence.
- Documented default install stays `@main#subdirectory=plugins/<name>`;
  **production guidance pins to a namespaced tag** (consistent with prior
  deploy-hardening guidance).

## Old-repo archival & migration

Existing deployed signs pin plugins by URL in `requirements-plugins.txt`
(e.g. `git+https://github.com/JamesAwesome/led-ticker-baseball@main`).

After cutover:

- Flip the engine's `config/requirements-plugins.example.txt` to the new
  monorepo subdirectory URLs.
- **Archive all source repos read-only**, each README redirecting to the
  monorepo subdirectory URL. Existing `@main` pins keep resolving (archived
  repos still clone) frozen-at-archive until each sign updates its
  `requirements-plugins.txt` at next deploy.
- Add a migration note to the deploy docs, including the breaking type renames
  for the feeds/arcade splits.

## Execution approach: pilot-one-then-rest (Approach B)

Chosen over big-bang (risk concentrated at the end) and per-plugin trickle
(long hybrid half-in/half-out limbo). B front-loads proof of the one risky
unknown — constraint-based `#subdirectory=` install + entry-point discovery —
on the smallest surface before the bulk move.

### Phases

- **P0 — Install-model spike (HARD GATE).** Against the *live* repo, prove
  `pip install "git+…/led-ticker-plugins.git@<sha>#subdirectory=plugins/crypto"`
  works with (a) the engine's `-c constraints-core.txt` constraint install and
  (b) entry-point auto-registration of the `led_ticker.plugins` group. Also
  confirm `LED_TICKER_DEPLOY_KEY`'s scope. ~half a day. **No further work until
  green.**
- **P1 — Pilot `crypto`.** `filter-repo` crypto into `plugins/crypto/`; stand up
  the workspace, root configs, single conftest + vendored stub, the per-package
  CI matrix (one row), and a `crypto-v*` tag; do a real hardware install +
  entry-point check. Proves the entire pipeline end-to-end on the smallest,
  hires-free surface.
- **P2 — Bulk fold-in.** `filter-repo` the remaining packages into
  `plugins/<name>/`, history-preserving. This includes the feeds → {rss,
  weather} and arcade → {nyancat, pokeball, pacman, sailor_moon} **splits** —
  one `filter-repo` per target subdir from each source repo (so a source repo's
  history maps to multiple subdirs; messier than a 1:1 move but still
  history-preserving). Apply the finalized split names (from the naming
  brainstorm). CI matrix grows to all 10 members.
- **P3 — Distribution + cutover.** Flip engine example reqs; archive the source
  repos with README redirects; write the migration note.
- **P4 — Hardware validation.** Install monorepo plugins, smoke on smallsign +
  bigsign.

## Out of scope / tracked loose ends

- **#233 `led_ticker.testkit`** — separate engine effort; this spec only
  consumes it via the harness swap. May trickle.
- **Core rss/weather removal** — still needed (both are live registered
  widgets); separate engine PR. May trickle.
- **Final split names** — locked to the variant-suffix *style*; literal strings
  finalized in a follow-up naming brainstorm before P2.
- **Atomic engine+plugin PRs** — accepted non-goal.

## Process constraints

- Multi-repo structural change: brainstorm → spec → plan → subagent-driven
  execution, with the P0 spike gating the full migration.
- No merge of any constituent PR without explicit consent.
- All work on branches/worktrees, never on `main`.
