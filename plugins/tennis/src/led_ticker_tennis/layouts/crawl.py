"""Hi-res ticker crawl (scale>1 `layout = "ticker"`) — the ENGINE-scrolled
cursor contract, ported from baseball's `layouts/crawl.py`:

`cursor_pos` and the return value are LOGICAL px (the units the engine's
scroll math and the ScaledCanvas wrapper use). Segments paint at physical
resolution, so this function multiplies the incoming logical cursor by
`scale` once, accumulates the run's physical width, and ceil-divides it
back to logical before returning. When the run (plus the caller's engine
padding) fits the logical canvas the line is held and CENTERED.

Scrolling text is exempt from the layout collision invariant (motion is
the overflow mechanism) — nothing here is measured against a neighbour.
"""

from led_ticker.plugin import Color, resolve_font, safe_scale

from led_ticker_tennis import _palette as pal
from led_ticker_tennis._models import (
    MatchInfo,
    format_points,
    format_start_time,
    is_break_point,
    status_label,
)
from led_ticker_tennis._paint import hires, js_round, phys_wrap, text_width

_GAP = 12
_DOT_GAP = 9
_STAR_GAP = 2


def _px_size(real_w: int) -> int:
    return 30 if real_w > 300 else 28


def _y_for(px_size: int) -> int:
    """Center the CAP band on the 64-row panel (baseball `_y_for`)."""
    font = resolve_font("Inter-Bold", px_size, 80)
    return js_round((64 + px_size * 0.72) / 2) - font.ascent


def _name(m: MatchInfo, side: int, show_ranking: bool) -> str:
    name = (m.p1 if side == 1 else m.p2).upper() or "?"
    rank = m.p1_rank if side == 1 else m.p2_rank
    if show_ranking and rank:
        name = f"{name} ({rank})"
    return name


def segments(
    m: MatchInfo, tz, *, show_ranking: bool = False
) -> list[tuple[str, Color]]:
    """The crawl as (text, color) pairs — shared with the legacy scale-1
    ticker (`_scoreboard._build_match_message`) so wording never drifts
    between the two paths. Gaps are inserted by the painter."""
    segs: list[tuple[str, Color]] = []
    for side in (1, 2):
        name_c = pal.IDENT
        if m.state == "final" and m.winner in (1, 2):
            name_c = pal.WIN if m.winner == side else pal.LABEL_HI
        segs.append((_name(m, side, show_ranking), name_c))
        if m.state == "live" and m.server == side:
            segs.append(("*", pal.SERVE))
        if side == 1:
            segs.append(("v", pal.LABEL_HI))
    if m.state == "upcoming":
        day, clock = format_start_time(m.start_time, tz)
        segs.append(("·", pal.LABEL))
        segs.append((f"{day} {clock}".strip(), pal.AMBER))
    else:
        games = " ".join(f"{a}-{b}" for a, b in m.games)
        if not games and m.state == "final":
            games = f"{m.sets[0]}-{m.sets[1]} sets"
        if games:
            segs.append((games, pal.AMBER))
        pts = format_points(m.points) if m.state == "live" else ""
        if pts:
            segs.append((f"({pts})", pal.CYAN))
        if m.state == "live" and is_break_point(m.points, m.server, m.is_tiebreak):
            segs.append(("BP", pal.LOSS))
        segs.append(("·", pal.LABEL))
        segs.append((status_label(m), pal.WIN if m.state == "live" else pal.LABEL_HI))
        if m.state == "live" and m.is_tiebreak:
            segs.append(("TB", pal.TB))
    if m.stale:
        segs.append(("STALE", pal.AMBER))
    tail = " ".join(t for t in (m.round_code, m.tournament.upper()) if t)
    if tail:
        segs.append(("·", pal.LABEL))
        segs.append((tail, pal.LABEL_HI))
    return segs


def render_crawl(
    canvas,
    m: MatchInfo,
    tz,
    cursor_pos: int,
    *,
    y_offset: int = 0,
    hold_padding: int = 0,
    show_ranking: bool = False,
) -> int:
    """Draw at LOGICAL `cursor_pos`; return the run's advance width, also
    LOGICAL (see module docstring)."""
    shim, real = phys_wrap(canvas)
    scale = safe_scale(canvas)
    yo = y_offset * scale
    px_size = _px_size(real.width)
    y = _y_for(px_size)
    segs = segments(m, tz, show_ranking=show_ranking)
    widths = [text_width(px_size, t) for t, _ in segs]
    # gap BEFORE each segment: the serve "*" hugs its name, dots sit tight.
    gaps = [0] + [
        (_STAR_GAP if t == "*" else _DOT_GAP if t == "·" else _GAP) for t, _ in segs[1:]
    ]
    run_phys = sum(widths) + sum(gaps)
    logical_advance = -(-run_phys // scale)
    held = logical_advance + hold_padding <= canvas.width
    center_off = js_round((real.width - run_phys) / 2) if held else 0
    x = cursor_pos * scale + center_off
    for (text, color), w, gap in zip(segs, widths, gaps, strict=True):
        x += gap
        if -w < x < real.width:  # performance cull only; hires() clips safely
            hires(shim, text, js_round(x), y + yo, color, px_size)
        x += w
    return logical_advance
