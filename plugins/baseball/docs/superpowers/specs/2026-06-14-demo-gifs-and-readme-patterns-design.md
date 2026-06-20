# Demo GIFs + README "Common patterns" — design

**Date:** 2026-06-14
**Status:** Approved
**Scope:** Documentation polish for the now-complete four-widget set
(`scores`, `standings`, `promotions`, `statcast`, `attendance`). Two
deliverables, one PR to `led-ticker-baseball`.

## Deliverable A — Demo GIFs for the three new widgets

The README `## Screenshots` block already shows `scores.gif`, `standings.gif`,
`roll-transition.gif`, and the two emoji PNGs. The three widgets shipped since
(`promotions`, `statcast`, `attendance`) have no demo asset. Add one GIF each.

### How they're rendered

GIFs are produced **headlessly** by led-ticker's software-matrix renderer —
no physical panel. Use led-ticker's `making-a-gif` skill in **dev mode** (these
are the plugin's own docs assets, not led-ticker's pinned demo set), against the
three existing smoketest configs in the led-ticker repo:

| Widget | Render source (in ../led-ticker) | Output (in this repo) |
| --- | --- | --- |
| promotions | `config/config.mlb_promotions_test.toml` | `docs/promotions.gif` |
| statcast | `config/config.mlb_statcast_test.toml` | `docs/statcast.gif` |
| attendance | `config/config.mlb_attendance_test.toml` | `docs/attendance.gif` |

Per the `making-a-gif` skill, for each config:

1. `make plan-gif CONFIG=config/config.mlb_<w>_test.toml` (from the led-ticker
   root) → recommended `--duration N`.
2. Apply the skill's colour/contrast judgement (the configs use
   `font_color = "random"` titles + brand-colored body, so no black-on-black
   risk; note any warnings it raises).
3. Render: `uv run python tools/render_demo/render.py
   config/config.mlb_<w>_test.toml -o /tmp/<w>.gif --duration N`, then copy the
   GIF into this repo's `docs/`.

### Preconditions & caveats (the plan must handle these)

- **Plugin importable in led-ticker's env.** The renderer loads `baseball.*`
  widgets through the plugin entry point, so `led-ticker-baseball` must be
  importable from the led-ticker venv. The plan verifies this first (e.g.
  `uv run python -c "import led_ticker_baseball"` from ../led-ticker) and
  installs editable if missing.
- **Live data.** The widgets fetch live StatsAPI data during render, so each
  capture reflects that moment. League-wide statcast/attendance want a slate
  with finals (afternoon/evening ET) for rich frames; pre-game captures show
  the documented fallback lines (`Yest`/short-date, `No games soon`). Render
  when there is live/final data; if a capture lands on a thin slate, note it
  and re-render later rather than committing an empty-looking GIF.
- **Non-determinism is acceptable** for demo GIFs — they illustrate the format,
  not specific games (same as the existing `scores.gif`).
- **Config availability.** The promotions config is on led-ticker `main`; the
  statcast config merged (PR #206). The **attendance** config is still in open
  PR #209 (branch `config/attendance-smoketest`) — the plan must ensure that
  file is present in the led-ticker checkout before rendering (merge #209 first,
  or render from its branch).

### Scheduling the render

Because the captures depend on live data, the rendering of Deliverable A is
**deferred to a scheduled run in the evening-ET window** (after a full slate of
games has gone Final — roughly 11:30 PM ET / 03:30 UTC), when league-mode
statcast/attendance have rich superlatives and team mode shows real
attendance + fill %. A scheduled agent (set up via the `/schedule` skill) does,
in the led-ticker checkout:

1. Confirm `led_ticker_baseball` imports from the led-ticker venv (install
   editable if not).
2. For each of the three smoketest configs: `make plan-gif` → render with the
   `making-a-gif` workflow → copy the GIF into this repo's `docs/`.
3. Eyeball each GIF for non-empty, legible frames; if a config landed on a thin
   slate, skip and let the next scheduled run retry rather than committing a
   weak capture.
4. Commit the GIFs onto the `docs-gifs-patterns` branch and report back.

Deliverable B (the README prose) needs no live data and is authored
immediately by the implementation plan; the scheduled run only supplies the
GIF files and confirms the `## Screenshots` image links resolve. The PR is
finalized once the GIFs land.

### README wiring

Add to the `## Screenshots` section, after the existing three GIFs, in the
existing one-line-alt-text style:

```markdown
![baseball.promotions — upcoming home-game giveaways and theme nights, highlighted promos in amber](docs/promotions.gif)

![baseball.statcast — league-wide daily superlatives (longest HR, hardest hit, fastest/slowest pitch)](docs/statcast.gif)

![baseball.attendance — ballpark crowds and conditions; league superlatives or one team's game](docs/attendance.gif)
```

## Deliverable B — README "Common patterns" section

A new `## Common patterns` section in `README.md`, placed **after `## Widgets`
and before `## Team codes`**. Three copy-paste playlist recipes; each is a
fenced `toml` block plus a one-line "what it shows". Recipes use only
already-documented widget options and led-ticker section knobs.

### Recipe 1 — My-team dashboard

One team across all four widgets in a `swap` rotation with the rolling-baseball
transition between sections.

```toml
[[playlist.section]]
mode = "swap"
transition = "baseball.roll_alternating"
hold_time = 8

[[playlist.section.widget]]
type = "baseball.scores"
team = "TOR"

[[playlist.section.widget]]
type = "baseball.standings"
teams = ["TOR"]

[[playlist.section.widget]]
type = "baseball.promotions"
team = "TOR"

[[playlist.section.widget]]
type = "baseball.attendance"
team = "TOR"
```

*Shows: your team's current series, its place in the standings, its next
home-game promotions, and the crowd/conditions at its game.*

### Recipe 2 — League roundup

League-wide daily superlatives — no `team`, so both widgets run in league mode.

```toml
[[playlist.section]]
mode = "swap"
hold_time = 8
scroll_step_ms = 35

[[playlist.section.widget]]
type = "baseball.statcast"

[[playlist.section.widget]]
type = "baseball.attendance"
```

*Shows: the day's longest HR / hardest hit / fastest + slowest pitch, then the
biggest/smallest crowd and fullest/emptiest park across all of MLB.*

### Recipe 3 — Gameday ticker

A minimal single-widget scrolling ticker for one team.

```toml
[[playlist.section]]
mode = "swap"
hold_time = 6

[[playlist.section.widget]]
type = "baseball.scores"
team = "NYY"
```

*Shows: just the tracked team's live/final/upcoming game line.*

### Shared-knobs note

A short paragraph after the recipes, pointing out cross-cutting conventions
(not new options — orientation only):

- Every widget takes the standard `title`, `font`, `font_color`, `bg_color`,
  `padding`, and `timezone` knobs (see each widget's table).
- Use `:baseball.ball:` in a `[playlist.section.title]` message for a themed
  header (as the smoketest configs do).
- **Pacing** — `hold_time` (dwell before/after a line) and `scroll_step_ms`
  (scroll cadence, lower = faster) are **led-ticker section settings**, not
  plugin options; they tune how overflowing lines (common in statcast /
  attendance / promotions) read on-panel. Link to the led-ticker config docs.

### Accuracy constraints (the plan must verify)

- Config field names must match the widgets' actual config:
  `scores`/`promotions`/`attendance` take `team` (string); `standings` takes
  `teams` (list); `statcast`/`attendance` league mode take no `team`. Verify
  against the widget classes / README tables before writing.
- `transition`/`mode`/`hold_time`/`scroll_step_ms` are led-ticker section keys
  — confirm spelling against led-ticker's config docs / an existing config
  (the smoketest configs use exactly these).
- Recipes are illustrative snippets (just the `baseball`-specific keys), matching
  how the per-widget README examples are already written — they are not
  full `config.toml` files.

## Out of scope

- New widget options or behavior changes (docs only).
- Committing new demo configs to the led-ticker repo (render from the existing
  smoketest configs; only the output GIFs land here).
- A `docs/site` MDX docs build (this plugin's surface is the README).

## Testing / verification

- `git`-tracked GIFs open and animate; each is a reasonable size (the existing
  `scores.gif`/`standings.gif` set the bar — keep new ones in the same ballpark).
- README renders: the three new image links resolve to the committed files;
  the three recipe TOML blocks are valid TOML and use real field names.
- No code changes → no pytest/ruff/pyright impact, but run the suite once to
  confirm the branch is clean.
