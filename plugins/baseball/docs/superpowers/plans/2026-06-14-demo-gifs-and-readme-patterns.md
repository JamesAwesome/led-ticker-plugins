# Demo GIFs + README Common-Patterns Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `## Common patterns` recipes section to the README and wire the three new-widget demo GIFs into `## Screenshots`; the GIF *files* arrive via the scheduled render, this plan authors all the prose and image links.

**Architecture:** Docs-only change to `led-ticker-baseball/README.md` (no `src/` or test changes). Deliverable B (common-patterns prose) is written now. Deliverable A is split: the README image links are added now (so the PR is complete), and the binary GIFs land on the same `docs-gifs-patterns` branch via the scheduled cloud routine `trig_01CMFqn6Q8QmfRtuzpMM4nCu` (~11:30 PM ET). Spec: `docs/superpowers/specs/2026-06-14-demo-gifs-and-readme-patterns-design.md`.

**Tech Stack:** Markdown. Verification: `tomllib` parse of the recipe blocks + field-name cross-check against the widget classes; no pytest/ruff/pyright impact (but run the suite once to confirm the branch is clean).

**Branch:** work on `docs-gifs-patterns` (already created; the spec + scheduling commits are on it). Never commit to main.

**Verified field names (use exactly these in recipes):**
- `baseball.scores` → `team` (string)
- `baseball.standings` → `teams` (list of strings)
- `baseball.promotions` → `team` (string)
- `baseball.statcast` → no team; optional `stats` (list)
- `baseball.attendance` → optional `team` (string); omit for league mode; optional `stats` (list)
- led-ticker section keys used: `mode`, `transition`, `hold_time`, `scroll_step_ms`; widget tables: `[[playlist.section.widget]]`.

---

### Task 1: Add the `## Common patterns` section

**Files:**
- Modify: `README.md` (insert a new `## Common patterns` section between `## Widgets` (line ~50–230) and `## Team codes` (line ~231))

- [ ] **Step 1: Insert the section**

Insert this block immediately before the `## Team codes` line in `README.md`:

````markdown
## Common patterns

Recipes that combine the widgets above. Each block shows just the
baseball-specific keys — drop the widgets into a playlist section of your
`config/config.toml` (see the [first-config tutorial](https://docs.ledticker.dev/tutorial/02-first-config/) for the surrounding structure).

### My-team dashboard

One team across every widget, rotating with the rolling-baseball transition.

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

Shows your team's current series, its place in the standings, its next
home-game promotions, and the crowd and conditions at its game.

### League roundup

League-wide daily superlatives — omit `team` and both widgets run in league
mode.

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

Shows the day's longest home run, hardest-hit ball, and fastest and slowest
pitch, then the biggest and smallest crowd and the fullest and emptiest park
across all of MLB.

### Gameday ticker

A minimal single-team scrolling line.

```toml
[[playlist.section]]
mode = "swap"
hold_time = 6

[[playlist.section.widget]]
type = "baseball.scores"
team = "NYY"
```

Shows just the tracked team's live, final, or upcoming game line.

### Shared knobs

- Every widget accepts the standard `title`, `font`, `font_color`, `bg_color`,
  `padding`, and `timezone` options — see each widget's table above.
- Put `:baseball.ball:` in a `[playlist.section.title]` message for a themed
  header.
- **Pacing** is tuned with `hold_time` (dwell before and after a line) and
  `scroll_step_ms` (scroll cadence — lower is faster). These are
  [led-ticker section settings](https://docs.ledticker.dev/), not plugin
  options; they control how an overflowing line (common in the statcast,
  attendance, and promotions widgets) reads on the panel.

````

- [ ] **Step 2: Verify the recipe TOML is valid and uses real field names**

Run:

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-baseball
python3 - <<'EOF'
import re, tomllib
md = open("README.md").read()
# Extract the toml blocks inside the Common patterns section.
section = md.split("## Common patterns", 1)[1].split("## Team codes", 1)[0]
blocks = re.findall(r"```toml\n(.*?)```", section, re.DOTALL)
assert len(blocks) == 3, f"expected 3 recipe blocks, got {len(blocks)}"
for i, b in enumerate(blocks, 1):
    cfg = tomllib.loads(b)  # raises if invalid TOML
    widgets = [w for s in cfg["playlist"]["section"] for w in s.get("widget", [])]
    for w in widgets:
        t = w["type"]
        assert t.startswith("baseball."), t
        # Field-name guards: standings uses `teams`; the rest use `team`.
        if t == "baseball.standings":
            assert "teams" in w and "team" not in w, w
        if t in ("baseball.scores", "baseball.promotions"):
            assert "team" in w and "teams" not in w, w
        if t == "baseball.statcast":
            assert "team" not in w, w
    print(f"recipe {i}: ok ({len(widgets)} widgets)")
print("all recipes valid TOML with correct field names")
EOF
```

Expected: `recipe 1/2/3: ok` and `all recipes valid TOML with correct field names`.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: add Common patterns recipes to the README"
```

---

### Task 2: Wire the three demo-GIF image links into `## Screenshots`

**Files:**
- Modify: `README.md` (`## Screenshots` block, after the `roll-transition.gif` line)

- [ ] **Step 1: Add the image links**

In `README.md`, immediately after this existing line:

```markdown
![baseball.roll — rolling-baseball sprite transition between widgets](docs/roll-transition.gif)
```

insert:

```markdown
![baseball.promotions — upcoming home-game giveaways and theme nights, highlighted promos in amber](docs/promotions.gif)

![baseball.statcast — league-wide daily superlatives (longest HR, hardest hit, fastest/slowest pitch)](docs/statcast.gif)

![baseball.attendance — ballpark crowds and conditions; league superlatives or one team's game](docs/attendance.gif)
```

- [ ] **Step 2: Note the GIF files arrive via the scheduled render**

The three `docs/*.gif` files do not exist yet — they are committed onto this
same `docs-gifs-patterns` branch by the scheduled cloud routine
`trig_01CMFqn6Q8QmfRtuzpMM4nCu` (~11:30 PM ET, watch
https://claude.ai/code/routines/trig_01CMFqn6Q8QmfRtuzpMM4nCu). The image
links are intentionally added ahead of the files so the PR is content-complete;
they resolve once the render lands. Confirm the alt-text widget names match the
README's existing one-line style (they do — compare to the scores/standings
lines above).

- [ ] **Step 3: Update the intro line to mention the new widgets (optional polish)**

The README's first paragraph says "MLB scores and standings widgets…". Update
it to reflect the full set:

In `README.md` line 3, change:

```markdown
MLB scores and standings widgets, a rolling-baseball sprite transition, and a `:baseball.ball:` emoji for [led-ticker](https://github.com/JamesAwesome/led-ticker). Live game data comes from MLB's free StatsAPI — no API key required.
```

to:

```markdown
MLB scores, standings, promotions, Statcast, and attendance widgets, a rolling-baseball sprite transition, and a `:baseball.ball:` emoji for [led-ticker](https://github.com/JamesAwesome/led-ticker). Live game data comes from MLB's free StatsAPI — no API key required.
```

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: add promotions/statcast/attendance demo GIFs to Screenshots"
```

---

### Task 3: Final verification + open the PR

**Files:** none (verification + PR)

- [ ] **Step 1: Confirm the branch is otherwise clean**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-baseball
uv run pytest -q
uv run ruff check src tests
```

Expected: full suite passes, lint clean (this change is docs-only, so nothing
should have moved — this just confirms the branch state).

- [ ] **Step 2: Confirm the three image links reference the agreed filenames**

```bash
grep -n "docs/promotions.gif\|docs/statcast.gif\|docs/attendance.gif" README.md
```

Expected: three matches, one per widget. (The files themselves land via the
scheduled render — `ls docs/*.gif` will not list them until then.)

- [ ] **Step 3: Push and open the PR**

```bash
git push -u origin docs-gifs-patterns
gh pr create --title "docs: common-patterns recipes + demo GIFs for the new widgets" --body "$(cat <<'EOF'
## Summary
- New `## Common patterns` README section: three copy-paste playlist recipes (my-team dashboard, league roundup, gameday ticker) plus a shared-knobs note.
- Wires `docs/promotions.gif` / `docs/statcast.gif` / `docs/attendance.gif` into `## Screenshots` and updates the intro to list the full widget set.

## Notes
- Docs-only; no `src/` or test changes.
- The three GIF **files** are rendered and committed onto this branch by a scheduled cloud run (~11:30 PM ET, when a full slate is Final) — the image links are added ahead so the PR is content-complete and resolve once the render lands. Routine: trig_01CMFqn6Q8QmfRtuzpMM4nCu.
- Recipe TOML blocks were validated (parse + field-name check: standings→`teams`, others→`team`, statcast→league).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 4: Leave the PR open until the GIFs land**

Do not merge until the scheduled render has pushed the GIF files to this branch
(so the published README has working images). Re-run CI / refresh the PR after
the render reports back.

---

## Spec coverage self-check (for the reviewer)

- Deliverable B (common-patterns section, 3 recipes + shared-knobs note, placement after Widgets) → Task 1
- Field-name accuracy constraints (standings `teams`; others `team`; statcast league) → Task 1 Step 2 (automated check)
- Deliverable A README wiring (3 image links, existing alt-text style, intro update) → Task 2
- Scheduled render supplies the GIF files; PR opened content-complete, held until files land → Tasks 2–3
- Out of scope honored: no new widget options, no led-ticker config commits, no MDX docs build (README only) → whole plan is README-only
