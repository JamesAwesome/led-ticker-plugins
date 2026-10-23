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

from led_ticker_hockey import _palette as pal
from led_ticker_hockey._models import (
    GameInfo,
    fmt_clock,
    live_pp_seconds,
    status_lines,
)
from led_ticker_hockey._paint import hires, js_round, phys_wrap, text_width
from led_ticker_hockey.teams import team

_FONT = "Inter-Bold"


def _px_size(real_w: int) -> int:
    return 30 if real_w > 300 else 28


def _y_for(px_size: int) -> int:
    """Center the CAP band on the 64-row panel."""
    font = resolve_font(_FONT, px_size)
    return js_round((64 + px_size * 0.72) / 2) - font.ascent


def _team_color(abbrev: str) -> Color:
    return make_color(*team(abbrev).primary)


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
            (a, _team_color(a)),
            (" @ ", pal.GRAY),
            (h, _team_color(h)),
            sep,
            (f"{day} {clock}".strip(), pal.AMBER),
            *flag,
        ]
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
    if game.state == "final":
        segs.append(("FINAL", pal.WHITE))
        if game.final_type:
            segs.append((f"/{game.final_type}", pal.AMBER))
        return segs + flag

    label, clock = status_lines(game, now, tz)
    segs.append((label, pal.AMBER))
    if clock:
        segs += [(" ", pal.WHITE), (clock, pal.WHITE)]
    segs += flag
    sit = game.situation
    if sit is not None and sit.pp_team:
        pp = fmt_clock(live_pp_seconds(game, now))
        segs += [sep, (sit.pp_team, _team_color(sit.pp_team))]
        segs.append((f" PP {pp}".rstrip(), pal.AMBER))
    elif sit is not None and sit.en_team:
        segs += [sep, (sit.en_team, _team_color(sit.en_team)), (" EN", pal.AMBER)]
    if game.away_sog is not None and game.home_sog is not None:
        segs += [sep, (f"SOG {game.away_sog}-{game.home_sog}", pal.CYAN)]
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
