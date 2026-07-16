# Plugins: layout collision-guard sweep — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Roll the measured-clearance pattern (proven in stocks #54, promoted to core as `hires_text_width` + `fit_text_size`) across the plugin fleet in one pass: fix flight's live collision surfaces, migrate stocks onto the core API, audit baseball, document the rest as checked, and encode the convention so it can't regress.

**Architecture:** Survey first (headless pixel render with worst-case data — fix measured collisions, not imagined ones), then per-surface shrink-to-fit ladders calling core `fit_text_size`. **Ladder values stay per-plugin.** Convention lands in the monorepo CLAUDE.md.

**Tech Stack:** led-ticker-plugins monorepo (uv workspace), branch `flight-layout-guards`. **GATE: Tasks 2–3 require the core release carrying `hires_text_width`/`fit_text_size` (Plan `2026-07-16-hires-text-fit-api.md` in the core repo) — do not start them before it's on PyPI.** Tasks 1, 4, 5, 6 have no core dependency.

## Global Constraints

- Plugins import core symbols ONLY via `led_ticker.plugin`. No `from __future__ import annotations`.
- **Never ship <6px measured clearance** between adjacent positioned text blocks (the near-miss rule: a 3px macOS clearance was an overlap on the Pi's freetype — stocks #54).
- Pixel-separation tests are invariant-based — never exact-pin hires sizes/widths (freetype macOS≠Linux).
- Equity/short-data cases must keep their design sizes — zero visual change unless a collision is real.
- CI gate per plugin before commit: `uv run --extra dev pytest tests/ -q` + `uvx ruff@0.15.18 check` + `format --check` + `uv run --with pyright==1.1.410 pyright src/`.
- Every PR body gets the **"Test on the sign"** section (branch-ref requirements line + `down -v` note).
- Commit trailers, exactly:
  Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_015czjSP4i45aZxX717Zh9yS

## File Structure

- `plugins/flight/src/led_ticker_flight/{dashboard_layout,hero_layout,ticker_layout}.py` — **modify** per survey findings; `paint.py` may gain a thin fit wrapper.
- `plugins/flight/pyproject.toml` — **modify**: core floor → the API release (`led-ticker-core>=<vNext>`).
- `plugins/flight/tests/` — new survey-derived pixel-separation tests.
- `plugins/stocks/src/led_ticker_stocks/_paint.py` — **modify**: `text_width` delegates to core `hires_text_width`.
- `plugins/stocks/pyproject.toml` — **modify**: core floor → `<vNext>`.
- `plugins/baseball/` — audit; guard or a "checked, safe" comment.
- `CLAUDE.md` (monorepo root) — **modify**: the convention invariant.

---

## Task 1: flight collision survey (no core dependency — start immediately)

Render all three flight layouts headless with worst-case data and record every adjacent-block gap. Findings (surface → gap px) drive Task 2; a surface with ≥6px clearance under worst-case data gets NO change.

- [ ] **Step 1: Write the survey harness** at `plugins/flight/tests/survey_layout_gaps.py` (a script, not a test — committed for rerunnability):

```python
"""Survey: render flight layouts with worst-case data; print block gaps.

Run: uv run python tests/survey_layout_gaps.py   (from plugins/flight)
A gap < 6px (or a merged block where two fields should be distinct) is a
collision surface for the fit-ladder treatment.
"""

from led_ticker.plugin import HeadlessBackend, ScaledCanvas

from led_ticker_flight.dashboard_layout import render_dashboard
from led_ticker_flight.data import Aircraft
from led_ticker_flight.hero_layout import render_hero
from led_ticker_flight.ticker_layout import render_ticker

# Worst-case: 7-char ICAO callsign, longest airline name (SOUTHWEST),
# widest actype, 5-digit altitude, 3-digit speed/track, long distance.
WORST = [
    Aircraft("SWA1234", "B77W", 41000, 1200, 510, 305, "222KM NE", 222.0, "N7088A"),
    Aircraft("BAW123A", "A388", 39000, -900, 480, 90, "31KM NW", 31.0, "G-STBA"),
]


def blocks(real, y0, y1, x0=0, x1=None, gap=3):
    x1 = x1 or real.width
    cols = sorted(
        {x for y in range(y0, y1) for x in range(x0, x1)
         if real.get_pixel(x, y) != (0, 0, 0)}
    )
    if not cols:
        return []
    out, start, prev = [], cols[0], cols[0]
    for c in cols[1:]:
        if c - prev > gap:
            out.append((start, prev))
            start = c
        prev = c
    out.append((start, prev))
    return out


def survey(name, w, h, render, bands):
    real = HeadlessBackend(w, h).create_canvas()
    canvas = ScaledCanvas(real, scale=4, content_height=16)
    render(canvas, WORST, 0.0)
    print(f"== {name} ({w}x{h}) ==")
    for label, y0, y1 in bands:
        bl = blocks(real, y0, y1)
        gaps = [b[0] - a[1] for a, b in zip(bl, bl[1:], strict=False)]
        flag = " <-- CHECK" if any(g < 6 for g in gaps) else ""
        print(f"  {label}: blocks {bl} gaps {gaps}{flag}")


survey("dashboard", 512, 64, render_dashboard, [
    ("ident+cols top", 0, 24), ("name/type + values", 24, 44), ("full", 0, 56),
])
survey("hero", 256, 64, render_hero, [("top", 0, 32), ("bottom", 32, 56)])
# ticker is a scrolling layout — different mechanism; render once to confirm
# nothing is positioned/right-aligned, then note it.
```

(Adjust `render_*` call signatures to the real ones — read each layout's entry function first; hero/ticker may take `clock_ms`/kwargs like `render_dashboard(canvas, flights, clock_ms, *, y_offset=0)`.)

- [ ] **Step 2: Run it; record findings** in the task report as a table: surface → worst-case gap → verdict (guard / safe). Known suspects from code reading: (a) dashboard `airline name + actype` row vs the metric columns' values (the name row y≈40–52 vs column values y≈24–40 overlap vertically; columns start at `x = max(hx+iw+30, 190)` but the name row has NO budget check); (b) dashboard column VALUES at size 16 vs computed `col_w` when a long ident pushes `x` right and shrinks `col_w`; (c) `paint.py`'s own admitted latent label-clip fallback; (d) hero layout unknown — survey decides.
- [ ] **Step 3: Commit** the harness + findings note — `test(flight): layout-gap survey harness + worst-case findings`.

## Task 2: flight guards (GATED on the core release)

- [ ] **Step 1:** Bump `plugins/flight/pyproject.toml` core floor to the API release. `uv sync`.
- [ ] **Step 2 (TDD per surface found in Task 1):** for each colliding surface, write the failing pixel-separation test first (worst-case fixture from the survey; assert adjacent blocks separated, invariant-style), then guard it: import `fit_text_size` (and `hires_text_width` where an end-x is needed) from `led_ticker.plugin`; define an in-plugin ladder near the layout (e.g. `_IDENT_SIZES = (26, 22, 20, 18)` — pick per surface, floor = smallest readable); budget = measured space to the neighboring block, minus a 6px gap. Where a column's budget is dynamic (`col_w`), fit each value against its actual column width.
- [ ] **Step 3:** Re-run the Task 1 survey — every flagged gap now ≥6px; short-data cases keep design sizes (assert in tests).
- [ ] **Step 4:** Full CI gate; commit — `fix(flight): measured collision guards on positioned layouts (core fit_text_size)`.

## Task 3: stocks migration (GATED on the core release)

- [ ] **Step 1:** `plugins/stocks/pyproject.toml` core floor → `<vNext>`.
- [ ] **Step 2:** `_paint.text_width` body delegates: `return hires_text_width(text, size, font="Inter-Bold" if bold else "Inter-Regular", threshold=_HIRES_THRESHOLD)` (import via `led_ticker.plugin`). Call sites and ladders unchanged. `_subst` stays (draw-side; harmless duplication of core's fallback).
- [ ] **Step 3:** Full stocks suite (222+) + CI gate — behavior-identical (the existing fit tests are the proof). Commit — `refactor(stocks): text_width delegates to core hires_text_width`.

## Task 4: baseball center-zone audit (no core dependency)

- [ ] **Step 1:** Read baseball's positioned-drawing surfaces (scoreboard center zone). ONE question: does any positioned text take variable-length data that can collide with a neighbor? Fixed-vocabulary text (team abbreviations, inning numerals, "TOP/BOT") cannot.
- [ ] **Step 2:** If yes → survey + guard + test (Task 2 pattern, gated on the release). If no → add a one-line comment at the drawing site: `# Layout-collision audit 2026-07-16: all positioned text here is fixed-vocabulary (team abbrevs/inning digits) — no variable-length collision surface.` Commit either way.

## Task 5: fleet audit note (no core dependency)

- [ ] **Step 1:** Confirm by inspection and record IN THE SWEEP PR BODY: crypto (scrolling crawl — overflow handled by motion), pool/weather/calendar/rss/storefront (ride core message/two_row — core owns overflow→scroll), flair (non-text effects). **No retrofit** — that's the point; the note prevents a future "did anyone check these?" re-audit.

## Task 6: the convention (no core dependency)

- [ ] **Step 1:** Add to the monorepo root `CLAUDE.md` (contributor invariants), verbatim:

> **Positioned hi-res text must be collision-guarded.** Any plugin that paints hi-res text at a fixed or computed position (not scrolling) with variable-length data must: (a) measure with core's `hires_text_width` (via `led_ticker.plugin`) — the same glyph resolution the renderer draws with; (b) shrink-to-fit via `fit_text_size` with a plugin-owned size ladder when the text would collide with a neighbor; (c) ship a pixel-separation regression test (invariant-based — never exact-pin sizes/widths; freetype metrics differ macOS vs Linux); (d) never ship <6px measured clearance — a near-miss on dev metrics is an overlap on the panel (stocks #54, flight). Ladder values are per-layout design decisions — keep them in the plugin, not core.

- [ ] **Step 2:** Mirror a one-line pointer in `plugins/stocks/CLAUDE.md` + `plugins/flight/CLAUDE.md` (if present) near their layout notes. Commit — `docs: layout collision-guard invariant (measured clearance, fit ladders, pixel tests)`.

---

## Post-implementation

- One sweep PR (or two: flight+convention / stocks+baseball — implementer's call by diff size), each with the Test-on-the-sign section. Hardware check on the longboi: dashboard with `SWA1234` + SOUTHWEST worst-case (demo feed can carry it).
- Releases after merge: `flight-v0.2.0` (new floor + fixes), `stocks-v0.6.2` (floor bump; no behavior change — can also ride the next feature release instead). James approves releases.

## Self-Review

Coverage: survey (T1) ✓ fix-what's-measured (T2) ✓ stocks migration (T3) ✓ baseball audit (#4 → T4) ✓ fleet no-retrofit documented (T5) ✓ convention (#2 → T6) ✓. Gating: core-release dependency explicit on T2/T3 only. Placeholders: harness + invariant text are complete; per-surface fixes are survey-driven by design, with the guard recipe + test style fully specified (the plan can't know gaps it hasn't measured — that's T1's output, recorded before T2 starts). Consistency: ladders in-plugin everywhere; 6px rule single-sourced; `led_ticker.plugin`-only imports throughout.
