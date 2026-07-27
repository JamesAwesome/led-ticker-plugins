# Baseball hi-res fallback lines — design

**Status:** approved (brainstorm 2026-07-26)
**Ships as:** `led-ticker-baseball` v1.9.0 (minor)
**Repo:** led-ticker-plugins, `plugins/baseball`

## Problem

Every baseball widget draws a rich **hero card** at scale>1 (bigsign / longboi) when it has data, but forwards to a **BDF `SegmentMessage`/`TickerMessage`** line for its non-hero states — the scores series-title line, no-data / off-day / "next game" lines, etc. At scale>1 those BDF glyphs are block-scaled by `ScaledCanvas` into chunky "lores" text. The most visible offender is the **scores series-record line** ("Yankees @ Red Sox 1-0"), shown at the top of *every* scores rotation. This was reported as "seeing the mph in bdf" (the attendance weather line); v1.8.0 fixed attendance's own no-data fallback in isolation, but the pattern is plugin-wide.

## Goal

On a scale>1 sign, the **in-season, regularly-hit** non-hero states render **hi-res**, matching the hero cards. Smallsign (scale≤1) is unchanged (BDF). Rare states (exceptions, offseason) stay BDF. One shared, reusable mechanism — no per-widget duplication.

## Non-goals

- Error / exception lines stay BDF (bug states, seen rarely).
- Offseason "Opens `<date>`" lines stay BDF (out of season).
- All smallsign (scale≤1) rendering stays BDF (fits the 16px panel; matches the design convention).
- No new config knobs.
- No change to the hero-card layouts.

## Architecture

### `HiresLine` — a new shared story (`plugins/baseball/src/led_ticker_baseball/_hires_line.py`)

One frame-aware story class: "a text line that renders hi-res on a big sign and BDF on a small one." It is the single home for scale-dispatched line rendering with per-segment color.

**Fields**
- `segments: list[tuple[str, Color | ColorProvider]]` — the line content (text + color per run).
- `legacy: Any` — the BDF `SegmentMessage`/`TickerMessage` used at scale≤1 (built from the same segments).
- `bg_color: Color | None = None` (kw-only).
- `size: int = 20` — base hi-res size (fit-shrunk as needed).
- `center: bool = True`.

**`draw(canvas, cursor_pos=0, *, y_offset=0, font_color=None) -> (canvas, int)`**
- `scale = safe_scale(canvas)`.
- **scale≤1:** `return self.legacy.draw(canvas, cursor_pos, y_offset=y_offset, font_color=font_color)` — smallsign path unchanged.
- **scale>1:**
  1. Unwrap the real canvas (`unwrap_to_real`) / `phys_wrap`.
  2. Fit: measure the full line at `size` via `_paint.text_width`; while it exceeds `real.width − 2*margin`, drop `size` by 1 down to a floor (`_MIN_SIZE`, ~12); if still over at the floor, ellipsize the trailing segment(s) via `_paint.fit_text`.
  3. Center horizontally (when `center`) at the fitted width; vertically center on the 64px card (`cap_top`); add `y_offset * scale`.
  4. Draw each segment left-to-right with `_paint.hires(shim, text, x, y, color, size)`, advancing `x` by each segment's `text_width`. Resolve a `ColorProvider` segment via `color_for(frame, 0, 1)` (single color) using the story's frame counter; constant `Color` drawn directly.
  5. Return `(canvas, canvas.width)` — the logical wrapper width, so the engine takes the hold branch (same lesson as the hero cards).
- **Safety:** empty `segments` → forward to `self.legacy` (never blank / never crash).

**Frame hooks** — `advance_frame` / `pause_frame` / `resume_frame` / `reset_frame` call `super()` then forward to `self.legacy`, so scale≤1 frame-aware colors keep working (mirrors the hero cards' `legacy` forwarding).

**Construction pattern (used by every caller):** build the `segments` list once, then
`HiresLine(segments=segs, legacy=SegmentMessage(segs, ...), ...)`.
`SegmentMessage` does not expose its segments, so the segments are built at the source and shared — wording/colors cannot drift between the hi-res and BDF representations.

### Widget changes (visible-only scope)

Each widget replaces its **in-season non-hero** `feed_stories = [SegmentMessage(...)/TickerMessage(...)]` assignments with a `HiresLine`. Concretely:

| Widget | Convert to `HiresLine` | Leave BDF |
|---|---|---|
| **scores** (`scores.py`) | the series-title line (`_build_series_title` / `_build_two_row_series_title`); the in-season no-games-today / off-day line | error state; offseason "Opens" |
| **statcast** (`statcast.py`) | the no-Statcast-data line (`_set_no_games_state`) | error state |
| **promotions** (`promotions.py`) | `_story_line` output for "No Data" / off-day / "Next home game" | error state; offseason |
| **attendance** (`attendance.py`, `_attendance_card.py`) | migrate the v1.8.0 `_draw_fallback_line` to delegate to `HiresLine` (remove the duplicated renderer); **restore the weather** (temp/wind) segment in the fallback | error state |
| **standings** (`standings.py`) | none (board always has in-season data) | error state; offseason |

"Convert" means: build the segments, then set `feed_stories = [HiresLine(segments, legacy=<the existing BDF line>)]`. The series-title builders return `HiresLine` in place of the bare `SegmentMessage`.

### Attendance weather restoration

`_build_team_fallback_text` currently omits weather (v1.8.0, "keep it short"). Replace it with a segment builder that includes the temp/wind segment (reuse `_format_weather` + the team-line segment colors), producing e.g. `PHI · Ballpark · 72°, wind 5 mph`. `HiresLine`'s fit-shrink + ellipsize guarantees a long weather string can't overflow, so length is no longer a reason to drop it.

## Data flow

`update()` (per widget) → on a non-hero state, build `segments` (text + colors) → `HiresLine(segments, legacy=SegmentMessage(segments))` → `feed_stories = [that]`. Engine draws it per pass; `HiresLine.draw` dispatches on scale. No fetch/poll changes; no `feed_title` change.

## Error handling

- `HiresLine` never raises (the baseball render-loop-breaker contract): empty segments → legacy; the fit loop is bounded; painting goes through `_paint.px` (bounds-checked). A genuine bug still surfaces in tests rather than being swallowed.
- Widget error states (exceptions) deliberately keep their existing BDF line — an error is not a "normal" state and its rarity doesn't justify the hi-res surface.

## Testing

**`HiresLine` unit (`tests/test_hires_line.py`):**
- scale≤1 → forwards to `legacy`, byte-identical `_pixels`.
- scale>1 → hi-res: **bounded** vertical span (`_MIN..~30`, excluding the ~35px block-scaled-BDF regression) **and** a not-equal-to-legacy pixel guard (mutation-proof — the pattern from the v1.8.0 fix).
- per-segment colors present at scale>1 (assert a segment's color pixels exist).
- long line fits on-canvas at **512 and 256** (no pixels past the edges; ellipsized).
- empty segments → forwards to legacy (safety).
- frame hooks forward to `legacy` (advance/pause/resume/reset).

**Per-widget:**
- each converted state renders hi-res at scale>1 (span + ≠-BDF pixel guard).
- **tripwire against over-conversion:** the left-alone states (error; offseason where applicable) still render BDF at scale>1 (span ~35 / equals the legacy render).
- attendance fallback now includes the weather text and renders hi-res; fit-to-width holds on a long venue+weather string.

**Regression:** hero-card layouts unchanged (existing layout tests stay green); smallsign (scale≤1) output for every converted state is byte-identical to before (forwarded to `legacy`).

**Mutation proof (required in the implementation report):** temporarily make `HiresLine.draw`'s scale>1 branch forward to `legacy`; the hi-res per-widget + unit tests must fail; revert and confirm green.

## Rollout

- Full gate: `uv run pytest tests/` (green), ruff check+format, pyright 0.
- Adversarial whole-branch review before merge (empty-feed safety, fit/overflow at 512 & 256, over-conversion tripwires, no smallsign change, no hero-card change).
- Ship `baseball-v1.9.0`; on-sign check (render-path change) at deploy; bump sign pins to `==1.9.0`.
