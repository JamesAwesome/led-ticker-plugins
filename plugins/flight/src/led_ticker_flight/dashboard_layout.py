"""longboi layout: hi-res dashboard row (design/app.js longA()).

The widescreen target — hero ident on the left, four labelled metric
columns filling the rest of the width. One flight held, rotating on a
fixed schedule (`idx = floor(clock_ms / DWELL_MS) % len(flights)`).
All positions are physical pixels — `dy = y_offset * scale` shifts the
whole layout for push transitions.

With 2+ tracked flights, the whole row fades through black for
`paint.FADE_MS` at each end of its dwell window (hardware review: a hard
cut between rotating flights read as a glitch on the physical panel). A
single held flight never fades — see the `bright` computation below.
"""

from led_ticker.plugin import fit_text_size, safe_scale

from led_ticker_flight.data import VR_COLOR, vr_state
from led_ticker_flight.fins import draw_fin
from led_ticker_flight.paint import (
    FADE_MS,
    draw_empty,
    hires,
    level_bar,
    paging_dots,
    phys_wrap,
    px,
)
from led_ticker_flight.palette import (
    ALT,
    DIST,
    IDENT,
    LABEL,
    RGB,
    SPEED,
    TRACK,
    TYPE,
    airline_of,
)

DWELL_MS = 4800

# Metric-column value shrink-to-fit ladder (layout collision-guard sweep,
# 2026-07-16 — docs/superpowers/plans/2026-07-16-layout-guards-sweep.md).
# 16 is the design size (handoff's longA() metric columns); the survey
# harness (tests/survey_layout_gaps.py) found a 5-digit altitude + vr-glyph
# prefix can land within 3px of the next column, and a long DIST value
# ("222KM NE") can overflow its own column budget by ~9px — both real
# collisions on worst-case data, not imagined ones. Floor 12 matches the
# name/type row's own size (this file's `hires(..., 12, ...)` calls above)
# so a maximally-shrunk value still reads at a size already used elsewhere
# in this widget. Ladder values are plugin-owned per CLAUDE.md's convention.
_COL_VALUE_SIZES = (16, 14, 12)


def render_dashboard(canvas, flights, clock_ms: float, *, y_offset: int = 0) -> None:
    shim, real = phys_wrap(canvas)
    scale = safe_scale(canvas)
    dy = y_offset * scale

    if not flights:
        draw_empty(canvas, clock_ms, wide=real.width >= 200, y_offset=y_offset)
        return

    idx = int(clock_ms // DWELL_MS) % len(flights)
    f = flights[idx]
    al = airline_of(f.flt)

    b = 1.0
    if len(flights) >= 2:
        pos = clock_ms % DWELL_MS
        b = max(0.0, min(1.0, pos / FADE_MS, (DWELL_MS - pos) / FADE_MS))

    def sink(x: int, y: int, rgb: RGB, bright: float = 1.0) -> None:
        px(real, x, y, rgb, bright)

    fin_w = draw_fin(sink, 6, 6 + dy, 32, al, bright=b)
    hx = 6 + fin_w + 10
    iw = hires(shim, f.flt, hx, 5 + dy, IDENT, 26, bright=b)

    nx = hx
    if al.name:
        nx += hires(shim, al.name, hx, 40 + dy, al.c1, 12, bright=b) + 7
    if f.actype:
        hires(shim, f.actype, nx, 40 + dy, TYPE, 12, bright=b)

    cols = [
        ("ALT FT", f"{f.alt:,}", ALT),
        ("SPD KT", str(f.gs), SPEED),
        ("TRK", f"{f.trk}°", TRACK),
        ("DIST", f.dist, DIST),
    ]
    x = max(hx + iw + 30, 190)
    col_w = (real.width - x - 16) // len(cols)

    state = vr_state(f.vr)
    vr_color = VR_COLOR[state]

    for i, (lab, val, color) in enumerate(cols):
        cx = x + i * col_w
        hires(shim, lab, cx, 8 + dy, LABEL, 10, bright=b)
        vx = cx
        if i == 0:
            if state == "level":
                vx += level_bar(real, cx, 29 + dy, vr_color, bright=b) + 3
            else:
                glyph = "▲" if state == "climb" else "▼"
                vx += hires(shim, glyph, cx, 26 + dy, vr_color, 11, bright=b) + 3
        # Budget = the space left in this column's slot after the vr-glyph
        # prefix (col 0 only; vx == cx elsewhere), minus a 6px inter-column
        # gap (the near-miss rule — stocks #54). The last column has no
        # neighboring column, only the panel edge; it still respects its
        # col_w slot (for visual alignment with the paging dots below) AND,
        # defensively, the true physical right margin.
        budget = col_w - (vx - cx) - 6
        if i == len(cols) - 1:
            budget = min(budget, real.width - vx - 6)
        size = fit_text_size(val, _COL_VALUE_SIZES, budget, font="Inter-Bold")
        hires(shim, val, vx, 24 + dy, color, size, bright=b)

    paging_dots(
        real,
        scale,
        len(flights),
        idx,
        real.width - len(flights) * (2 * scale) - 6,
        real.height - scale * 2 - 3 + dy,
        bright=b,
    )
