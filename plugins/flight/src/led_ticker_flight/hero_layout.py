"""bigsign layout: hi-res hero ident (design/app.js bigA()).

One flight is shown large at a time, rotating on a fixed schedule
(`idx = floor(clock_ms / DWELL_MS) % len(flights)`): a swept tail-fin,
a huge hi-res callsign, an airline-name/type line underneath, then a
metrics line (vertical-rate cue, altitude, ground speed, track,
distance), and paging dots. All positions are physical pixels —
`dy = y_offset * scale` shifts the whole layout for push transitions.

With 2+ tracked flights, the whole card fades through black for
`paint.FADE_MS` at each end of its dwell window (hardware review: a hard
cut between rotating flights read as a glitch on the physical panel). A
single held flight never fades — see the `bright` computation below.
"""

from led_ticker.plugin import safe_scale

from led_ticker_flight.data import VR_COLOR, fmt_alt, vr_state
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
    RGB,
    SPEED,
    TRACK,
    TYPE,
    airline_of,
)

DWELL_MS = 4200


def render_hero(canvas, flights, clock_ms: float, *, y_offset: int = 0) -> None:
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

    fin_w = draw_fin(sink, 4, 3 + dy, 28, al, bright=b)
    lx = 4 + fin_w + 8
    hires(shim, f.flt, lx, 1 + dy, IDENT, 26, bright=b)

    nx = lx
    if al.name:
        nx += hires(shim, al.name, lx, 30 + dy, al.c1, 10, bright=b) + 6
    if f.actype:
        hires(shim, f.actype, nx, 30 + dy, TYPE, 10, bright=b)

    y, x = 45 + dy, 4
    state = vr_state(f.vr)
    color = VR_COLOR[state]
    if state == "level":
        x += level_bar(real, x, y + 4, color, bright=b) + 3
    else:
        x += (
            hires(shim, "▲" if state == "climb" else "▼", x, y + 1, color, 10, bright=b)
            + 3
        )
    x += hires(shim, fmt_alt(f.alt), x, y, ALT, 12, bright=b) + 7
    x += hires(shim, f"{f.gs}KT", x, y, SPEED, 12, bright=b) + 7
    x += hires(shim, f"{f.trk}°", x, y, TRACK, 12, bright=b) + 7
    hires(shim, f.dist, x, y, DIST, 12, bright=b)

    paging_dots(
        real,
        scale,
        len(flights),
        idx,
        real.width - len(flights) * (2 * scale) - 4,
        real.height - scale * 2 - 2 + dy,
        bright=b,
    )
