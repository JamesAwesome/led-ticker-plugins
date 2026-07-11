"""longboi layout: hi-res dashboard row (design/app.js longA()).

The widescreen target — hero ident on the left, four labelled metric
columns filling the rest of the width. One flight held, rotating on a
fixed schedule (`idx = floor(clock_ms / DWELL_MS) % len(flights)`).
All positions are physical pixels — `dy = y_offset * scale` shifts the
whole layout for push transitions.
"""

from led_ticker.plugin import safe_scale

from led_ticker_flight.data import VR_COLOR, vr_state
from led_ticker_flight.fins import draw_fin
from led_ticker_flight.paint import (
    draw_empty,
    hires,
    level_bar,
    live_pulse,
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


def render_dashboard(canvas, flights, clock_ms: float, *, y_offset: int = 0) -> None:
    shim, real = phys_wrap(canvas)
    scale = safe_scale(canvas)
    dy = y_offset * scale

    if not flights:
        draw_empty(canvas, clock_ms, wide=real.width >= 200, y_offset=y_offset)
        live_pulse(real, scale, clock_ms)
        return

    idx = int(clock_ms // DWELL_MS) % len(flights)
    f = flights[idx]
    al = airline_of(f.flt)

    def sink(x: int, y: int, rgb: RGB, bright: float = 1.0) -> None:
        px(real, x, y, rgb, bright)

    fin_w = draw_fin(sink, 6, 6 + dy, 32, al)
    hx = 6 + fin_w + 10
    iw = hires(shim, f.flt, hx, 5 + dy, IDENT, 26)

    nx = hx
    if al.name:
        nx += hires(shim, al.name, hx, 40 + dy, al.c1, 12) + 7
    if f.actype:
        hires(shim, f.actype, nx, 40 + dy, TYPE, 12)

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
        hires(shim, lab, cx, 8 + dy, LABEL, 10)
        vx = cx
        if i == 0:
            if state == "level":
                vx += level_bar(real, cx, 29 + dy, vr_color) + 3
            else:
                glyph = "▲" if state == "climb" else "▼"
                vx += hires(shim, glyph, cx, 26 + dy, vr_color, 11) + 3
        hires(shim, val, vx, 24 + dy, color, 16)

    paging_dots(
        real,
        scale,
        len(flights),
        idx,
        real.width - len(flights) * (2 * scale) - 6,
        real.height - scale * 2 - 3 + dy,
    )
    live_pulse(real, scale, clock_ms)
