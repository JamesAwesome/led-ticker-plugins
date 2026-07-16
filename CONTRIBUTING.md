# Contributing to led-ticker-plugins

This repo is the **first-party plugin pack** for [led-ticker](https://github.com/JamesAwesome/led-ticker) — a curated set of plugins the project maintains and ships. The single most valuable thing you can contribute is usually **a plugin of your own, in your own repo**. Here's why, and what we do take here.

## Building a new plugin? Make it your own repo.

led-ticker's plugin API (`led_ticker.plugin`) is designed so a plugin is a small standalone package — no fork of core, and no need to live in this monorepo. A plugin in your own repository installs exactly the way these do (one line in a sign's `config/requirements-plugins.txt`), versions on your own schedule, and stays yours.

So **new widgets, transitions, color providers, or other plugins belong in their own repository — not a PR here.** Start with the [plugin authoring guide](https://docs.ledticker.dev/plugins/authoring/01-scaffold/): it walks an empty `register(api)` through to an installed, published plugin. The packages in this repo double as worked examples to copy from.

Built something? Share it in [Discussions](https://github.com/JamesAwesome/led-ticker/discussions) — we're glad to point people at good community plugins.

## What we take in this repo

Contributions that **improve the existing first-party plugins** are welcome:

- Bug fixes.
- New options, layouts, or data sources on an **existing** plugin.
- Docs, tests, and packaging fixes.

What generally **isn't** a fit here:

- **Brand-new plugins or widgets** — those go in your own repo (above). Keeping this pack a small, curated first-party set is deliberate.
- **New fan-homage sprite families** in `led-ticker-flair` — the homages carry third-party character and artwork rights (see [NOTICE.md](NOTICE.md)); ship yours as your own plugin instead.

Not sure whether something fits? Open an [issue](https://github.com/JamesAwesome/led-ticker-plugins/issues) first — happy to talk it through before you write code.

## Working in the repo

This is a `uv` workspace; each plugin lives under `plugins/<name>/` with its own `pyproject.toml`, `CLAUDE.md`, and `README.md` (versions derive from per-plugin git tags — `<plugin>-vX.Y.Z` — via hatch-vcs; no manual version bump is needed to release). A sibling `../led-ticker` checkout is required (the workspace resolves `led-ticker-core` from it).

```bash
make dev    # uv sync the whole workspace
make test   # pytest every member
make lint   # ruff + pyright
make format # ruff format
```

### Layout invariant: positioned hi-res text must be collision-guarded

Any plugin that paints hi-res text at a fixed or computed position (not
scrolling) with variable-length data must:

- **(a) measure with core's `hires_text_width`** (via `led_ticker.plugin`) —
  the same glyph resolution the renderer draws with, so collision math can't
  drift from the paint;
- **(b) shrink-to-fit via `fit_text_size`** with a plugin-owned size ladder
  when the text would collide with a neighbor (ladder values are per-layout
  design decisions — keep them in the plugin, not core);
- **(c) ship a pixel-separation regression test** — invariant-based, never
  exact-pinning sizes or widths (freetype metrics differ macOS vs Linux);
- **(d) never ship < 6px measured clearance** — a near-miss on dev metrics is
  an overlap on the panel (stocks #54; flight dashboard columns).

Scrolling layouts are exempt (motion is the overflow mechanism), as is
fixed-vocabulary text that cannot vary in length (digits, team abbreviations).

Read the target plugin's `CLAUDE.md` before changing it — each package documents its own invariants. Keep changes scoped to one plugin per PR where you can, and make sure `make test` and `make lint` pass.
