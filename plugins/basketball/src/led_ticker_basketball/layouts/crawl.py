"""Ticker crawl — the single wording source plus the hi-res painter.

`segments()` is shared by the hi-res crawl (scale>1) and the scale-1
`SegmentMessage` (`_scoreboard.build_ticker_message`), so the wording can
never drift between the two. Segments carry their own spaces and the
` · ` joiner; the painter adds no gaps.

`render_crawl` follows the engine-scrolled cursor contract: `cursor_pos`
and the return value are LOGICAL px; segments paint at physical resolution.
When the run (plus padding) fits the logical canvas the line is held and
CENTERED. Scrolling text is exempt from the layout collision invariant.
"""

from led_ticker.plugin import Color, make_color, resolve_font, safe_scale

from led_ticker_basketball import _palette as pal
from led_ticker_basketball._models import GameInfo, Leader, is_clutch, status_lines
from led_ticker_basketball._paint import hires, js_round, phys_wrap, text_width
from led_ticker_basketball.teams import team

_FONT = "Inter-Bold"


def _px_size(real_w: int) -> int:
    return 30 if real_w > 300 else 28


def _y_for(px_size: int) -> int:
    """Center the CAP band on the 64-row panel."""
    font = resolve_font(_FONT, px_size)
    return js_round((64 + px_size * 0.72) / 2) - font.ascent


def _team_color(abbrev: str) -> Color:
    return make_color(*team(abbrev).primary)


def _name(abbrev: str, record: str) -> list[tuple[str, Color]]:
    segs: list[tuple[str, Color]] = [(abbrev, _team_color(abbrev))]
    if record:
        segs.append((f" {record}", pal.GRAY))
    return segs


def _leader(leader: Leader | None) -> str:
    """`J. EMBIID 31` — the crawl keeps the initial and drops ` PTS`."""
    return f"{leader.name} {leader.points}" if leader is not None else ""


def segments(
    game: GameInfo, now: float, tz, *, stale: bool = False
) -> list[tuple[str, Color]]:
    """The crawl as (text, color) pairs; `"".join(texts)` is the line.
    `stale` adds a DIM ` STALE` right after the state/status run."""
    sep = (" · ", pal.DIM)
    flag = [(" STALE", pal.DIM)] if stale else []
    a, h = game.away, game.home
    if game.state == "future":
        day, clock = status_lines(game, now, tz)
        segs: list[tuple[str, Color]] = [
            *_name(a, game.away_record),
            (" VS " if game.neutral_site else " @ ", pal.GRAY),
            *_name(h, game.home_record),
            sep,
            (f"{day} {clock}".strip(), pal.AMBER),
            *flag,
        ]
        if game.broadcast:
            segs += [sep, (game.broadcast.upper(), pal.DIM)]
        if game.venue:
            segs += [sep, (game.venue.upper(), pal.DIM)]
        return segs

    segs = [
        (a, _team_color(a)),
        (f" {game.away_score}", pal.WHITE),
        sep,
        (h, _team_color(h)),
        (f" {game.home_score}", pal.WHITE),
        sep,
    ]
    label, clock = status_lines(game, now, tz)
    if game.state == "final":
        segs.append((label, pal.WHITE))
        if clock:
            segs.append((f"/{clock}", pal.AMBER))
        return segs + flag

    segs.append((label, pal.AMBER))
    if clock:
        segs.append((f" {clock}", pal.RED if is_clutch(game) else pal.WHITE))
    segs += flag
    for leader in (game.away_leader, game.home_leader):
        text = _leader(leader)
        if text:
            segs += [sep, (text, pal.CYAN)]
    return segs


def render_crawl(
    canvas,
    game: GameInfo,
    now: float,
    tz,
    cursor_pos: int,
    *,
    y_offset: int = 0,
    hold_padding: int = 6,
    stale: bool = False,
) -> int:
    """Draw at LOGICAL `cursor_pos`; return the run's advance width, also
    LOGICAL."""
    shim, real = phys_wrap(canvas)
    scale = safe_scale(canvas)
    yo = y_offset * scale
    px_size = _px_size(real.width)
    y = _y_for(px_size)
    segs = segments(game, now, tz, stale=stale)
    widths = [text_width(px_size, t) for t, _ in segs]
    run_phys = sum(widths)
    logical_advance = -(-run_phys // scale)
    held = logical_advance + hold_padding <= canvas.width
    center_off = js_round((real.width - run_phys) / 2) if held else 0
    x = cursor_pos * scale + center_off
    for (text, color), w in zip(segs, widths, strict=True):
        if -w < x < real.width:  # performance cull only; hires() clips safely
            hires(shim, text, js_round(x), y + yo, color, px_size)
        x += w
    return logical_advance
