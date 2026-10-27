# Open Issues Sweep (#88, #93, #105, #106) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the four open issues on led-ticker-plugins with five parallel, isolated worktrees, each ending in an antagonist-approved draft PR; then port the hockey fixes to the open football branch.

**Architecture:** Five lanes, one git worktree each, all branched from `main`. Lanes are independent except the football port, which starts after the hockey lane's code has passed review. Each task is implemented by a fresh subagent, then reviewed by a fresh *antagonist* subagent who tries to break it; the implementer fixes and the antagonist re-reviews until it passes with no findings. Only then does the lane open a draft PR.

**Tech Stack:** Python 3.14, `uv` workspace, attrs, pytest (`asyncio_mode = "auto"`), ruff, pyright. Core (`led-ticker-core >= 4.30`) resolves from the sibling checkout `../led-ticker`.

**Spec:** The four GitHub issues plus James's decisions recorded under *Decisions* below. There is no separate design doc.

## Decisions (from James, 2026-10-26)

- **#106:** fix the behavior, not the docs. In `ticker` / `one_at_a_time` sections a pending celebration starts on the first live draw and **takes over the full panel** for its run, exactly as in slideshow. The slideshow path is unchanged.
- **#105:** `bg_color` is **scale-1 only everywhere**. Remove the `Fill(bg_color)` from the scale>1 celebration detail card. README states the contract.
- **#93:** **one PR per package** (baseball, flight, stocks).
- **Football:** port the #106 and #105 code fixes to the `feat/football-scores` branch (PR #107) after hockey passes review.
- **Delivery:** every lane ends in a **draft PR** in James's open-pr style. Nothing is merged. **No GitHub issue comments** are posted (memory rule: no posting without express approval).
- **My call:** #105 and #106 both edit `HockeyGameCard._celebrate`, so they share one worktree and one PR (two commits, PR closes both). Override at plan review if you want them split.

## Global Constraints

- Worktrees live as siblings of the repo, `/Users/james/projects/github/jamesawesome/led-ticker-plugins-<lane>`, so `../led-ticker` still resolves. Each needs its own `uv sync --extra dev`.
- Import `led_ticker` only from `led_ticker.plugin` (every plugin has an AST tripwire test).
- Python 3.14+, no `from __future__ import annotations`.
- Per-plugin coverage gate `fail_under = 90`; ruff check + format-check + pyright on `src` must pass.
- Hi-res text is never pixel-pinned in tests; assert extents, colors, call spies.
- Read the target plugin's `CLAUDE.md` before changing it; update it when an invariant changes.
- Commit messages: conventional (`fix(hockey): ...`), ending with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Example teams in hockey are `PHI` / `NYI`; football `PHI` / `NYG`.

## Review Focus

Each line is pinned to a test in the owning task.

1. **#106 — a goal queued while a self-started run is mid-flight.** It must wait for the current run to finish, then play on its own run; it must never shift the index of the goal currently playing. (Task 2)
2. **#106 — paused draws during a self-started run (transition compositing).** They paint the board, do not advance the run, and never consume; the run resumes where it was on the next live frame. (Task 2)
3. **#106 — slideshow regression.** A card that received `reset_frame()` must behave exactly as before: goals queued mid-visit wait for the next turn, consumption happens at visit entry. The whole existing `test_celebration.py` suite is the pin. (Task 2)
4. **#88 — eager fetch succeeds.** `run_monitor_loop` must be spawned with `immediate=False` so the happy path does not double-fetch. (Task 4)
5. **#93 — advertised enum drifts from validation.** Each widget's drift-guard test compares the hint's `display_type` tokens to the exact validation tuple, both directions. (Tasks 5–7)

## Process (applies to every lane)

1. **Worktree:** `git -C /Users/james/projects/github/jamesawesome/led-ticker-plugins worktree add ../led-ticker-plugins-<lane> -b <branch> main`, then `cd` there and `uv sync --extra dev`.
2. **Implement** the lane's task(s) with TDD, committing per task.
3. **Antagonist review:** dispatch a fresh subagent with the prompt in *Antagonist brief* below, scoped to the lane's diff (`git diff main...HEAD`). It returns findings or `PASS`. Implementer (fresh subagent, with the findings) fixes; loop until `PASS`. Hard cap 5 cycles; if still failing, stop and report to James.
4. **Verify** in the worktree: `uv run pytest plugins/<p> --cov=plugins/<p>/src`, `uv run ruff check plugins/<p> && uv run ruff format --check plugins/<p>`, `uv run pyright plugins/<p>/src`. Paste the tail of each into the PR body's test section only if the open-pr style asks for it (it does not; keep the body terse).
5. **PR:** invoke the `open-pr` skill (draft, no Shortcut card since this is a personal repo, restore block). Body says `Closes #N`.

### Antagonist brief

> You are reviewing a branch adversarially. Your job is to find a way the change is wrong, incomplete, or breaks something that worked. Read the issue(s), the plugin's `CLAUDE.md`, and the full diff. Then: (1) trace every code path the diff touches and name any input or sequence that now misbehaves; (2) run the plugin's full test suite, ruff, pyright and coverage gate yourself; (3) write at least one new probing test you believe might fail and run it, deleting it if it passes and the existing tests already cover the same thing; (4) check every documentation claim the diff adds or keeps against the source code it describes; (5) confirm the plan's Review Focus items for this task are actually pinned by a test. Report `PASS` only if you found nothing. Otherwise list findings most-severe first, each with file:line, a failing scenario, and the fix you would make. Do not edit the branch.

---

## Lane A: hockey — `fix/hockey-celebration-scroll-modes` (#105, #106)

Worktree `../led-ticker-plugins-hockey-fix`. Tasks 1 and 2 run in order on this branch.

### Task 1: `bg_color` is scale-1 only, README contract fixes (#105)

**Files:**
- Modify: `plugins/hockey/src/led_ticker_hockey/_card.py` (`_celebrate`, the `if name == "detail":` branch)
- Modify: `plugins/hockey/README.md` (option table rows `update_interval`, `padding`, `bg_color`, `font_color`; the `layout = "scoreboard"` next-game sentence)
- Modify: `plugins/hockey/CLAUDE.md` (one line under *Palette*: `bg_color` never paints at scale > 1)
- Test: `plugins/hockey/tests/test_celebration.py`

**Interfaces:**
- Produces: `_celebrate` no longer calls `canvas.Fill` for `bg_color`. Task 2 and the football port build on this shape.

- [ ] **Step 1: Write the failing test**

```python
def test_detail_ignores_bg_color_at_scale_gt1(bigsign):
    # #105: bg_color is a scale-1 option; the hi-res detail card paints its
    # own palette like every other hi-res renderer.
    card = _card(bigsign, bg_color=make_color(40, 0, 0))  # use the module's card factory
    card.queue_goals([_goal()])
    card.reset_frame()
    for _ in range(FLASH_FRAMES + 1):
        card.advance_frame()
    fill = mock.Mock()
    with mock.patch.object(bigsign, "Fill", fill):
        card.draw(bigsign)
    assert not any(c.args == (40, 0, 0) for c in fill.call_args_list)
```

Adapt the factory/goal helper names to what `test_celebration.py` already uses.

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest plugins/hockey/tests/test_celebration.py::test_detail_ignores_bg_color_at_scale_gt1 -v`
Expected: FAIL (Fill called with the bg color).

- [ ] **Step 3: Remove the `bg_color` fill from `_celebrate`**

Delete the three `if self.bg_color is not None: ... canvas.Fill(...)` lines in the `detail` branch. `render_detail` clears the panel itself (verify; if it does not, call `render_flash(..., False)`-style clear — check `_celebration.py` and keep whatever it uses for the flash-off frame).

- [ ] **Step 4: Run the suite**

Run: `uv run pytest plugins/hockey -q`
Expected: all pass.

- [ ] **Step 5: Verify each README claim against the source, then fix the wording**

For each row, read the code first and write what it actually does:
- `update_interval`: `NHLSource.want(live_interval=...)` takes `min(self._live_interval, live_interval)` with `LIVE_INTERVAL = 15` as the start value (`_source.py` ~line 76/117). Determine whether a value above 15 can slow polling (it cannot through `min` unless the start value changes); the issue claims the README is wrong, so state precisely what happens and remove the ambiguous "does not slow" phrasing. If the code and the issue disagree, the code wins and you say so in the PR body.
- `padding`: confirm where `padding` applies (`_card.py` crawl path `hold_padding` / `+ self.padding`; scale-1 ticker via `build_ticker_message`). Make the row say exactly those layouts.
- `bg_color` / `font_color`: "Scale-1 only. The hi-res renderers, including the goal celebration, paint their own palette."
- Next-game card: read `layouts/scoreboard.py` `_big_next` and the longboi variant; say which signs draw both chips and which draw one.

- [ ] **Step 6: Update `test_examples.py` if it asserts README wording, run suite + lint**

Run: `uv run pytest plugins/hockey -q && uv run ruff check plugins/hockey && uv run ruff format --check plugins/hockey && uv run pyright plugins/hockey/src`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add plugins/hockey
git commit -m "fix(hockey): bg_color is scale-1 only; README option contract fixes

Closes #105

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

### Task 2: celebrations play in `ticker` / `one_at_a_time` sections (#106)

**Files:**
- Modify: `plugins/hockey/src/led_ticker_hockey/_card.py` (`HockeyGameCard`: new field, `_celebrate`, `reset_frame`, module docstring)
- Modify: `plugins/hockey/CLAUDE.md` (*`reset_frame` consumption* invariant gains the self-started run)
- Modify: `plugins/hockey/README.md` (celebration section: one sentence that scroll-mode sections celebrate on the next live frame and the crawl keeps scrolling underneath)
- Test: `plugins/hockey/tests/test_celebration.py`

**Interfaces:**
- Consumes: `phase_at(frame, n_goals)`, `CELEBRATION_FRAMES`, `FLASH_FRAMES`, `DEMO_EVERY` as they exist.
- Produces: `HockeyGameCard._run_start: int | None` (attrs, `init=False`, default `None`). `None` means the run's frame origin is 0 (a visit started by `reset_frame`). An `int` means a **self-started** run that began at that `_frame_count` because no visit snapshot existed.

**Mechanism (the decision the implementer cannot make alone):**
- In `_celebrate`, before the existing `if not playing or self._frame_paused` check: if `self._playing is None and self.pending and not self._frame_paused and self._frame_count > 0`, set `self._playing = list(self.pending)` and `self._run_start = self._frame_count`.
- Compute the phase as `phase_at(self._frame_count - (self._run_start or 0), len(playing))`.
- When the phase is `None` **and** `self._run_start is not None`: the self-started run is over. Consume exactly as `reset_frame` does (`pending` minus `_shown`, clear `_shown`), set `_playing = None`, `_run_start = None`, and apply the demo re-arm (`_demo_visits += 1`; re-queue `demo_goals` when `% DEMO_EVERY == 0` and nothing pending). Return `False` so the board draws this frame.
- `reset_frame` sets `_run_start = None` (slideshow runs keep origin 0). Nothing else in `reset_frame` changes.
- `hold_time` is unchanged: core does not read it in scroll modes.
- Takeover: `draw()` already returns `canvas, canvas.width` while celebrating; in a side-by-side scroll that paints the full panel and skips later widgets for the tick. The underlying scroll position keeps advancing, so the crawl resumes about 80 px further on. Accepted; document it in README and CLAUDE.md.

- [ ] **Step 1: Write the failing tests**

```python
def _scroll_frames(card, canvas, n):
    """Tick like _scroll_side_by_side: advance then draw, never reset_frame."""
    out = []
    for _ in range(n):
        card.advance_frame()
        out.append(card.draw(canvas))
    return out

def test_scroll_mode_starts_pending_celebration_on_first_live_draw(bigsign):
    # #106: never reset_frame()'d (ticker / one_at_a_time sections)
    card = _card(bigsign); card.queue_goals([_goal()])
    with mock.patch("led_ticker_hockey._card.render_flash") as flash:
        _scroll_frames(card, bigsign, 2)
    # 1st advance -> _frame_count 1 -> run self-starts at origin 1 -> phase 0 (flash_on);
    # 2nd advance -> phase 1 (still flash_on). Two flash paints, zero board paints.
    assert flash.call_count == 2
    assert card._run_start == 1

def test_scroll_mode_run_consumes_once_shown(bigsign):
    card = _card(bigsign); card.queue_goals([_goal()])
    _scroll_frames(card, bigsign, CELEBRATION_FRAMES + 1)
    assert card.pending == [] and card._playing is None and card._run_start is None

def test_scroll_mode_goal_queued_mid_run_waits_for_next_run(bigsign):   # Review Focus 1
    card = _card(bigsign); g1, g2 = _goal(score=(1, 0)), _goal(score=(2, 0))
    card.queue_goals([g1])
    _scroll_frames(card, bigsign, 10)
    card.queue_goals([g2])
    assert card._playing == [g1]
    _scroll_frames(card, bigsign, CELEBRATION_FRAMES)       # g1's run ends; that draw paints the board
    assert card._playing is None and card.pending == [g2]
    _scroll_frames(card, bigsign, 1)                        # next live draw self-starts g2
    assert card._playing == [g2]

def test_scroll_mode_paused_draws_do_not_advance_or_consume(bigsign):   # Review Focus 2
    card = _card(bigsign); card.queue_goals([_goal()])
    _scroll_frames(card, bigsign, 1)                        # run self-started at frame 1 (that flash IS shown)
    card.pause_frame()
    with mock.patch("led_ticker_hockey._card.render_flash") as flash, \
         mock.patch("led_ticker_hockey._card.render_detail") as detail:
        for _ in range(CELEBRATION_FRAMES + 5):
            card.draw(bigsign)                              # transition compositing: board, no advance
    assert flash.call_count == 0 and detail.call_count == 0
    card.resume_frame()
    assert card.pending and card._playing is not None       # nothing consumed by paused draws
    _scroll_frames(card, bigsign, CELEBRATION_FRAMES)       # frames 2..81 finish the run
    assert card.pending == []

def test_scroll_mode_takes_over_full_panel(bigsign):
    card = _card(bigsign); card.queue_goals([_goal()])
    card.advance_frame()
    canvas, cursor = card.draw(bigsign, cursor_pos=-37)
    assert cursor == bigsign.width

def test_scroll_mode_demo_rearms_every_third_run(bigsign):
    card = _card(bigsign, demo_goals=(_goal(),)); card.queue_goals(list(card.demo_goals))
    for run in range(1, DEMO_EVERY + 1):
        _scroll_frames(card, bigsign, CELEBRATION_FRAMES + 1)
    assert card.pending  # re-armed after the 3rd completed run

def test_slideshow_path_unchanged_with_run_start(bigsign):   # Review Focus 3
    card = _card(bigsign); card.queue_goals([_goal()])
    card.reset_frame()
    assert card._run_start is None
    for _ in range(5): card.advance_frame()
    card.queue_goals([_goal(score=(2, 0))])
    assert len(card._playing) == 1          # mid-visit goal waits (existing contract)
```

Fix the first test's assertion once you have traced exactly which draw paints the first flash; the comment marks the uncertainty. Use the file's existing card/goal helpers.

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest plugins/hockey/tests/test_celebration.py -k scroll_mode -v`
Expected: FAIL (no flash painted, `_run_start` missing).

- [ ] **Step 3: Implement the mechanism in `_card.py` as specified above**

Also update the module docstring paragraph on consumption to describe both run kinds.

- [ ] **Step 4: Run the full hockey suite**

Run: `uv run pytest plugins/hockey --cov=plugins/hockey/src -q`
Expected: all pass, coverage >= 90.

- [ ] **Step 5: Reproduce the issue's demo render**

Run the demo render the issue used (a `mode = "ticker"` section with `layout = "ticker"`, bigsign and smallsign; see `plugins/hockey/examples/` and the core CLI's demo/render command in `../led-ticker`). Count flash frames; expected > 0 on both signs. Record the command and count in the commit body.

- [ ] **Step 6: CLAUDE.md + README, lint, commit**

Run: `uv run ruff check plugins/hockey && uv run ruff format --check plugins/hockey && uv run pyright plugins/hockey/src`

```bash
git add plugins/hockey
git commit -m "fix(hockey): celebrations play in ticker and one_at_a_time sections

Closes #106

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

- [ ] **Step 7: Antagonist review loop, then open-pr** (Process steps 3–5). PR title: `fix(hockey): celebrations in scroll-mode sections; bg_color is scale-1 only`.

---

## Lane A2: football port — on `feat/football-scores` (PR #107)

Worktree already exists: `/Users/james/projects/github/jamesawesome/led-ticker-plugins-football` (clean at plan time; re-check `git status` first and stop if dirty). Starts only after Lane A's antagonist returns `PASS`.

### Task 3: port #105 and #106 to `FootballGameCard`

**Files:**
- Modify: `plugins/football/src/led_ticker_football/_card.py` (same shape as hockey; `_playing` is the same name there, plays are `ScoringPlay`, snapshot key is `pre_extra_score`)
- Modify: `plugins/football/CLAUDE.md`, `plugins/football/README.md` (same two sentences as hockey, football wording)
- Test: `plugins/football/tests/test_celebration.py`

**Interfaces:**
- Consumes: the hockey diff from Tasks 1–2 (`git -C ../led-ticker-plugins-hockey-fix diff main...HEAD -- plugins/hockey/src/led_ticker_hockey/_card.py plugins/hockey/tests/test_celebration.py`).

- [ ] **Step 1: Port the Task 1 + Task 2 tests** with football names (`queue_plays`, `ScoringPlay`, `pre_extra_score` snapshots must be distinct). Run; expected FAIL.
- [ ] **Step 2: Port the code change**: remove the `bg_color` Fill from the detail branch; add `_run_start`, the self-start, relative phase, end-of-run consumption with demo re-arm.
- [ ] **Step 3: Run suite, lint, pyright** (`plugins/football`). Expected: pass, coverage >= 90.
- [ ] **Step 4: Commit on `feat/football-scores`**: `fix(football): celebrations in scroll-mode sections; bg_color is scale-1 only (port of hockey #105/#106)`.
- [ ] **Step 5: Antagonist review loop.** Then `git push` to update PR #107 (it is James's open draft; do **not** open a new PR or change its draft state). Report the new head SHA.

---

## Lane B: weather — `fix/weather-current-immediate-retry` (#88)

Worktree `../led-ticker-plugins-weather-fix`.

### Task 4: weather.current retries immediately after a failed boot fetch

**Files:**
- Modify: `plugins/weather/src/led_ticker_weather/weather.py:140-152` (`WeatherWidget.start`)
- Test: `plugins/weather/tests/test_weather.py`

**Interfaces:**
- Consumes: `run_monitor_loop(widget, interval, immediate=...)` from `led_ticker.plugin`; the forecast tests at `tests/test_forecast_widget.py:116-178` are the pattern to mirror (patch `led_ticker_weather.weather.spawn_tracked` and `...run_monitor_loop`).

- [ ] **Step 1: Write the failing tests**

```python
async def test_start_polls_immediately_after_failed_eager_fetch(monkeypatch): ...
    # patch fetch_current to raise; assert mock_loop.assert_called_once_with(w, 10800, immediate=True)
async def test_start_does_not_poll_immediately_after_successful_eager_fetch(monkeypatch): ...  # Review Focus 4
    # patch fetch_current to return a valid payload; assert immediate=False
```

- [ ] **Step 2: Run to verify they fail**: `uv run pytest plugins/weather/tests/test_weather.py -k immediately -v`. Expected: FAIL (`immediate` kwarg absent).
- [ ] **Step 3: Implement** in `start`: a local `fetched = False`, set `True` after `await widget.update()` succeeds; `spawn_tracked(run_monitor_loop(widget, update_interval, immediate=not fetched))`. Add a comment mirroring forecast's. No new attribute; `weather == ""` is not a safe sentinel because the API could return an empty condition.
- [ ] **Step 4: Suite, lint, pyright** for `plugins/weather`. Expected: pass.
- [ ] **Step 5: Commit**: `fix(weather): weather.current retries immediately after a failed boot fetch` + `Closes #88`.
- [ ] **Step 6: Antagonist loop, open-pr.**

---

## Lanes C/D/E: `_LIST_FIELD_HINTS` for `layout` (#93)

Common shape, copied from `plugins/pool/src/led_ticker_pool/monitor.py:237-244` and the drift guard at `plugins/pool/tests/test_monitor.py:852-890` (including its `_list_fields()` registry helper). A hint is a 3-tuple `(display_type, description, default_display)`; `display_type` is the enum as `'"a" | "b" | "c"'`. The hint lives on the **registered widget class** (the one passed to `api.widget(...)`), which is where core reads `_LIST_FIELD_HINTS` (`../led-ticker/src/led_ticker/app/factories.py:1358`).

Drift guard per widget (one test, parametrized over the package's widgets):

```python
def test_layout_hint_matches_validated_enum(widget_cls, valid_layouts):
    display_type = widget_cls._LIST_FIELD_HINTS["layout"][0]
    advertised = {tok.strip().strip('"') for tok in display_type.split("|")}
    assert advertised == set(valid_layouts)            # Review Focus 5, both directions
```

Plus one `_list_fields()`-driven test per package asserting the enum string appears in `--list-fields` output for one widget.

### Task 5: baseball — `fix/baseball-list-field-hints` (Lane C)

**Files:**
- Modify: `plugins/baseball/src/led_ticker_baseball/scores.py` (`MLBScoreMonitor`, enum `_MLB_VALID_LAYOUTS`, default `"auto"`)
- Modify: `standings.py` (`MLBStandingsMonitor`, `_STANDINGS_VALID_LAYOUTS`)
- Modify: `promotions.py` (`MLBPromotionsMonitor`, `_PROMO_VALID_LAYOUTS`)
- Modify: `statcast.py:335-339` — hoist the inline `("auto", "big", "long")` to module constant `_STATCAST_VALID_LAYOUTS` used by both `validate_config` and the hint
- Modify: `attendance.py:715-719` — same hoist to `_ATTENDANCE_VALID_LAYOUTS`
- Test: `plugins/baseball/tests/test_list_field_hints.py` (new)

- [ ] **Step 1: Write the failing tests** (parametrized drift guard over the five classes; one `_list_fields` smoke for `baseball.standings`).
- [ ] **Step 2: Run, expect FAIL** (`AttributeError: _LIST_FIELD_HINTS`).
- [ ] **Step 3: Add the five hints.** Descriptions come from each widget's README layout section, one short sentence per value; default `'"auto"'`.
- [ ] **Step 4: Suite, lint, pyright** for `plugins/baseball`. Expected: pass, coverage >= 90.
- [ ] **Step 5: Commit** `feat(baseball): declare _LIST_FIELD_HINTS for layout on all five widgets` + `Refs #93` (the issue closes when all three land; say `Refs`, not `Closes`).
- [ ] **Step 6: Antagonist loop, open-pr.**

### Task 6: flight — `fix/flight-list-field-hints` (Lane D)

**Files:**
- Modify: `plugins/flight/src/led_ticker_flight/widget.py` (`OverheadWidget`; enum `_LAYOUTS = ("auto", "ticker", "hero", "dashboard")`, default `"auto"`)
- Test: `plugins/flight/tests/test_list_field_hints.py` (new)

- [ ] Steps 1–6 as Task 5, single widget. Description must mention that `hero` / `dashboard` need scale > 1 and fall back to `ticker` (that is what `resolve_layout` does). Commit: `feat(flight): declare _LIST_FIELD_HINTS for layout` + `Refs #93`.

### Task 7: stocks — `fix/stocks-list-field-hints` (Lane E)

**Files:**
- Modify: `plugins/stocks/src/led_ticker_stocks/ticker.py` (`StocksTicker`; enum is `sorted(LAYOUTS)` from `layouts/__init__.py` = `"card" | "crawl" | "dashboard"`; there is **no** `"auto"` value — unset means "by panel width")
- Test: `plugins/stocks/tests/test_list_field_hints.py` (new)

- [ ] Steps 1–6 as Task 5. `default_display` is `"unset (chosen by panel width: crawl <= 160 px, dashboard >= 400 px, card between)"` — verify those thresholds against `resolve_layout` before writing them. The drift guard compares against `set(LAYOUTS)`. The last lane to land flips its PR body to `Closes #93`. Commit: `feat(stocks): declare _LIST_FIELD_HINTS for layout` + `Refs #93`.

---

## Orchestration

| Lane | Worktree | Branch | Tasks | Depends on |
|------|----------|--------|-------|------------|
| A | `../led-ticker-plugins-hockey-fix` | `fix/hockey-celebration-scroll-modes` | 1, 2 | — |
| A2 | `../led-ticker-plugins-football` (exists) | `feat/football-scores` | 3 | A passes review |
| B | `../led-ticker-plugins-weather-fix` | `fix/weather-current-immediate-retry` | 4 | — |
| C | `../led-ticker-plugins-baseball-hints` | `fix/baseball-list-field-hints` | 5 | — |
| D | `../led-ticker-plugins-flight-hints` | `fix/flight-list-field-hints` | 6 | — |
| E | `../led-ticker-plugins-stocks-hints` | `fix/stocks-list-field-hints` | 7 | — |

Lanes A–E start together. Lane A2 starts when A's antagonist returns `PASS`. When every lane has a PR URL, the orchestrator reports the six PRs (five new + #107 updated) with CI status, and leaves the worktrees in place for James to inspect. Three stale `prunable` worktrees from an earlier session exist under an old scratchpad path; leave them, mention them.
