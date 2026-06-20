# Monorepo P3c — Archive the 6 old plugin repos (runbook)

> **For the operator:** this is an OPS RUNBOOK, not a code plan. Every step below touches **external public repos** and is outward-facing. Do NOT execute the destructive steps (push redirect README, archive, close PR) until the user has explicitly approved this runbook in the current turn. Reversibility notes are inline.

**Goal:** Make `led-ticker-plugins` the single home for the first-party plugins by redirecting + archiving the 6 now-superseded repos: `led-ticker-pool`, `led-ticker-baseball`, `led-ticker-crypto`, `led-ticker-calendar`, `led-ticker-feeds`, `led-ticker-arcade`.

**Why now / safety:** P3a (catalog) and P3b (docs) are merged — the engine catalog, example requirements, and docs site already point at the monorepo, so nothing in the live product depends on these 6 repos anymore. Existing `@main` install pins on deployed signs still resolve (archived repos still clone, frozen at archive) until each sign updates its `requirements-plugins.txt` at next deploy. **Nothing here is truly destructive:** archiving is reversible (`gh repo edit --archived=false`), and the README change preserves full git history.

**Decision (from the spec, 2026-06-19):** Archive + README redirect. Not forwarding shims, not a deprecation window.

---

## Pre-flight state (verified 2026-06-19)

| repo | visibility | archived | open PRs | open issues |
|---|---|---|---|---|
| led-ticker-pool | public | no | **1 (Dependabot #7, actions/checkout bump)** | 0 |
| led-ticker-baseball | public | no | 0 | 0 |
| led-ticker-crypto | public | no | 0 | 0 |
| led-ticker-calendar | public | no | 0 | 0 |
| led-ticker-feeds | public | no | 0 | 0 |
| led-ticker-arcade | public | no | 0 | 0 |

All on `main`. Each carries the `LED_TICKER_DEPLOY_KEY` secret (their CI used it to checkout the engine) — archiving simply stops their CI; secrets are left as-is (harmless on an archived repo).

---

## Per-repo redirect README content

Replace each repo's `README.md` with a concise redirect (history is preserved in git; the canonical docs live in the monorepo subdirectory's own README). Tags: `-v0.1.0` except rss/weather (`-v0.2.0`).

### Straight moves (pool, baseball, crypto, calendar) — namespace unchanged

```markdown
# led-ticker-<name> — moved

This plugin now lives in the **[led-ticker-plugins](https://github.com/JamesAwesome/led-ticker-plugins)** monorepo at **[`plugins/<name>/`](https://github.com/JamesAwesome/led-ticker-plugins/tree/main/plugins/<name>)**.

Install it from there:

\```
git+https://github.com/JamesAwesome/led-ticker-plugins.git@<name>-v0.1.0#subdirectory=plugins/<name>
\```

The widget type (`<types>`) is unchanged. This repository is archived (read-only); its history is preserved in the monorepo.
```
- pool → `plugins/pool`, tag `pool-v0.1.0`, type `pool.monitor`
- baseball → `plugins/baseball`, tag `baseball-v0.1.0`, types `baseball.scores` / `.standings` / `.promotions` / `.statcast` / `.attendance` + `baseball.roll*` transitions + `:baseball.ball:`
- crypto → `plugins/crypto`, tag `crypto-v0.1.0`, type `crypto.coingecko`
- calendar → `plugins/calendar`, tag `calendar-v0.1.0`, type `calendar.events`

### led-ticker-feeds — moved AND split (breaking renames)

```markdown
# led-ticker-feeds — moved & split

The RSS and weather widgets now live in the **[led-ticker-plugins](https://github.com/JamesAwesome/led-ticker-plugins)** monorepo as two separate packages, with new type names:

| was | now | install |
|---|---|---|
| `feeds.rss` | **`rss.feed`** — [`plugins/rss/`](https://github.com/JamesAwesome/led-ticker-plugins/tree/main/plugins/rss) | `git+https://github.com/JamesAwesome/led-ticker-plugins.git@rss-v0.2.0#subdirectory=plugins/rss` |
| `feeds.weather` | **`weather.current`** — [`plugins/weather/`](https://github.com/JamesAwesome/led-ticker-plugins/tree/main/plugins/weather) | `git+https://github.com/JamesAwesome/led-ticker-plugins.git@weather-v0.2.0#subdirectory=plugins/weather` |

This repository is archived (read-only); its history is preserved in the monorepo.
```

### led-ticker-arcade — moved AND split into 4 families (breaking renames)

```markdown
# led-ticker-arcade — moved & split

The sprite-trail transitions now live in the **[led-ticker-plugins](https://github.com/JamesAwesome/led-ticker-plugins)** monorepo as four separate packages, with new type names:

| was | now | install |
|---|---|---|
| `arcade.nyancat*` | **`nyancat.forward` / `.reverse` / `.alternating`** — [`plugins/nyancat/`](https://github.com/JamesAwesome/led-ticker-plugins/tree/main/plugins/nyancat) | `…@nyancat-v0.1.0#subdirectory=plugins/nyancat` |
| `arcade.pokeball*` + `:arcade.pokeball:` | **`pokeball.forward` / `.reverse` / `.alternating`** + **`:pokeball.ball:`** — [`plugins/pokeball/`](https://github.com/JamesAwesome/led-ticker-plugins/tree/main/plugins/pokeball) | `…@pokeball-v0.1.0#subdirectory=plugins/pokeball` |
| `arcade.pacman*` | **`pacman.forward` / `.reverse` / `.alternating`** — [`plugins/pacman/`](https://github.com/JamesAwesome/led-ticker-plugins/tree/main/plugins/pacman) | `…@pacman-v0.1.0#subdirectory=plugins/pacman` |
| `arcade.sailor_moon*` | **`sailor_moon.forward` / `.reverse` / `.alternating`** — [`plugins/sailor_moon/`](https://github.com/JamesAwesome/led-ticker-plugins/tree/main/plugins/sailor_moon) | `…@sailor_moon-v0.1.0#subdirectory=plugins/sailor_moon` |

This repository is archived (read-only); its history is preserved in the monorepo.
```

---

## Execution runbook (per repo, in order)

For each repo, the order matters: **redirect commit must land BEFORE archiving** (an archived repo is read-only and can't accept the push).

1. **(pool only) Close the Dependabot PR** — it's moot for an archived repo:
   ```bash
   gh pr close 7 --repo JamesAwesome/led-ticker-pool --comment "Closing — this repo is being archived; the plugin now lives in led-ticker-plugins/plugins/pool."
   ```
2. **Push the redirect README** to `main` (clone fresh to a temp dir, overwrite README.md, commit, push). Per repo:
   ```bash
   cd /tmp && rm -rf arch-<name> && git clone git@github.com:JamesAwesome/led-ticker-<name>.git arch-<name>
   cd arch-<name>
   # write the redirect README.md (content above)
   git add README.md
   git commit -m "docs: redirect to the led-ticker-plugins monorepo (repo archived)"
   git push origin main
   cd /tmp && rm -rf arch-<name>
   ```
   (Co-author trailer on the commit.)
3. **Archive the repo** (read-only; reversible via `--archived=false`):
   ```bash
   gh repo edit JamesAwesome/led-ticker-<name> --archived
   ```
4. **Verify:** `gh repo view JamesAwesome/led-ticker-<name> --json isArchived -q .isArchived` → `true`.

Do all 6. Suggested order: crypto, calendar, baseball, pool (straight moves) first, then feeds, arcade (the split ones).

---

## Post-archival (optional, non-blocking)

- The per-repo read-only **deploy keys on `led-ticker`** (titled per old repo, e.g. "led-ticker-pool (readonly)") become dead after archiving. Harmless, but can be pruned from `led-ticker` repo settings → Deploy keys for tidiness. NOT required.
- The `LED_TICKER_DEPLOY_KEY` secret on each archived repo is inert (no CI runs). Leave it.

## Out of scope
- P4 hardware smoke (Pi-side).
- Core rss/weather removal (separate engine PR).
- Deleting the old repos outright (we archive, not delete — keeps URLs + history live).

## Rollback
If anything looks wrong: `gh repo edit JamesAwesome/led-ticker-<name> --archived=false` unarchives; `git revert` on the redirect commit restores the old README. No data is lost at any step.
