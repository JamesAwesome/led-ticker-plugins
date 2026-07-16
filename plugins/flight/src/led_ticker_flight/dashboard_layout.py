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

from led_ticker.plugin import hires_text_width, safe_scale

from led_ticker_flight.data import VR_COLOR, vr_state
from led_ticker_flight.fins import draw_fin
from led_ticker_flight.paint import (
    FADE_MS,
    LEVEL_BAR_W,
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
# name/type row's own size so a maximally-shrunk value still reads at a
# size already used elsewhere in this widget. Ladder values are
# plugin-owned per CLAUDE.md's convention.
#
# ROW-UNIFORM fit (James, 2026-07-16 render review): the fit size is chosen
# ONCE for all four values — mixed value sizes on one row read as broken
# typography, worse than the tight spacing they fixed. The whole row shrinks
# together or not at all.
#
# _COL_GAP = 2, a DOCUMENTED EXCEPTION to the convention's 6px default
# (CONTRIBUTING.md "Layout invariant"): these neighbors are strongly
# color-differentiated (amber/green/cyan/magenta), so even a 1px gap stays
# readable, and 2px is the design's own pre-guard clearance for a climbing
# 5-digit altitude (measured: "34,000" + vr glyph leaves exactly 2px at the
# handoff's 16px — a 3px floor would shrink most climbing/descending
# flights by ONE missing pixel). At 2px every realistic fixture — including
# the survey's worst case — keeps the full 16px design size; the floor
# still forbids touching.
_COL_VALUE_SIZES = (16, 14, 12)
_COL_GAP = 2


def _row_value_size(values, prefix_w: int, col_w: int, last_budget: int) -> int:
    """Shared size for ALL metric-column values: the largest ladder size at
    which every value fits its own budget. Col 0's budget loses the vr
    prefix; the LAST column's budget is the physical right margin, not its
    col_w slot — the design has always let the DIST value spill past its
    even-split slot toward the panel edge (it's the rightmost text; the
    paging dots below are y-separated), and capping it at col_w would shrink
    the whole row for the design's own normal case."""
    for size in _COL_VALUE_SIZES:
        ok = True
        for i, val in enumerate(values):
            if i == len(values) - 1:
                budget = last_budget
            else:
                budget = col_w - _COL_GAP - (prefix_w if i == 0 else 0)
            if hires_text_width(val, size, font="Inter-Bold") > budget:
                ok = False
                break
        if ok:
            return size
    return _COL_VALUE_SIZES[-1]


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

    # Row-uniform fit: measure the vr prefix (col 0 only) without drawing,
    # pick ONE size every value fits at, then draw the whole row with it.
    if state == "level":
        prefix_w = LEVEL_BAR_W + 3
    else:
        prefix_w = hires_text_width("▲" if state == "climb" else "▼", 11) + 3
    last_cx = x + (len(cols) - 1) * col_w
    last_budget = real.width - last_cx - _COL_GAP
    row_size = _row_value_size(
        [val for _lab, val, _c in cols], prefix_w, col_w, last_budget
    )

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
        hires(shim, val, vx, 24 + dy, color, row_size, bright=b)

    paging_dots(
        real,
        scale,
        len(flights),
        idx,
        real.width - len(flights) * (2 * scale) - 6,
        real.height - scale * 2 - 3 + dy,
        bright=b,
    )
