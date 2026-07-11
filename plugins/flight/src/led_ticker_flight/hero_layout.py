"""bigsign layout: hi-res hero ident (design/app.js bigA()).

One flight is shown large at a time, rotating on a fixed schedule
(`idx = floor(clock_ms / DWELL_MS) % len(flights)`): a swept tail-fin,
a huge hi-res callsign, an airline-name/type line underneath, then a
metrics line (vertical-rate cue, altitude, ground speed, track,
distance), paging dots, and the live-refresh pulse. All positions are
physical pixels — `dy = y_offset * scale` shifts the whole layout for
push transitions.
"""

from led_ticker.plugin import safe_scale

from led_ticker_flight.data import VR_COLOR, fmt_alt, vr_state
from led_ticker_flight.fins import draw_fin
from led_ticker_flight.paint import (
    draw_empty,
    hires,
    live_pulse,
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
LEVEL_BAR_W = 7
LEVEL_BAR_H = 3


def _level_bar(real, x: int, y_top: int, rgb: RGB) -> int:
    """Procedural stand-in for the level (▬) glyph — not in the hires charset."""
    for yy in range(LEVEL_BAR_H):
        for xx in range(LEVEL_BAR_W):
            px(real, x + xx, y_top + yy, rgb)
    return LEVEL_BAR_W


def render_hero(canvas, flights, clock_ms: float, *, y_offset: int = 0) -> None:
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

    fin_w = draw_fin(sink, 4, 3 + dy, 28, al)
    lx = 4 + fin_w + 8
    hires(shim, f.flt, lx, 1 + dy, IDENT, 26)

    nx = lx
    if al.name:
        nx += hires(shim, al.name, lx, 30 + dy, al.c1, 10) + 6
    if f.actype:
        hires(shim, f.actype, nx, 30 + dy, TYPE, 10)

    y, x = 45 + dy, 4
    state = vr_state(f.vr)
    color = VR_COLOR[state]
    if state == "level":
        x += _level_bar(real, x, y + 4, color) + 3
    else:
        x += hires(shim, "▲" if state == "climb" else "▼", x, y + 1, color, 10) + 3
    x += hires(shim, fmt_alt(f.alt), x, y, ALT, 12) + 7
    x += hires(shim, f"{f.gs}KT", x, y, SPEED, 12) + 7
    x += hires(shim, f"{f.trk}°", x, y, TRACK, 12) + 7
    hires(shim, f.dist, x, y, DIST, 12)

    paging_dots(
        real,
        scale,
        len(flights),
        idx,
        real.width - len(flights) * (2 * scale) - 4,
        real.height - scale * 2 - 2 + dy,
    )
    live_pulse(real, scale, clock_ms)
