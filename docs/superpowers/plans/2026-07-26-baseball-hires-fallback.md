# Baseball hi-res fallback lines — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make baseball widgets' in-season non-hero states (scores series-title, no-data / off-day / next-game lines) render hi-res at scale>1 instead of block-scaled BDF, via one shared `HiresLine` story; smallsign stays BDF.

**Architecture:** A new frame-aware `HiresLine` story forwards to a BDF `SegmentMessage`/`TickerMessage` at scale≤1 and draws the same content as a centered, fit-to-width hi-res Inter line (per-segment color) at scale>1. Each widget builds its segments once and wraps them: `HiresLine(segments, legacy=SegmentMessage(segments))`. `HiresLine` generalizes the single-color `_attendance_card._draw_fallback_line` shipped in v1.8.0.

**Tech Stack:** Python 3.14, attrs, `led_ticker.plugin` public surface, the plugin's `_paint` hi-res helpers, pytest, HeadlessBackend/ScaledCanvas render tests.

## Global Constraints

- Ships as `led-ticker-baseball` **v1.9.0** (minor).
- Scale≤1 (smallsign) output for every converted state MUST be byte-identical to before (forward to `legacy`).
- Convert only **in-season, regularly-hit** states. **Error/exception lines and offseason "Opens `<date>`" lines stay BDF.** Standings needs no conversion.
- No new config knobs. No change to hero-card layouts.
- Public imports from `led_ticker.plugin` only; NO `from __future__ import annotations`.
- `HiresLine` must never raise (render-loop-breaker contract): empty segments → forward to `legacy`; painting via bounds-checked `_paint.px`/`hires`.
- Each `HiresLine` is built from the SAME `segments` list used to build its `legacy` line — wording/colors cannot drift.
- The repo pre-commit hook pins a ruff too old for `target-version = py314`; if `git commit` is blocked, commit `--no-verify` (the real `uv run ruff`/`pytest` gates are authoritative).
- Commit trailer on every commit:
  ```
  Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_012wDgWWQSAr2ZyFnoxefYy4
  ```

## File Structure

- **Create** `plugins/baseball/src/led_ticker_baseball/_hires_line.py` — the `HiresLine` story (the only new file).
- **Create** `plugins/baseball/tests/test_hires_line.py` — `HiresLine` unit tests.
- **Modify** `scores.py`, `statcast.py`, `promotions.py`, `attendance.py`, `_attendance_card.py` — swap in-season non-hero `feed_stories` lines for `HiresLine`; migrate attendance's `_draw_fallback_line`.
- **Modify** the widgets' test files — add "converted state is hi-res" + "left-alone state still BDF" assertions.

All paths below are relative to `plugins/baseball/`. Run everything from `plugins/baseball/` via `uv run …`.

---

### Task 1: `HiresLine` shared story

**Files:**
- Create: `src/led_ticker_baseball/_hires_line.py`
- Test: `tests/test_hires_line.py`

**Interfaces:**
- Consumes: `_paint.{phys_wrap, hires, text_width, fit_text, cap_top, js_round}` (signatures: `hires(shim, text, x, y_top, color, size, *, bold=True) -> int` returns advance width; `text_width(size, text, *, bold=True) -> int`; `fit_text(text, max_w, size, *, bold=True) -> str`; `cap_top(y_target, size) -> int`; `phys_wrap(canvas) -> (shim, real)`); `led_ticker.plugin.{Color, ColorProvider, DrawResult, FrameAwareBase, safe_scale}`.
- Produces: `HiresLine(segments: list[tuple[str, Color | ColorProvider]], legacy, *, size: int = 20, center: bool = True)` — a frame-aware story with `.draw(canvas, cursor_pos=0, *, y_offset=0, font_color=None) -> (canvas, int)`. Widgets construct it in Tasks 2–5.

- [ ] **Step 1: Write the failing unit tests**

Create `tests/test_hires_line.py`. Use the plugin's existing render-test helpers (mirror `tests/test_layout_attend_long.py`: `HeadlessBackend(w, h).create_canvas()`, `ScaledCanvas(real, scale=…, content_height=16)`, `real._pixels`, `real.get_pixel`). Import `HiresLine` and a real BDF line to use as `legacy`.

```python
from led_ticker.plugin import HeadlessBackend, ScaledCanvas, SegmentMessage, make_color
from led_ticker_baseball._hires_line import HiresLine
from led_ticker_baseball import _palette as pal

WHITE = (255, 255, 255)

def _segs(text="NYY · Yankee Stadium"):
    return [(text, pal.IDENT)]

def _line(segments=None, **kw):
    segs = segments if segments is not None else _segs()
    return HiresLine(segments=segs, legacy=SegmentMessage(segs), **kw)

def _render(story, scale, w=512):
    real = HeadlessBackend(w, 64).create_canvas()
    story.draw(ScaledCanvas(real, scale=scale, content_height=16), 0)
    return real

def _span(real):
    ys = [y for (x, y), c in real._pixels.items() if c != (0, 0, 0)]
    return (max(ys) - min(ys) + 1) if ys else 0

def test_scale1_forwards_to_legacy_byte_identical():
    story = _line()
    hires = _render(story, 1)
    ref = HeadlessBackend(512, 64).create_canvas()
    story.legacy.draw(ScaledCanvas(ref, scale=1, content_height=16), 0)
    assert hires._pixels == ref._pixels

def test_scale_gt1_is_hires_not_bdf():
    story = _line()
    real = _render(story, 4)
    # hi-res span sits ~18-24; a BDF line block-scaled through scale=4 spans ~35.
    assert 12 <= _span(real) <= 30
    # mutation-proof: differs from what forwarding to the BDF legacy would draw.
    bdf = HeadlessBackend(512, 64).create_canvas()
    story.legacy.draw(ScaledCanvas(bdf, scale=4, content_height=16), 0)
    assert real._pixels != bdf._pixels

def test_scale_gt1_preserves_segment_color():
    teal = make_color(0, 200, 180)
    story = _line(segments=[("NYY ", teal), ("· Yankee Stadium", pal.IDENT)])
    real = _render(story, 4)
    assert any(c == (0, 200, 180) for c in real._pixels.values())

def test_long_line_fits_on_canvas_512_and_256():
    long = [("PHI · " + "Very Long Ballpark Name " * 6 + "· 72°, wind 5 mph", pal.IDENT)]
    for w in (512, 256):
        real = _render(_line(segments=long), 4, w=w)
        xs = [x for (x, y) in real._pixels]
        assert xs and min(xs) >= 0 and max(xs) < w  # no overflow/clip past edges

def test_empty_segments_forwards_to_legacy():
    story = HiresLine(segments=[], legacy=SegmentMessage(_segs()))
    real = _render(story, 4)
    ref = HeadlessBackend(512, 64).create_canvas()
    story.legacy.draw(ScaledCanvas(ref, scale=4, content_height=16), 0)
    assert real._pixels == ref._pixels

def test_frame_hooks_forward_to_legacy():
    calls = []
    class Spy(SegmentMessage):
        def advance_frame(self, *, visit_id=None): calls.append("advance")
        def reset_frame(self): calls.append("reset")
        def pause_frame(self): calls.append("pause")
        def resume_frame(self): calls.append("resume")
    story = HiresLine(segments=_segs(), legacy=Spy(_segs()))
    story.advance_frame(); story.pause_frame(); story.resume_frame(); story.reset_frame()
    assert set(calls) == {"advance", "pause", "resume", "reset"}
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_hires_line.py -q`
Expected: FAIL — `ModuleNotFoundError: led_ticker_baseball._hires_line`.

- [ ] **Step 3: Implement `HiresLine`**

Create `src/led_ticker_baseball/_hires_line.py`:

```python
"""HiresLine — a status line that renders hi-res at scale>1 and BDF at
scale<=1.

The single home for baseball's scale-dispatched non-hero lines (scores
series-title, no-data / off-day / next-game). Below the hero-card threshold
every widget forwarded these to a BDF SegmentMessage/TickerMessage, which
ScaledCanvas block-scales into chunky lores on a bigsign/longboi. This draws
the same content in hi-res Inter at scale>1 (centered, fit-to-width,
per-segment color) and forwards verbatim to the BDF `legacy` line at
scale<=1 (smallsign unchanged). Generalizes the single-color
`_attendance_card._draw_fallback_line` (v1.8.0) to multi-segment.
"""

from typing import Any

import attrs
from led_ticker.plugin import (
    Color,
    ColorProvider,
    DrawResult,
    FrameAwareBase,
    safe_scale,
)

from led_ticker_baseball._paint import (
    cap_top,
    fit_text,
    hires,
    js_round,
    phys_wrap,
    text_width,
)

_MIN_SIZE = 12
_MARGIN = 8  # physical px kept clear on each side


@attrs.define
class HiresLine(FrameAwareBase):
    segments: list[tuple[str, Any]]  # (text, Color | ColorProvider)
    legacy: Any
    size: int = attrs.field(default=20, kw_only=True)
    center: bool = attrs.field(default=True, kw_only=True)

    def draw(
        self,
        canvas: Any,
        cursor_pos: int = 0,
        *,
        y_offset: int = 0,
        font_color: Any = None,
    ) -> DrawResult:
        # Empty content or smallsign -> the BDF legacy path (unchanged).
        if not self.segments or safe_scale(canvas) <= 1:
            return self.legacy.draw(
                canvas, cursor_pos, y_offset=y_offset, font_color=font_color
            )
        scale = safe_scale(canvas)
        shim, real = phys_wrap(canvas)
        yo = y_offset * scale
        max_w = real.width - 2 * _MARGIN

        # Fit: shrink the size until the whole line fits; floor at _MIN_SIZE.
        size = self.size
        texts = [t for t, _ in self.segments]
        while size > _MIN_SIZE and sum(text_width(size, t) for t in texts) > max_w:
            size -= 1

        # If still over at the floor, ellipsize the trailing segment on its
        # own remaining width budget (fit_text appends the ellipsis).
        drawn = list(self.segments)
        if sum(text_width(size, t) for t, _ in drawn) > max_w:
            head_w = sum(text_width(size, t) for t, _ in drawn[:-1])
            last_text, last_color = drawn[-1]
            drawn[-1] = (fit_text(last_text, max(0, max_w - head_w), size), last_color)

        total = sum(text_width(size, t) for t, _ in drawn)
        x = js_round((real.width - total) / 2) if self.center else _MARGIN
        # Center by the glyphs' visible cap-height, matching the attend_* `_t`
        # convention (js_round(size * 0.72) approximates the cap box).
        glyph_h = js_round(size * 0.72)
        y = cap_top(js_round((real.height - glyph_h) / 2) + yo, size)

        for text, color in drawn:
            c = (
                color.color_for(self._frame_count, 0, 1)
                if isinstance(color, ColorProvider)
                else color
            )
            x += hires(shim, text, x, y, c, size)
        # Logical wrapper width -> engine takes the HOLD branch (same lesson
        # as the hero cards).
        return canvas, canvas.width

    def advance_frame(self, *, visit_id: int | None = None) -> None:
        super().advance_frame(visit_id=visit_id)
        self.legacy.advance_frame(visit_id=visit_id)

    def pause_frame(self) -> None:
        super().pause_frame()
        self.legacy.pause_frame()

    def resume_frame(self) -> None:
        super().resume_frame()
        self.legacy.resume_frame()

    def reset_frame(self) -> None:
        super().reset_frame()
        self.legacy.reset_frame()
```

NOTE for the implementer: confirm `FrameAwareBase` exposes `self._frame_count` (the hero cards read it); if the attribute name differs, use the same accessor the sibling cards use for `ColorProvider` resolution. Confirm `DrawResult` is exported from `led_ticker.plugin` (the cards import it); if not, annotate the return as `tuple[Any, int]`.

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/test_hires_line.py -q`
Expected: PASS (6 tests).

- [ ] **Step 5: Gate + commit**

Run: `uv run ruff check src/ tests/ && uv run ruff format src/ tests/ && uv run pyright src/`
Then:
```bash
git add src/led_ticker_baseball/_hires_line.py tests/test_hires_line.py
git commit -m "feat(baseball): HiresLine — scale-dispatched hi-res status line"
```

---

### Task 2: scores — series-title + no-games line → `HiresLine`

**Files:**
- Modify: `src/led_ticker_baseball/scores.py` (`_build_series_title`, `_build_two_row_series_title`, and the in-season no-games-today / off-day `feed_stories` assignment)
- Test: `tests/test_scores.py`

**Interfaces:**
- Consumes: `HiresLine(segments, legacy, *, size=20, center=True)` from Task 1.
- Produces: nothing new (internal wiring).

- [ ] **Step 1: Write failing tests** in `tests/test_scores.py`:
  - `test_series_title_is_hires_at_scale_gt1`: build the demo/live series-title story and render it at scale=4 on 512×64; assert `12 <= span <= 30` AND `_pixels` differs from rendering its `legacy` at scale=4 (mutation-proof, same pattern as Task 1). Reuse the file's existing render helper if present.
  - `test_no_games_today_line_is_hires`: drive the in-season no-games path (reuse this file's existing mocking for `update()` / the no-games builder) and assert the resulting `feed_stories[0]` renders hi-res at scale=4 (span bound + ≠-legacy).
  - `test_error_state_stays_bdf` (over-conversion tripwire): drive the error state; assert its `feed_stories[0]` at scale=4 renders BDF (span ~35 / equals its own legacy render — i.e. NOT converted).

- [ ] **Step 2: Run** `uv run pytest tests/test_scores.py -q` → the two hi-res tests FAIL (still BDF), the error tripwire PASSES.

- [ ] **Step 3: Implement.** In `_build_series_title` / `_build_two_row_series_title`, build the `segments: list[(text, Color)]` list as today, then return `HiresLine(segments, legacy=SegmentMessage(segments, ...))` instead of the bare `SegmentMessage`. For the in-season no-games / off-day `feed_stories` assignment, build its segments and wrap in `HiresLine` the same way. **Do NOT touch** the error-state assignment or any offseason "Opens" line — leave them bare BDF. Import `HiresLine` from `led_ticker_baseball._hires_line`.

- [ ] **Step 4: Run** `uv run pytest tests/test_scores.py -q` → all pass (both hi-res tests pass, error tripwire still passes).

- [ ] **Step 5: Gate + commit** (`ruff check/format`, `pyright src/`):
```bash
git add src/led_ticker_baseball/scores.py tests/test_scores.py
git commit -m "feat(baseball): scores series-title + no-games line render hi-res at scale>1"
```

---

### Task 3: statcast — no-Statcast-data line → `HiresLine`

**Files:**
- Modify: `src/led_ticker_baseball/statcast.py` (`_set_no_games_state`)
- Test: `tests/test_statcast.py`

**Interfaces:** Consumes `HiresLine` (Task 1).

- [ ] **Step 1: Write failing tests** in `tests/test_statcast.py`:
  - `test_no_data_line_is_hires`: drive `_set_no_games_state` (reuse existing mocking) and assert `feed_stories[0]` renders hi-res at scale=4 (span bound + ≠-legacy).
  - `test_error_state_stays_bdf`: drive the error state; assert it still renders BDF at scale=4.

- [ ] **Step 2: Run** → hi-res test FAILS, error tripwire PASSES.

- [ ] **Step 3: Implement.** In `_set_no_games_state`, build the line's segments (text + color) and set `feed_stories = [HiresLine(segments, legacy=<the existing BDF SegmentMessage/TickerMessage>)]`. Leave the error state bare BDF.

- [ ] **Step 4: Run** → all pass.

- [ ] **Step 5: Gate + commit:**
```bash
git add src/led_ticker_baseball/statcast.py tests/test_statcast.py
git commit -m "feat(baseball): statcast no-data line renders hi-res at scale>1"
```

---

### Task 4: promotions — "No Data" / off-day / next-game lines → `HiresLine`

**Files:**
- Modify: `src/led_ticker_baseball/promotions.py` (`_story_line` and/or its in-season non-hero call sites)
- Test: `tests/test_promotions.py`

**Interfaces:** Consumes `HiresLine` (Task 1).

- [ ] **Step 1: Write failing tests** in `tests/test_promotions.py`:
  - `test_no_data_line_is_hires` and `test_off_day_next_game_line_is_hires`: drive those in-season states; assert `feed_stories[0]` renders hi-res at scale=4 (span bound + ≠-legacy).
  - `test_error_state_stays_bdf` and (if a distinct offseason "Opens" path exists) `test_offseason_stays_bdf`: assert they still render BDF at scale=4.

- [ ] **Step 2: Run** → hi-res tests FAIL, tripwires PASS.

- [ ] **Step 3: Implement.** Make the in-season non-hero outputs of `_story_line` (No Data / off-day / next-game) build segments and wrap in `HiresLine(segments, legacy=<existing BDF line>)`. Leave the error and offseason "Opens" outputs bare BDF (branch on the caller/state, not blanket-convert `_story_line`).

- [ ] **Step 4: Run** → all pass.

- [ ] **Step 5: Gate + commit:**
```bash
git add src/led_ticker_baseball/promotions.py tests/test_promotions.py
git commit -m "feat(baseball): promotions no-data/off-day lines render hi-res at scale>1"
```

---

### Task 5: attendance — migrate `_draw_fallback_line` to `HiresLine` + restore weather

**Files:**
- Modify: `src/led_ticker_baseball/_attendance_card.py` (remove `_draw_fallback_line`; the card's no-attendance scale>1 branch delegates to `HiresLine`), `src/led_ticker_baseball/attendance.py` (`_build_team_fallback_text` → segment builder incl. weather)
- Test: `tests/test_attendance.py`, `tests/test_attendance_card_dispatch.py`

**Interfaces:** Consumes `HiresLine` (Task 1). NOTE: this removes the duplicated single-color renderer added in v1.8.0.

- [ ] **Step 1: Write failing tests:**
  - `test_team_fallback_includes_weather_hires`: att is None + weather present → the fallback story renders hi-res at scale=4 AND a weather token ("mph" or the "°" temp) is part of its segments/text; span bound + ≠-legacy.
  - Keep/adapt the existing v1.8.0 attendance hi-res + hide tests (they must stay green; the hi-res mechanism is now `HiresLine` but behavior is unchanged).
  - `test_attendance_error_state_stays_bdf`: the error state still renders BDF at scale=4.

- [ ] **Step 2: Run** → the weather test FAILS (weather currently omitted), others as-is.

- [ ] **Step 3: Implement.**
  - Replace `_build_team_fallback_text` with a segment builder (e.g. `_build_team_fallback_segments`) that includes the temp/wind weather segment (reuse `_format_weather` + the team-line segment colors), returning `list[(text, Color)]`.
  - In `_build_team_card_from_avg` / the off-day path, construct the fallback as `HiresLine(segments, legacy=SegmentMessage(segments))` and store it where the card's no-attendance branch can draw it — OR keep `MLBAttendanceCard` and have its `not _has_attendance` scale>1 branch delegate to a `HiresLine` built from the card's `fallback_segments`. Pick whichever keeps the existing `no_data="hide"`/scale≤1 behavior intact.
  - Delete `_attendance_card._draw_fallback_line` and its `fallback_text`/`fallback_color` single-color fields in favor of segment-based `HiresLine` delegation. Keep the scale≤1 legacy forward and the empty-safety.

- [ ] **Step 4: Run** `uv run pytest tests/test_attendance.py tests/test_attendance_card_dispatch.py -q` → all pass.

- [ ] **Step 5: Gate + commit:**
```bash
git add src/led_ticker_baseball/attendance.py src/led_ticker_baseball/_attendance_card.py tests/test_attendance.py tests/test_attendance_card_dispatch.py
git commit -m "feat(baseball): attendance fallback via HiresLine + weather restored"
```

---

### Task 6: Full gate + spec's mutation proof

**Files:** none (verification).

- [ ] **Step 1:** `uv run pytest tests/ -q` → full suite green.
- [ ] **Step 2:** `uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run pyright src/` → clean, 0 errors.
- [ ] **Step 3 (mutation proof, required by the spec):** temporarily edit `HiresLine.draw` so its scale>1 branch forwards to `self.legacy`; run `uv run pytest tests/test_hires_line.py tests/test_scores.py tests/test_statcast.py tests/test_promotions.py tests/test_attendance.py -q` and confirm the hi-res assertions FAIL; revert and confirm green. Record both outputs in the task report.
- [ ] **Step 4:** No commit (verification only), OR commit any lint fixups.

---

## Self-Review

**1. Spec coverage:**
- `HiresLine` story (spec §Architecture) → Task 1. ✅
- Widget conversions, visible-only (spec §Widget changes) → Tasks 2 (scores), 3 (statcast), 4 (promotions), 5 (attendance); standings = none (spec says no change). ✅
- Attendance weather restoration (spec §3) → Task 5. ✅
- Testing incl. mutation proof + over-conversion tripwires (spec §Testing) → per-task tests + Task 6. ✅
- Non-goals (error/offseason/smallsign stay BDF) → enforced by the "stays BDF" tripwires in Tasks 2–5 and the scale≤1 byte-identical test in Task 1. ✅

**2. Placeholder scan:** Task 1 carries complete code. Tasks 2–5 intentionally instruct "build the segments as today, then wrap in `HiresLine`" rather than transcribing each widget's current segment code — the segments already exist in each method; the implementer reads them and wraps. Test intents are concrete (span bound + ≠-legacy pixel guard + over-conversion tripwire). No TBD/TODO.

**3. Type consistency:** `HiresLine(segments: list[tuple[str, Color|ColorProvider]], legacy, *, size=20, center=True)` and its `.draw(...) -> (canvas, canvas.width)` are used identically in Tasks 2–5. `_paint` helper signatures match Task 1's usage.
