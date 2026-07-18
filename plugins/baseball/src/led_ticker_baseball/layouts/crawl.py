"""Hires ticker crawl segments — port of design buildTickerSegs/tickerScores
(dc.html:306-342), adapted from the prototype's self-clocked continuous loop
to the ENGINE-scrolled cursor contract (stocks draw_crawl_story precedent):
the engine advances cursor_pos; we draw this game's segment run at that
offset and return its total advance width.

Unlike stocks' `draw_crawl_story` (which returns an absolute end position,
`cursor + end_padding`), `render_crawl` returns the segment's total content
WIDTH — cursor-independent by construction, so the caller can size the
engine's per-story advance without re-deriving it from cursor arithmetic.

**Units: `cursor_pos` and the return value are LOGICAL** (same units as
`canvas.width` on the ScaledCanvas wrapper and every other engine-scrolled
widget's cursor) — NOT physical. Segments paint at physical resolution
(`_paint.hires`/`_primitives.diamond` write real `SetPixel`s), so this
function is the seam: it multiplies the incoming logical `cursor_pos` by
`scale` once to get the physical paint offset, accumulates the segment
run's total physical width, then ceil-divides that back to logical before
returning (`-(-total_phys // scale)` — same convention as core's
`get_text_width` hires ceil-division in `drawing.py`). Mixing physical
paint-space with the engine's logical stop-position math here was Finding
2 of the final review: the crawl over-scrolled by `real.width -
logical.width` (192 physical px on a bigsign) and held a nearly-blank
final frame.
"""

from led_ticker.plugin import safe_scale

from led_ticker_baseball import _palette as pal
from led_ticker_baseball._models import _format_game_time
from led_ticker_baseball._paint import hires, js_round, phys_wrap, text_width
from led_ticker_baseball._primitives import diamond
from led_ticker_baseball.teams import _team_color

_BASE_R = 6
_BASE_STEP = _BASE_R * 2 + 3  # 15
_BASES_W = _BASE_STEP * 3 - 3  # 42
_MID_Y = 32  # dc.html ycP (~278): fixed vertical center for the bases cluster


def _px_size(real_w: int) -> int:
    return 30 if real_w > 300 else 28


def _y_for(px_size: int) -> int:
    return js_round((64 - px_size * 0.72) / 2)


def _score_color(game, side):
    if game.state != "final":
        return pal.IDENT
    a, h = game.away_score or 0, game.home_score or 0
    win = a > h if side == "a" else h > a
    return pal.WIN if win else pal.IDENT


def _segments(game, tz, px_size):
    """Yield (kind, payload) segments; kind in {'text','gap','bases'}.
    text payload = (string, color, bold); bases payload = game."""
    y = _y_for(px_size)
    ac, hc = _team_color(game.away_abbr), _team_color(game.home_abbr)
    if game.state in ("preview", "postponed"):
        # Gate on state, NOT tag truthiness: GameInfo.postpone_tag DEFAULTS
        # to "PPD" (and the parser sets it for every game), so a truthiness
        # check would label every ordinary preview "PPD" instead of its
        # start time. Same fix as the sibling renderers (two_row.py,
        # scoreboard.py).
        if game.state == "postponed" and game.postpone_tag:
            start = game.postpone_tag
        elif game.start_time:
            start = _format_game_time(game.start_time, tz)
        else:
            start = "TBD"
        segs = [
            ("text", (game.away_abbr, ac, True)),
            ("gap", 11),
            ("text", ("@", pal.IDENT, True)),
            ("gap", 11),
            ("text", (game.home_abbr, hc, True)),
            ("gap", 13),
            ("text", (start, pal.IDENT, False)),
        ]
    else:
        segs = [
            ("text", (game.away_abbr, ac, True)),
            ("gap", 9),
            ("text", (str(game.away_score or 0), _score_color(game, "a"), True)),
            ("gap", 15),
            ("text", (game.home_abbr, hc, True)),
            ("gap", 9),
            ("text", (str(game.home_score or 0), _score_color(game, "h"), True)),
            ("gap", 15),
        ]
        if game.state == "live":
            segs += [
                ("text", (game.inning or "", pal.IDENT, True)),
                ("gap", 14),
                ("bases", game),
                ("gap", 14),
                ("text", (str(game.balls or 0), pal.WIN, True)),
                ("gap", 5),
                ("text", ("·", pal.LABEL, True)),
                ("gap", 5),
                ("text", (str(game.strikes or 0), pal.YEL, True)),
                ("gap", 5),
                ("text", ("·", pal.LABEL, True)),
                ("gap", 5),
                ("text", (str(game.outs or 0), pal.LOSS, True)),
            ]
        else:
            segs.append(("text", ("(Final)", pal.IDENT, False)))
    # trailing separator so side-by-side stories read as one stream
    segs += [("gap", 22), ("text", ("•", pal.LABEL, True)), ("gap", 22)]
    return segs, y


def _seg_w(kind, payload, px_size):
    if kind == "gap":
        return payload
    if kind == "bases":
        return _BASES_W
    text, _c, bold = payload
    return text_width(px_size, text, bold=bold)


def render_crawl(canvas, game, tz, cursor_pos: int, *, y_offset: int = 0) -> int:
    """Draw at LOGICAL `cursor_pos`; return the segment run's advance width,
    also in LOGICAL px (see module docstring for the physical/logical seam)."""
    shim, real = phys_wrap(canvas)
    scale = safe_scale(canvas)
    yo = y_offset * scale
    px_size = _px_size(real.width)
    segs, y = _segments(game, tz, px_size)
    x = cursor_pos * scale  # physical paint offset
    total_phys = 0
    for kind, payload in segs:
        w = _seg_w(kind, payload, px_size)
        # These culls are a performance guard only — hires()/px() clip
        # safely at canvas edges, so a partially off-canvas segment still
        # renders correctly if the cull is skipped or slightly off.
        if kind == "text" and -w < x < real.width:
            text, color, bold = payload
            hires(shim, text, js_round(x), y + yo, color, px_size, bold=bold)
        elif kind == "bases" and -_BASES_W < x < real.width:
            g = payload
            occ = (g.on_third, g.on_second, g.on_first)
            for i, on in enumerate(occ):
                diamond(
                    real,
                    js_round(x) + _BASE_R + i * _BASE_STEP,
                    _MID_Y + yo,
                    _BASE_R,
                    bool(on),
                    pal.IDENT if on else pal.LABEL,
                    1.0 if on else 0.7,
                )
        x += w
        total_phys += w
    return -(-total_phys // scale)  # ceil-division back to logical
