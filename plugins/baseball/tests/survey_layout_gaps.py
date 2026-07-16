"""Survey: scoreboard-layout collision audit with worst-case live data.

Run: uv run python tests/survey_layout_gaps.py   (from plugins/baseball)

Spies on `led_ticker.plugin.draw_text` (this widget imports it inside
`draw()`) to record each field's logical extent, then reports overlaps and
<2px near-misses between DIFFERENT fields sharing a y-band.

FINDINGS (2026-07-16 audit — supersedes the earlier "collision-safe"
note, which was verified only on >=128-logical canvases):
- smallsign 160x16 (and any >=~128-logical canvas): CLEAN at the worst
  case (extra innings, full count, bases loaded, ABS pips) — every
  clearance >= 5px. The measured/zone-centered design works as intended.
- bigsign at logical 64 (scale 4): the LIVE center zone is a pile-up even
  with TYPICAL data ("▼5"): the outs dots overlap the 2B diamond AND
  reach the home team name; the base diamonds overlap the B/S count row.
  Root cause: the live rows have no budget check against center_half
  (13 logical px at width 64 — the design assumed >=128, per the
  half_h docstring "8 on 128×16 canvas"). `layout = "scoreboard"` is
  user-selectable on any sign, so this is config-reachable.
- The ABS challenge dash (home side) ends 1px past the logical right
  edge on width 64 (clipped silently — cosmetic).

KNOWN BY-DESIGN pairs the raw detector also flags (not findings): the
diamond cluster overlaps itself (2B/3B/1B form one glyph cluster); the two
stacked ABS pips overlap each other; team names vs ABS pips are in
different vertical bands (the |dy| heuristic is loose). Interpret the
output against the render, not mechanically.
"""

from led_ticker.plugin import HeadlessBackend, ScaledCanvas

import led_ticker.plugin as plug
from led_ticker_baseball._models import GameInfo
from led_ticker_baseball._scoreboard import MLBScoreboardMessage

WORST = GameInfo(
    home_abbr="NYY",
    away_abbr="BOS",
    home_score=12,
    away_score=10,
    state="live",
    inning="▼15",
    balls=3,
    strikes=2,
    outs=2,
    on_first=True,
    on_second=True,
    on_third=True,
    home_challenges=2,
    away_challenges=1,
)
TYPICAL = GameInfo(
    home_abbr="NYY",
    away_abbr="BOS",
    home_score=4,
    away_score=2,
    state="live",
    inning="▼5",
    balls=1,
    strikes=2,
    outs=2,
    on_first=True,
    on_second=False,
    on_third=False,
)


def survey(name, game, w_real, h_real, scale):
    calls = []
    orig_draw = plug.draw_text
    orig_measure = plug.measure_width

    def spy(canvas, font, text, x, y, color=None, **kw):
        width = orig_measure(font, text, canvas)
        calls.append((text, x, x + width, y))
        if color is not None:
            return orig_draw(canvas, font, text, x, y, color, **kw)
        return orig_draw(canvas, font, text, x, y, **kw)

    plug.draw_text = spy
    try:
        real = HeadlessBackend(w_real, h_real).create_canvas()
        canvas = (
            real if scale == 1 else ScaledCanvas(real, scale=scale, content_height=16)
        )
        MLBScoreboardMessage(game=game, team_abbr="NYY").draw(canvas, 0)
    finally:
        plug.draw_text = orig_draw

    logical_w = w_real // scale
    print(f"== {name} (logical width {logical_w}) ==")
    for t, x0, x1, y in calls:
        clip = "  <-- PAST LOGICAL EDGE" if x1 > logical_w else ""
        print(f"  {t!r:8} x{x0:3}-{x1:3} y={y}{clip}")
    print("  -- overlaps / <2px near-misses between fields (|dy| <= 7):")
    hits = 0
    for i, (t1, a0, a1, y1) in enumerate(calls):
        for t2, b0, b1, y2 in calls[i + 1 :]:
            if abs(y1 - y2) <= 7 and b0 < a1 and b1 > a0 and (t1, y1) != (t2, y2):
                print(f"     {t1!r} x{a0}-{a1} OVERLAPS {t2!r} x{b0}-{b1}")
                hits += 1
    if not hits:
        print("     (none)")


if __name__ == "__main__":
    survey("smallsign worst", WORST, 160, 16, 1)
    survey("bigsign TYPICAL", TYPICAL, 256, 64, 4)
    survey("bigsign worst", WORST, 256, 64, 4)
