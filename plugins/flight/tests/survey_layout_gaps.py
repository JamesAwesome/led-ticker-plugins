"""Survey: instrument flight layouts with worst-case data; print field gaps.

Run: uv run python tests/survey_layout_gaps.py   (from plugins/flight)

Spies on `hires()` to record each FIELD's extent (more precise than pixel
blocks, which false-flag 4-5px letter gaps inside a word), then reports:
- inter-field gaps < 6px in the same y-band (the collision/near-miss rule —
  a 3px clearance on dev metrics is an overlap on the Pi's freetype), and
- fields running off the panel's right edge (flowing-layout clipping).

Intentional intra-field pairs (the vr glyph + value, spaced `+3` by
construction and accumulated so they cannot overlap) are excluded.

NOTE (post-guard): the dashboard's 2-3px inter-column gaps flagged below
are the DOCUMENTED EXCEPTION (dashboard_layout._COL_GAP = 2 — strongly
color-differentiated neighbors, the design's own pre-guard clearance; see
CONTRIBUTING.md). A rerun showing those flags is expected output, not a
regression; the row-uniform fit guards anything tighter or wider.

FINDINGS (2026-07-16, fixture below — 7-char WN callsign so the SOUTHWEST
airline name renders; descend glyph; widest realistic metric values):
- DASHBOARD: col-0 value '41,000' ends 3px before col-1 ('510' / 'SPD KT')
  -> GENUINE NEAR-MISS between independent columns (col_w = 74px; vr glyph
  + 3 + value = 71px used). Also the DIST value overflows its own column
  budget by ~9px into the right margin (no neighbor; 7px from panel edge).
  GUARD NEEDED: fit each column value to its col_w budget (ladder), col-0
  budget minus the vr-glyph prefix.
- DASHBOARD: ident row, name/type row vs columns — all >= 30px clear at
  worst case (the column x already adapts to ident width). SAFE.
- HERO (256px): all rows flow (accumulated x); metrics line ends x=225 of
  256 at worst case (31px slack). SAFE — no guard; re-run this survey if a
  wider field is ever added.
- TICKER: scrolling stream — motion is the overflow mechanism; no fixed or
  right-aligned positioning (inspected 2026-07-16). Not surveyed.
- paint.draw_empty: has its own measured label fallback whose comment
  admits a residual clip case — checked separately in the guards task.
"""

from led_ticker.plugin import HeadlessBackend, ScaledCanvas

import led_ticker_flight.dashboard_layout as dash
import led_ticker_flight.hero_layout as hero
import led_ticker_flight.paint as paint
from led_ticker_flight.data import Aircraft

# Worst-case: 7-char callsign with a mapped airline prefix (WN -> SOUTHWEST,
# the longest name), widest actype, 5-digit altitude, 3-digit speed/track,
# long distance, descending (vr glyph drawn in col 0 / metrics line).
WORST = [
    Aircraft("WN1234A", "B77W", 41000, -1200, 510, 305, "222KM NE", 222.0, "N7088A"),
]


def survey(name, w, render, calls):
    calls.clear()
    real = HeadlessBackend(w, 64).create_canvas()
    canvas = ScaledCanvas(real, scale=4, content_height=16)
    render(canvas, WORST, 0.0)
    print(f"== {name} ({w}px) ==")
    for t, x0, x1, y, s in calls:
        clip = "  <-- RUNS OFF PANEL" if x1 > w else ""
        print(f"  {t!r:12} x{x0:3}-{x1:3} y{y:2} size{s:2}{clip}")
    print("  -- inter-field gaps < 6 (same y-band; vr-glyph+value pairs excluded):")
    for i, (t1, _a0, a1, y1, _s1) in enumerate(calls):
        for t2, b0, _b1, y2, _s2 in calls[i + 1 :]:
            if abs(y1 - y2) <= 12 and b0 >= a1 - 2:
                gap = b0 - a1
                # The vr glyph + its value are ONE composed field (spaced +3
                # by construction, accumulated — they cannot overlap). Every
                # other <6px pair is a genuine collision surface.
                if gap < 6 and t1 not in ("▲", "▼"):
                    kind = "COLLISION" if gap < 0 else "NEAR-MISS"
                    print(
                        f"     {t1!r} (ends {a1}) -> {t2!r} (starts {b0}): "
                        f"gap {gap}  <-- {kind}"
                    )


if __name__ == "__main__":
    calls = []
    _orig = paint.hires

    def spy(shim, text, x, y_top, color, size, **kw):
        adv = _orig(shim, text, x, y_top, color, size, **kw)
        calls.append((text, x, x + adv, y_top, size))
        return adv

    dash.hires = spy
    hero.hires = spy
    survey("DASHBOARD", 512, dash.render_dashboard, calls)
    survey("HERO", 256, hero.render_hero, calls)
