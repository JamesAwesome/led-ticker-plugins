# Sweep Follow-ups Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Act on the meta-antagonist's findings over the 2026-10-26 sweep: re-decide #105, fix the hi-res scroll-section hang across plugins, fix celebration gap (b), correct gap (a) docs, remove the monitor-loop splay from hockey and tennis, pin Python 3.14, and land the pre-merge minors.

**Architecture:** Same lane model as `2026-10-26-open-issues-sweep.md`: one worktree per lane, fresh implementer, antagonist review until clean, draft PR. Football (`feat/football-scores`, PR #107) belongs to another session; its deltas were sent to that session and are **not** touched here.

**Spec:** `.superpowers/sdd/2026-10-26-open-issues-sweep/progress.md` (meta-antagonist findings R1–R11) and James's decisions below.

## Decisions (James, 2026-10-27)

- **#105:** `bg_color` **applies at every scale**. Delete the `ScaleMemo`, the `bg_color` property / `_bg_color` alias, the hi-res leftmost clears and the three-case residual docs. Core already fills it; the celebration frame fills the configured bg (else black) at every scale before painting.
- **Hang fix:** all plugins, one PR, separate from #112. #112 keeps hockey's own hang fix so `Closes #106` is true on hi-res.
- **Football:** inform the other session; do not touch its branch.

## Global Constraints

- Every venv must run **Python 3.14** (`uv sync --extra dev --python 3.14`); CI is 3.14 / FreeType 2.14.3. Verify with `uv run python -c "import sys,PIL.features as f;print(sys.version.split()[0], f.version('freetype2'))"` before trusting a green suite.
- Import `led_ticker` only from `led_ticker.plugin`. Python 3.14+, no `from __future__ import annotations`. Coverage gate 90; ruff check + format-check + pyright clean; pristine test output.
- Core draw contract: `draw()` returns `(canvas, end_x)` where `end_x` is **absolute** (`cursor_pos + content_width [+ padding]`), like `widgets/message.py`. Core pops a widget only when `end_x < 0`.
- Commit trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- No GitHub comments. Draft PRs only, open-pr style, restore block.

## Review Focus

1. **Hang fix — a held hi-res card at `cursor_pos < 0` must paint shifted and clipped**, not at x=0, and return `cursor_pos + canvas.width`; a regression test runs core's real `_scroll_one_by_one` with two cards and a watchdog. (Tasks 1, 2)
2. **#105 redo — every-scale fill must not reintroduce the overlay bug:** the celebration clear still happens before every frame, filling bg or black. (Task 1)
3. **Gap (b) — a paused `reset_frame` must leave `_playing = None`; a live one must snapshot.** Slideshow path (`_show_one` live reset after a paused transition reset) unchanged. (Task 1)
4. **Splay — `run_monitor_loop(..., splay=False)` with the exact call asserted;** the shared source's own rate limiting is what protects the API. (Tasks 1, 3)
5. **Python pin — `.python-version` is honored by `uv sync` in a fresh clone;** the two premise tests pass on 3.14 and are skipped (not failed) on other FreeType versions. (Task 4)

---

## Lane H: hockey — continue `fix/hockey-celebration-scroll-modes` (PR #112)

Worktree `../led-ticker-plugins-hockey-fix` (venv already on 3.14).

### Task 1: #105 redo, hang fix, gap (b), gap (a) docs, splay, PR text

**Files:** `plugins/hockey/src/led_ticker_hockey/{_card.py,_paint.py,scores.py,layouts/scoreboard.py,layouts/crawl.py}`, `plugins/hockey/{CLAUDE.md,README.md}`, `plugins/hockey/tests/{test_celebration.py,test_card_dispatch.py,test_scores.py}`.

**Reference for the hang fix:** football commit `7c3c178` in `/Users/james/projects/github/jamesawesome/led-ticker-plugins-football` (read-only): `render_scoreboard` takes a LOGICAL `x_offset` painted through `_paint.ShiftedReal` (clipped both edges); card returns `cursor_pos + canvas.width`; a self-started run freezes the effective cursor (`_x_shift`) until the raw cursor next increases. Mirror the design; football's crawl still returns `w + self.padding`, which is wrong — hockey's crawl must return `cursor_pos + w + self.padding`.

- [ ] **Step 1 (#105 redo, TDD):** delete `ScaleMemo`, `scale_memo` field, `_bg_color` alias and the `bg_color` property; `bg_color` is a plain attrs field again. Delete the hi-res leftmost clear in `draw()`. `_celebrate`'s per-frame clear becomes: `Fill(bg_color)` if set else `real.Clear()`, at every scale. Delete `test_slideshow_visit_cached_bg_never_shows_at_scale_gt1`, the memo tests and the scale-1-only tests; keep/adjust the takeover-clear tests; add `test_core_fill_of_bg_color_shows_at_every_scale` (Fill with `card.bg_color` then draw at scale 4 → bg pixels remain outside painted text). Remove `scores.py` `_scale_memo`. README `bg_color`/`font_color` rows: bg "Background fill at every scale (core paints it under every renderer)"; font_color stays scale-1 ticker only. CLAUDE.md: drop the Palette residual paragraph and `ScaleMemo` mentions. Commit `fix(hockey): bg_color applies at every scale (#105 premise was wrong)`.
- [ ] **Step 2 (hang fix, TDD):** failing test first: `test_scroll_one_by_one_two_hires_cards_completes` builds a real `Ticker`-free harness or drives core's `_scroll_one_by_one` with two cards on bigsign under `asyncio.wait_for(..., 1.5)` with `asyncio.sleep` patched; expect timeout on the current code. Then: `render_scoreboard(..., x_offset: int)` via a `ShiftedReal` wrapper in `_paint.py` (clip at both edges), card returns `cursor_pos + canvas.width` for held layouts and `cursor_pos + w + self.padding` for the crawl; `_x_shift` freeze during a self-started run (reset when the raw cursor increases). Takeover still returns `canvas.width`. Update the module docstring's return contract. CLAUDE.md gains a **Draw return is absolute** invariant. Commit `fix(hockey): hi-res board honours cursor_pos; takeover freezes the scroll`.
- [ ] **Step 3 (gap (b), TDD):** test: `pause_frame(); reset_frame(); resume_frame()`, scroll 200 frames, queue g2, scroll → g2 celebrates; and `reset_frame()` live still snapshots. Fix: in `reset_frame`, when `self._frame_paused`, consume as now but set `_playing = None`. Remove gap (b) text from CLAUDE.md/README. Commit `fix(hockey): a transition reset no longer disables self-started celebrations`.
- [ ] **Step 4 (gap (a) docs):** replace the gap (a) sentence in README + CLAUDE.md with: only a goal landing while the LAST card is already in the section's end-of-scroll hold is cut, to the remainder of the section `hold_time` (default 3 s), and resumes on the card's next pass; `hold_time >= 7` avoids it. Add: celebration and demo timing in scroll modes count scroll ticks (`scroll_step_ms`, default 50 ms). Commit `docs(hockey): precise end-of-scroll-hold limit; timing scales with scroll_step_ms`.
- [ ] **Step 5 (splay, TDD):** test asserts `run_monitor_loop(widget, interval, splay=False)` (mirror football 3f01c54 and its test). Fix `scores.py:~316`. README cadence line is now true. Commit `fix(hockey): poll without core's startup splay`.
- [ ] **Step 6:** gates on 3.14; demo render flash counts before/after for the PR body (report the real number). Report.
- [ ] **Step 7 (controller):** antagonist review loop; then push and edit #112's body: new title `fix(hockey): celebrations in scroll-mode sections; bg_color at every scale; hi-res cards scroll`, correct flash counts, keep `Closes #105` + `Closes #106`, drop the hi-res disclosure, mention the football coordination.

## Lane X: cross-plugin hang fix — `fix/hires-draw-cursor-pos`

Worktree `../led-ticker-plugins-hires-cursor`.

### Task 2: cursor-relative returns in tennis, baseball, weather.forecast

**Files:** `plugins/tennis/src/led_ticker_tennis/_card.py:99,108`; `plugins/baseball/src/led_ticker_baseball/{_card.py:135,159,_promo_card.py:91,104,_standings_card.py:88,_statcast_card.py:99,_attendance_card.py:132,_hires_line.py:118}`; `plugins/weather/src/led_ticker_weather/forecast.py:134,146`; one new test per plugin `tests/test_scroll_mode_returns.py`.

- [ ] **Step 1 (TDD):** per plugin, a failing test that drives core's real `Ticker._scroll_one_by_one` (or the minimal equivalent: advance+draw loop asserting the returned end goes below 0 within `canvas.width + content` ticks) with two hi-res cards on a bigsign fixture under a watchdog. Also a direct unit test: `draw(canvas, cursor_pos=-40)` returns `-40 + expected_width`.
- [ ] **Step 2:** held layouts return `cursor_pos + canvas.width`; crawls return `cursor_pos + advance + padding`. Where a held renderer paints at x=0 regardless of cursor, add the minimal shift/clip so a partially scrolled card paints at its cursor (mirror hockey's `ShiftedReal` from Task 1 / football 7c3c178, per plugin; keep it in each plugin, no shared helper). Do not change slideshow behavior at cursor 0.
- [ ] **Step 3:** gates per plugin on 3.14 (`uv run pytest plugins/<p> --cov=plugins/<p>/src -q`, ruff, format, pyright). One commit per plugin: `fix(<plugin>): hi-res draw() returns an absolute end so scroll sections advance`.
- [ ] **Step 4 (controller):** antagonist; draft PR `fix: hi-res cards return an absolute end position so ticker/one_at_a_time sections advance`, body lists the per-plugin hunks and the core contract, `Refs` the issue James files later.

## Lane T: tennis splay — `fix/tennis-splay`

Worktree `../led-ticker-plugins-tennis-splay`.

### Task 3: `splay=False` in tennis
- [ ] TDD mirror of football 3f01c54 at `plugins/tennis/src/led_ticker_tennis/scores.py:~179` + test; README cadence check; gates; commit `fix(tennis): poll without core's startup splay`; antagonist; draft PR.

## Lane P: Python pin — `chore/pin-python-3.14`

Worktree `../led-ticker-plugins-py314`.

### Task 4: `.python-version`, premise-test skipif, commit the two plan files
- [ ] Add root `.python-version` = `3.14`. Confirm `uv sync` in a fresh temp clone picks 3.14. Guard the two premise tests (`plugins/stocks/tests/test_glyph_separation.py::test_the_thin_font_threshold_fuses_bold_symbols`, `plugins/baseball/tests/test_glyph_separation.py::test_the_thin_font_threshold_fuses_bold_text`) with `pytest.mark.skipif(PIL.features.version("freetype2") != "2.14.3", reason=...)`; verify they run (not skip) on 3.14 and would skip on 3.15. Add a CONTRIBUTING.md line. Copy `docs/superpowers/plans/2026-10-26-open-issues-sweep.md` and `2026-10-27-sweep-followups.md` from the main checkout and commit them. Gates for stocks + baseball. Commits: `chore: pin Python 3.14 for local envs; guard FreeType premise tests`, `docs: plans for the 2026-10 issue sweep`. Antagonist; draft PR.

## Lane M: pre-merge minors on open PRs

### Task 5: baseball #111 — `fix/baseball-list-field-hints`
- [ ] Build the statcast/attendance `validate_config` error strings from `_STATCAST_VALID_LAYOUTS` / `_ATTENDANCE_VALID_LAYOUTS` (as scores/standings/promotions do); parametrize the `_list_fields` test over all five widgets. Gates on 3.14 (glyph test now passes). Commit; antagonist (sonnet); push; edit PR body: remove the "pre-existing failure" paragraph, replace with one line "local suites need Python 3.14 (see #<pin PR>)".

### Task 6: stocks #109 — `fix/stocks-list-field-hints`
- [ ] Hoist `160`/`400` in `layouts/__init__.py:37,39` into `CRAWL_MAX_WIDTH` / `DASHBOARD_MIN_WIDTH`; the hint's default_display is built from them; the list-fields test asserts the literal numbers. Gates on 3.14. Commit; antagonist (sonnet); push; same PR-body edit.

## Orchestration

| Lane | Worktree | Branch | Depends on |
|---|---|---|---|
| H | `../led-ticker-plugins-hockey-fix` | `fix/hockey-celebration-scroll-modes` (#112) | — (reads football 7c3c178 read-only) |
| X | `../led-ticker-plugins-hires-cursor` | `fix/hires-draw-cursor-pos` | — |
| T | `../led-ticker-plugins-tennis-splay` | `fix/tennis-splay` | — |
| P | `../led-ticker-plugins-py314` | `chore/pin-python-3.14` | — |
| M | `../led-ticker-plugins-baseball-hints`, `../led-ticker-plugins-stocks-hints` | #111, #109 | — |

Controller housekeeping (no subagent): `git worktree remove` the merged `-hockey`, `-hockey-release`, `-weather-forecast` trees after confirming clean; leave `-football` alone.
