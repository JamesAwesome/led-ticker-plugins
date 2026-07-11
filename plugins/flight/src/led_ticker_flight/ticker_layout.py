"""smallsign layout: single-line 6x12 BDF ticker (design/app.js smallB()).

Everything is drawn through the LOGICAL canvas passed in — on smallsign
(scale=1) logical == physical, so no ScaledCanvas unwrap is needed for the
token drawing itself. The empty-state radar + live-pulse dot still paint at
physical resolution via `paint.draw_empty` / `paint.live_pulse`.
"""

import attrs
from led_ticker.plugin import (
    FONT_DEFAULT,
    compute_baseline,
    draw_text,
    measure_width,
    safe_scale,
    unwrap_to_real,
)

from led_ticker_flight.data import VR_COLOR, VR_GLYPH, Aircraft, fmt_alt, vr_state
from led_ticker_flight.fins import draw_fin, fin_width, js_round
from led_ticker_flight.glyphs import draw_glyph, glyph_size
from led_ticker_flight.paint import dim, draw_empty, live_pulse
from led_ticker_flight.palette import (
    ALT,
    DIST,
    IDENT,
    LABEL,
    RGB,
    SPEED,
    TRACK,
    TYPE,
    Airline,
    airline_of,
)

PX_PER_SEC = 26
ROW_H = 12


@attrs.define
class _Token:
    kind: str  # fin | text | glyph | sep | space
    w: int
    text: str = ""
    rgb: RGB = (0, 0, 0)
    glyph: str = ""
    airline: Airline | None = None
    bright: float = 1.0


def _flight_tokens(canvas, f: Aircraft) -> list[_Token]:
    """One flight's token stream (fin, gap, callsign, sep, type, sep, ...)."""
    al = airline_of(f.flt)
    toks: list[_Token] = []

    toks.append(_Token("fin", fin_width(ROW_H), airline=al))
    toks.append(_Token("space", 4))

    ident_w = measure_width(FONT_DEFAULT, f.flt, canvas)
    toks.append(_Token("text", ident_w, text=f.flt, rgb=IDENT))
    toks.append(_Token("space", 5))

    toks.append(_Token("sep", 1, rgb=LABEL))
    toks.append(_Token("space", 5))

    if f.actype != "":
        type_w = measure_width(FONT_DEFAULT, f.actype, canvas)
        toks.append(_Token("text", type_w, text=f.actype, rgb=TYPE))
        toks.append(_Token("space", 5))

        toks.append(_Token("sep", 1, rgb=LABEL))
        toks.append(_Token("space", 5))

    state = vr_state(f.vr)
    glyph_name = VR_GLYPH[state]
    glyph_w, _ = glyph_size(glyph_name)
    toks.append(_Token("glyph", glyph_w, glyph=glyph_name, rgb=VR_COLOR[state]))
    toks.append(_Token("space", 2))

    alt_text = fmt_alt(f.alt)
    alt_w = measure_width(FONT_DEFAULT, alt_text, canvas)
    toks.append(_Token("text", alt_w, text=alt_text, rgb=ALT))
    toks.append(_Token("space", 5))

    toks.append(_Token("sep", 1, rgb=LABEL))
    toks.append(_Token("space", 5))

    speed_text = f"{f.gs}KT"
    speed_w = measure_width(FONT_DEFAULT, speed_text, canvas)
    toks.append(_Token("text", speed_w, text=speed_text, rgb=SPEED))
    toks.append(_Token("space", 5))

    toks.append(_Token("sep", 1, rgb=LABEL))
    toks.append(_Token("space", 5))

    trk_text = str(f.trk)
    trk_w = measure_width(FONT_DEFAULT, trk_text, canvas)
    toks.append(_Token("text", trk_w, text=trk_text, rgb=TRACK))
    deg_w, _ = glyph_size("deg")
    toks.append(_Token("glyph", deg_w, glyph="deg", rgb=TRACK))
    toks.append(_Token("space", 5))

    toks.append(_Token("sep", 1, rgb=LABEL))
    toks.append(_Token("space", 5))

    dist_w = measure_width(FONT_DEFAULT, f.dist, canvas)
    toks.append(_Token("text", dist_w, text=f.dist, rgb=DIST))
    toks.append(_Token("space", 8))

    toks.append(_Token("sep", 1, rgb=IDENT))
    toks.append(_Token("space", 8))

    return toks


def _build_stream(canvas, flights: list[Aircraft]) -> list[_Token]:
    tokens: list[_Token] = []
    for f in flights:
        tokens.extend(_flight_tokens(canvas, f))
    return tokens


def stream_period(canvas, flights: list[Aircraft]) -> int:
    """Total width (px) of one full loop of the token stream."""
    return sum(t.w for t in _build_stream(canvas, flights))


def _draw_row(
    canvas, tokens: list[_Token], start_x: int, y_top: int, baseline: int
) -> None:
    width = canvas.width
    height = canvas.height

    def sink(x: int, y: int, rgb: RGB, bright: float = 1.0) -> None:
        if 0 <= x < width and 0 <= y < height:
            r, g, b = rgb
            canvas.SetPixel(x, y, int(r * bright), int(g * bright), int(b * bright))

    x = start_x
    for t in tokens:
        if x + t.w <= 0 or x >= width:
            x += t.w
            continue
        if t.kind == "fin":
            assert t.airline is not None  # always set when kind == "fin"
            draw_fin(sink, x, y_top, ROW_H, t.airline, t.bright)
        elif t.kind == "text":
            draw_text(canvas, FONT_DEFAULT, t.text, x, baseline, dim(t.rgb, t.bright))
        elif t.kind == "glyph":
            draw_glyph(sink, t.glyph, x, y_top, t.rgb, bright=t.bright, expand=1)
        elif t.kind == "sep":
            cy = y_top + js_round(ROW_H / 2) - 1
            sink(x, cy, t.rgb, 0.7 * t.bright)
        # "space" tokens carry no pixels.
        x += t.w


def render_ticker(
    canvas, flights: list[Aircraft], clock_ms: float, *, y_offset: int = 0
) -> None:
    real = unwrap_to_real(canvas)
    scale = safe_scale(canvas)

    if not flights:
        wide = canvas.width * scale >= 200
        draw_empty(canvas, clock_ms, wide, y_offset=y_offset)
        live_pulse(real, scale, clock_ms)
        return

    tokens = _build_stream(canvas, flights)
    period = sum(t.w for t in tokens)

    if period > 0:
        off = (clock_ms / 1000 * PX_PER_SEC) % period
        x = canvas.width - off
        # Back-fill: the JS reference only tiles rightward from x, leaving the
        # region left of it blank — the screen blanked every wrap (off -> 0)
        # and re-entered over seconds. The README's prose ("loops seamlessly")
        # wins over that quirk: back up whole periods so tiling starts at or
        # left of x=0 and the screen is fully covered at every clock value.
        while x > 0:
            x -= period
        y_top = (canvas.height - ROW_H) // 2 + y_offset
        baseline = compute_baseline(FONT_DEFAULT, canvas) + y_offset

        guard = 0
        while x < canvas.width and guard < 8:
            if x + period > 0:
                _draw_row(canvas, tokens, int(round(x)), y_top, baseline)
            x += period
            guard += 1

    live_pulse(real, scale, clock_ms)
