# Smallsign Sport Icons Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every football and hockey smallsign card carries an 8×8 sport icon, and basketball upcoming cards carry the ball when it fits, so a mixed sports rotation is readable at a glance.

**Architecture:** Each plugin gets an 8×8 `PixelData` sprite (football/hockey new, basketball existing), registered as plugin emoji and painted directly onto the real canvas by its scale-1 band board. Placement is computed from the board's existing column math; the icon is recorded in `shape_extents` so the existing clearance tripwires guard it, and it is always the element that drops when space runs out.

**Tech Stack:** Python 3.14, attrs, `led_ticker.plugin` public surface, pytest, uv workspace (`led-ticker-plugins`).

**Spec:** `docs/superpowers/specs/2026-10-29-smallsign-sport-icons-design.md`

**Worktree:** `/Users/james/projects/github/jamesawesome/led-ticker-plugins-sport-icons` (branch `spec/smallsign-sport-icons`, based on `origin/main`). Verify `pwd` and `git branch --show-current` before any git operation.

## Global Constraints

- Smallsign (scale-1 band boards) only; scale > 1 renderers, celebrations and the `ticker` crawl are untouched.
- Plugins import only from `led_ticker.plugin`. No `from __future__ import annotations`.
- The icon never collides: it keeps `_GAP` (6 px) from everything except the one element it labels, which sits `_ICON_GAP` (2 px) to its right. When that can't hold, the icon is not drawn.
- Pre-existing elements on live/final cards do not move. Existing pixel-position tests for those cards must pass untouched.
- New emoji slugs: `:football.ball:`, `:hockey.puck:` (lo-res only).
- LED colours: no `(0, 0, 0)` pixels in sprites; the puck must not be near-black.
- Sprite art lands as the spec's drafts; final art is approved by the user (Task 4) before any demo GIF is rendered or anything is released.
- Tests: `uv run pytest plugins/<name>`; lint `uv run ruff check plugins/<name>`; types `uv run pyright plugins/<name>/src` (pyright is pre-push only — run it before pushing).

## Shared decisions (all three boards)

- Constants in each `_scoreboard.py`: `_ICON = 8`, `_ICON_GAP = 2`.
- Each `_paint.py` gains `sprite(real, pixels: PixelData, x: int, y: int) -> None`, which sets each `(dx, dy, r, g, b)` at `(x + dx, y + dy)`, clipped like `px`.
- The icon is appended to `shape_extents` with INCLUSIVE x bounds, matching that board's existing tuple shape: football/hockey `("ICON", x0, x0 + 7, band)`; basketball `("ICON", x0, x0 + 7)`.
- Each plugin's clearance test helper learns one exception: the gap between an `"ICON"` item and the item that starts immediately right of it may be `_ICON_GAP`; every other pair still needs ≥ 6. (Football's and hockey's helpers compare end-exclusive text extents; convert the icon's inclusive `x1` to `x1 + 1` the way basketball's helper already does for shapes.)
- All x positions include `ox` (cursor_pos); the icon's top row is the band's top row plus `y_offset`.

## Review Focus

1. **Scroll sections** (`cursor_pos != 0`): the icon must move with the board, never stay at x=0 → `test_band_board_honours_cursor_pos` extended in Tasks 1–3.
2. **PushUp/PushDown** (`y_offset != 0`): the icon rides the offset like the chips → `test_band_board_shapes_follow_y_offset` / `test_band_board_follows_y_offset` extended in Tasks 1–3.
3. **Crowded football top band** (`WSH 48`, stale, `END Q3`, `1ST & GOAL` on the top band): the icon drops instead of crowding left content → `WORST_*` clearance params now include the icon (Task 1), and a forced-crowding test asserts no `ICON`.
4. **Stale basketball upcoming card:** the ball never costs `STALE`, the weekday, AM/PM or the day label → `test_future_ball_never_costs_stale` (Task 3).
5. **Football bye week with long codes** (`WSH @ JAX BYE` + `SUN NOV 8`): matchup + icon still clear the date, or the icon drops → `test_future_icon_bye_long_codes_clear` (Task 1).

---

### Task 1: Football — `:football.ball:` emoji and icon on every smallsign card

**Files:**
- Create: `plugins/football/src/led_ticker_football/emoji.py`
- Modify: `plugins/football/src/led_ticker_football/__init__.py` (register)
- Modify: `plugins/football/src/led_ticker_football/_paint.py` (add `sprite`)
- Modify: `plugins/football/src/led_ticker_football/_scoreboard.py` (future branch ~L114-141; live/final status ~L203-211; module docstring geometry)
- Create: `plugins/football/tests/test_emoji.py`
- Modify: `plugins/football/tests/test_scoreboard.py`, `plugins/football/tests/test_smoke.py`
- Modify: `plugins/football/README.md` (Layouts → Smallsign bullet + next-game sentence; mention `:football.ball:`), `plugins/football/CLAUDE.md` (geometry/tripwire note)

**Interfaces:**
- Produces: `led_ticker_football.emoji.BALL: PixelData` (8×8); emoji `football.ball`; `_paint.sprite(real, pixels, x, y) -> None`; `_scoreboard._ICON = 8`, `_scoreboard._ICON_GAP = 2`; `("ICON", x0, x1_inclusive, band)` entries in `FootballBandBoard.shape_extents`.

- [ ] **Step 1: Write the failing emoji tests** in `tests/test_emoji.py`:

```python
from led_ticker_football.emoji import BALL

def test_ball_lowres_fits_8x8_without_black():
    assert BALL
    assert all(0 <= x < 8 and 0 <= y < 8 for x, y, *_ in BALL)
    assert all((r, g, b) != (0, 0, 0) for *_, r, g, b in BALL)
```

and in `test_smoke.py`, after loading plugins: `assert "football.ball" in emoji_slugs()` (import `emoji_slugs` from `led_ticker.plugin`).

- [ ] **Step 2: Run** `uv run pytest plugins/football/tests/test_emoji.py plugins/football/tests/test_smoke.py -v` — expect FAIL (ImportError / missing slug).

- [ ] **Step 3: Implement `emoji.py`.** Build `BALL` from a `_ROWS` string grid exactly like `basketball/emoji.py`, using the spec's draft:

```
"....BBB.", "..BBBBBB", ".BBBWBBB", ".BBWBWBB",
"BBWBWBB.", "BBBWBBB.", "BBBBBB..", ".BBB...."
```
`B = (160, 80, 30)`, `W = (255, 255, 255)`. Register in `register(api)`: `api.emoji("ball", BALL)`.

- [ ] **Step 4: Run Step 2's command** — expect PASS.

- [ ] **Step 5: Write the failing board tests** in `test_scoreboard.py` (use `_board`, `_spy_texts`, `TOP`, `NEXT`, `LIVE`, `HALF`, `FINAL_OT`, `BYE`):
  - `test_future_icon_left_of_matchup`: draw `NEXT`; the board's `shape_extents` holds `("ICON", 0, 7, 0)`; the first text call on band 0 starts at `x = sb._ICON + sb._ICON_GAP` (10); the bottom band's venue still starts at `sb.X_ABBREV`.
  - `test_live_and_final_icon_left_of_status`: for each of `LIVE`, `HALF`, `FINAL_OT`, the `ICON` extent's end-exclusive `x1` (inclusive `x1 + 1`) plus `_ICON_GAP` equals the x0 of the band-0 status text call (`Q4` / `HALF` / `FINAL`).
  - `test_live_existing_columns_unchanged`: the existing `test_band_board_live_columns` assertions pass unmodified (no edit to that test).
  - `test_icon_drops_when_top_band_crowded`: monkeypatch the board's font width so band 0's left content ends within `_GAP` of `x_status - _ICON_GAP - _ICON` (or build a game whose top band carries `1ST & GOAL` plus `END Q3`-length status), and assert no `"ICON"` in `shape_extents`.
  - `test_future_icon_bye_long_codes_clear`: `dataclasses.replace(BYE, away="WSH", home="JAX")` with `bye=True`; `_assert_band_clearance(_coalesce(calls), 160)` passes (the icon is present or dropped, but never crowding).
  - Extend `_assert_band_clearance` with the `ICON` exception from Shared decisions; the existing `WORST_*` / typical / future clearance tests now cover the icon automatically.
  - Extend `test_band_board_honours_cursor_pos` and `test_band_board_shapes_follow_y_offset`: the `ICON` extent shifts by `cursor_pos`, and its pixels shift by `y_offset`.

- [ ] **Step 6: Run** `uv run pytest plugins/football/tests/test_scoreboard.py -v` — expect the new tests to FAIL.

- [ ] **Step 7: Implement in `_scoreboard.py`.**
  - Future branch: `sprite(real, BALL, ox, y_offset)`, record `("ICON", ox, ox + 7, 0)`, start the matchup at `ox + _ICON + _ICON_GAP`. Before drawing, measure the matchup (+ ` BYE`): if `_ICON + _ICON_GAP + matchup_w + _GAP > width - w(top)`, skip the icon and start the matchup at `ox + X_ABBREV` as today.
  - Live/final: track `top_end`, the max end-exclusive x of everything drawn on band 0 before the status (abbrev, score, dot, pips, down & distance, `STALE`). The chip counts too, since it's drawn first. Then `status_x = ox + width - w(top)`; `icon_x = status_x - _ICON_GAP - _ICON` (with an empty `top`, use `ox + width - _ICON`). Draw and record the icon only if `icon_x >= top_end + _GAP`.
  - Update the module docstring's geometry paragraph.

- [ ] **Step 8: Run** `uv run pytest plugins/football -v` — expect all PASS. Then run `uv run ruff check plugins/football`, and `uv run ruff format --check plugins/football`, which should be clean.

- [ ] **Step 9: Update `README.md` and `CLAUDE.md`.** Smallsign layout: the football icon sits before the matchup on next-game cards and left of the quarter / `HALF` / `FINAL` on live and final cards, and drops when crowded. Also document the `:football.ball:` emoji.

- [ ] **Step 10: Commit**

```bash
git add plugins/football
git commit -m "feat(football): smallsign sport icon + :football.ball: emoji"
```

---

### Task 2: Hockey — `:hockey.puck:` emoji and icon on every smallsign card

Same shape as Task 1; differences only:

**Files:**
- Create: `plugins/hockey/src/led_ticker_hockey/emoji.py`, `plugins/hockey/tests/test_emoji.py`
- Modify: `plugins/hockey/src/led_ticker_hockey/{__init__.py,_paint.py,_scoreboard.py}`, `plugins/hockey/tests/{test_scoreboard.py,test_smoke.py}`, `plugins/hockey/{README.md,CLAUDE.md}`

**Interfaces:**
- Consumes: nothing from Task 1. Hockey is a separate package, so it mirrors Task 1's names: `_ICON`, `_ICON_GAP`, `sprite`.
- Produces: `led_ticker_hockey.emoji.PUCK: PixelData`; emoji `hockey.puck`; a new `HockeyBandBoard.shape_extents: list[tuple[str, int, int, int]]` (`attrs.field(init=False, factory=list)`, reset at the top of `draw()`, like football's), holding only `ICON` entries.

- [ ] **Step 1: Write the failing emoji tests.** Use Task 1's emoji test with `PUCK`. Add a test that every PUCK pixel has `max(r, g, b) >= 100` (no near-black puck), and assert `"hockey.puck" in emoji_slugs()` in the smoke test.
- [ ] **Step 2: Run** `uv run pytest plugins/hockey/tests/test_emoji.py plugins/hockey/tests/test_smoke.py -v`. Expect FAIL.
- [ ] **Step 3: Implement `emoji.py`** from the draft grid `"S.......", ".S......", "..S.....", "...S....", "....S...", "....SSS.", ".GGG.SSS", ".GGG...."`, with `S = (210, 160, 90)` and `G = (150, 150, 160)`. Register it with `api.emoji("puck", PUCK)`.
- [ ] **Step 4: Run Step 2's command.** Expect PASS.
- [ ] **Step 5: Write the failing board tests.** Write the same five tests as Task 1, Step 5, with `LIVE` / the intermission fixture / `FINAL_OT` and statuses `2ND` / `1ST INT` / `FINAL`. Extend hockey's `_spy_texts` to append `board.shape_extents` (football's helper does this) and give `_assert_band_clearance` the `ICON` exception. For the crowding test, use the existing `WORST_*` fixtures with `stale=True`, which puts `STALE` in the SOG-label column. Then assert that either no `ICON` is drawn or the icon clears everything by `_GAP`.
- [ ] **Step 6: Run** `uv run pytest plugins/hockey/tests/test_scoreboard.py -v`. Expect FAIL.
- [ ] **Step 7: Implement in `_scoreboard.py`.** Apply Task 1, Step 7's two placement rules. Hockey's future branch has no BYE and no venue ellipsis; leave those as they are. On live and final cards, `top_end` covers the abbreviation, the score, the `SOG`/`STALE` label, the SOG value, and `PP`/`EN` when they're on band 0. Update the module docstring.
- [ ] **Step 8: Run** `uv run pytest plugins/hockey -v`, then ruff check and format. Expect clean.
- [ ] **Step 9: Update `README.md` and `CLAUDE.md`.** Make the same additions as Task 1, Step 9, using `:hockey.puck:`.
- [ ] **Step 10: Commit** `git add plugins/hockey && git commit -m "feat(hockey): smallsign sport icon + :hockey.puck: emoji"`

---

### Task 3: Basketball — ball on the upcoming card when it fits

**Files:**
- Modify: `plugins/basketball/src/led_ticker_basketball/_paint.py` (add `sprite`)
- Modify: `plugins/basketball/src/led_ticker_basketball/_scoreboard.py` (`_draw_future` ~L183-227, plus the docstring)
- Modify: `plugins/basketball/tests/test_scoreboard.py`
- Modify: `plugins/basketball/{README.md,CLAUDE.md}` (Smallsign bullet)

**Interfaces:**
- Consumes: the existing `led_ticker_basketball.emoji.BALL`.
- Produces: `("ICON", x0, x0 + 7)` in `BasketballBandBoard.shape_extents`, with `_ICON` and `_ICON_GAP` in `_scoreboard.py`.

The rule is to pick exactly the `(day, tip, stale)` candidate the board picks today without the ball. Draw the ball only if that same candidate still fits once the names start at `left + _ICON + _ICON_GAP`. If it doesn't fit, the card is today's card, pixel for pixel. This reads the spec's "the full card it would show today" literally: the ball can never cost `STALE`, the weekday, AM/PM or the day label.

- [ ] **Step 1: Write the failing tests:**
  - `test_future_ball_when_it_fits`: use `NEXT` (`NY @ PHI`, a short date). `shape_extents` contains `("ICON", left, left + 7)`, where `left = max(sb.X_ABBREV, sb._CHIP + sb._GAP)`. The `NY` call starts at `left + 10`. The ball's pixels sit in rows 4–11. `_assert_clearance` (with the `ICON` exception) passes.
  - `test_future_ball_drops_on_tonight`: make a `NEXT` variant that renders `TONIGHT` with `PHI @ BOS`. Assert no `ICON`, and assert the text calls equal those of an unmodified board drawn from the same game. Compute the expected calls with the ball disabled by monkeypatching `sb._ICON` to a width that can never fit (for example 200).
  - `test_future_ball_never_costs_stale`: draw a stale short game (`start_utc=None`, which already fits `STALE`). Assert that `STALE` is drawn, and that the ball is drawn only if it fits as well. Then draw a stale `NEXT` whose `STALE` only just fits without the ball. Assert `STALE` is present and no `ICON` is drawn.
  - `test_future_ball_never_costs_day_label`: for `UTAH @ PHI 10:00 PM`, assert the chosen day and tip text match the no-ball board, and that no `ICON` is drawn.
  - Add the `ICON` exception to `_assert_clearance`. Extend `test_band_board_honours_cursor_pos` and `test_band_board_follows_y_offset` to check the ball.
  - Update the assertion in the existing `test_band_board_future_row` from `{(0, 2), (157, 159)}` to an assertion that accepts the extra `ICON` extent. That test uses `NEXT`, which fits.
- [ ] **Step 2: Run** `uv run pytest plugins/basketball/tests/test_scoreboard.py -v`. Expect FAIL.
- [ ] **Step 3: Implement in `_draw_future`.** Split the current candidate walk into a pure `_pick_future(candidates, lo, right, run_w) -> list[Part] | None`. Compute `pick` with `lo` from the names at `left`. If `pick` fits again with `lo` from the names at `left + _ICON + _ICON_GAP`, paint the sprite at `(ox + left, y_offset + 4)`, record it, and paint the names at the shifted x. Otherwise paint today's layout.
- [ ] **Step 4: Run** `uv run pytest plugins/basketball -v`, then ruff. Expect all PASS. The live, final, halftime and worst-case tests must pass without edits.
- [ ] **Step 5: Update the docs.** In the README Smallsign bullet, say the ball appears before the names on next-game cards when the line fits, and is the first thing dropped. Update `CLAUDE.md` to match.
- [ ] **Step 6: Commit** `git add plugins/basketball && git commit -m "feat(basketball): smallsign ball on next-game card when it fits"`

---

### Task 4: Sprite art sign-off (human gate)

**Files:**
- Modify (if the art changes): `plugins/football/src/led_ticker_football/emoji.py`, `plugins/hockey/src/led_ticker_hockey/emoji.py`

- [ ] **Step 1: Render the previews.** Render each plugin's `examples/config.<sport>-demo.smallsign.toml` with `uv run --project /Users/james/projects/github/jamesawesome/led-ticker-plugins-sport-icons python /Users/james/projects/github/jamesawesome/led-ticker/tools/render_demo/render.py <config> -o <scratchpad>/<sport>.gif --duration 40`. Pull one frame per card state, sampled by playback time rather than frame index, into PNGs. Also render each 8×8 sprite enlarged on its own.
- [ ] **Step 2: Show the PNGs to the user.** Iterate on the art in small visual steps (one change at a time, re-render, show) until they approve. Remember on-panel colour behaviour: black is invisible, white reads blue-white, dark colours read dim.
- [ ] **Step 3: Rerun the tests.** Run `uv run pytest plugins/football plugins/hockey` and expect PASS. The sprite tests check bounds and colour only, so an art swap should not break any layout test.
- [ ] **Step 4: Commit** `git commit -am "art(football, hockey): final smallsign icon sprites"` (only if the art changed).

---

### Task 5: Ship the plugins

- [ ] **Step 1: Run the full checks.** Run `uv run pytest plugins/football plugins/hockey plugins/basketball`, `uv run ruff check plugins`, and `uv run pyright plugins/football/src plugins/hockey/src plugins/basketball/src`. All must be clean.
- [ ] **Step 2: Validate the examples.** Run `led-ticker validate` on each plugin's smallsign examples; each must pass.
- [ ] **Step 3: Open the PR.** Push the branch and open a draft PR with the `open-pr` skill (one PR; the spec and plan ride along). `gh pr create` needs the user's approval, so write the body file first, then ask. Never merge without the user's explicit go-ahead for that PR.
- [ ] **Step 4: Release after the merge.** Release `football`, `hockey` and `basketball` with the `publishing-a-plugin` skill. The user clicks each PyPI publish approval.

---

### Task 6: Docs site (led-ticker repo, after the releases)

**Files** (in a new led-ticker worktree branched from `origin/main`):
- Modify: `docs/site/src/content/docs/widgets/football.mdx`, `docs/site/src/content/docs/widgets/hockey.mdx`. Add the icon to the smallsign layout prose, and add `:football.ball:` / `:hockey.puck:` wherever the page lists emoji.
- Regenerate: the smallsign demo GIFs those pages embed. Find them through the pages' `DemoGif` sources and their pinned demo TOMLs, and keep each snippet identical to the TOML it renders from. If the emoji catalogue page lists plugin emoji, add the two new slugs and run `make render-emoji-previews`.

- [ ] **Step 1: Edit the pages** following `docs/DOCS-STYLE.md`.
- [ ] **Step 2: Re-render the smallsign GIFs.** Use the `making-a-gif` skill to choose durations, and render against the released plugin versions.
- [ ] **Step 3: Run the checks.** Run `make test`, which includes the docs drift tripwires, and `make docs-build` (source nvm first if pnpm isn't on PATH). Both must be green.
- [ ] **Step 4: Open the PR.** Open a draft PR with the `open-pr` skill, after the user approves `gh pr create`.
