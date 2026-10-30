"""bigsign two-row scores card — port of design twoRowScores (dc.html:343).

256x64 physical. Top band: AWAY score ...dashes... HOME score. Dotted
divider at y31. Bottom band: live (inning triangle red, bases cluster,
count right-anchored) or centered FINAL, or a "next"-game matchup + start
time for preview/postponed states.

With `logos` (the default) each team's bundled logo sits just before its
abbrev in the top band (and in the next-game matchup). A logo that cannot
be drawn (`logos=False`, unknown team, missing asset) is simply left out
and that side keeps its logo-free position — per SIDE, so one missing logo
never shifts the other team. When both logos crowd the band, the two
abbrevs shrink together (`_NAME_SIZES`) until the series dashes keep
`_GAP` apart.

Engine rotates stories (the prototype self-pages via its own clock); paging
dots reflect the caller-supplied (story_index, story_total) instead.

Never raises on missing/None GameInfo fields — every optional numeric or
string field is guarded with `or 0` / `or ""` rather than try/except, so a
genuine bug in this module still surfaces in tests (render-loop breaker
contract: a visual helper must degrade, not crash).
"""

from led_ticker.plugin import resolve_font, safe_scale

from led_ticker_baseball import _palette as pal
from led_ticker_baseball._logos import LOGO_ROW, paint_logo, sprite
from led_ticker_baseball._models import _format_game_time
from led_ticker_baseball._paint import (
    hires,
    js_round,
    paging_dots,
    phys_wrap,
    text_width,
)
from led_ticker_baseball._primitives import diamond, dotted_divider, series_dashes
from led_ticker_baseball.teams import _team_color

_GAP = 6  # logo -> abbrev, and the minimum between the two dash pairs
_LOGO_Y = 4  # top band logo rows 4..27: clear of the divider at y31
_NEXT_LOGO_Y = 5  # next-game logo rows 5..28: centred on the px20 caps
_NAME_SIZES = (20, 18, 16)  # top-band abbrev ladder (both sides share one)
_DASH_W = 12  # series_dashes width
_LOGO_W = LOGO_ROW + _GAP  # what a logo adds in front of an abbrev


def _sprite(abbrev: str, logos: bool):
    return sprite(abbrev, LOGO_ROW) if logos and abbrev else None


def _name_top(size: int) -> int:
    """y_top for a top-band abbrev at `size`, sharing the px20 baseline."""
    return (
        4
        + resolve_font("Inter-Bold", 20).ascent
        - resolve_font("Inter-Bold", size).ascent
    )


def render_two_row(
    canvas,
    game,
    tz,
    *,
    y_offset: int = 0,
    story_index: int = 0,
    story_total: int = 1,
    logos: bool = True,
) -> None:
    """`logos=False` draws the logo-free card."""
    shim, real = phys_wrap(canvas)
    yo = y_offset * safe_scale(canvas)
    ac, hc = _team_color(game.away_abbr), _team_color(game.home_abbr)

    if game.state in ("preview", "postponed"):
        _render_next(shim, real, game, tz, yo, ac, hc, logos)
    else:
        _render_scored(shim, real, game, yo, ac, hc, logos)

    if story_total > 1:
        paging_dots(real, story_total, story_index, 256 - story_total * 8 - 4, 60 + yo)


def _score_color(game, side: str):
    if game.state != "final":
        return pal.IDENT
    a, h = game.away_score or 0, game.home_score or 0
    win = a > h if side == "a" else h > a
    return pal.WIN if win else pal.IDENT


def _render_next(shim, real, game, tz, yo, ac, hc, logos):
    # centered "AWY @ HOM" at y5 px20 (each name led by its logo), start
    # time / postpone tag centered y38 px18
    away_spr = _sprite(game.away_abbr, logos)
    home_spr = _sprite(game.home_abbr, logos)
    parts = [
        (game.away_abbr, ac, away_spr),
        ("@", pal.IDENT, None),
        (game.home_abbr, hc, home_spr),
    ]
    widths = [text_width(20, t) + (_LOGO_W if spr else 0) for t, _, spr in parts]
    total = sum(widths) + 8 * 2
    x = js_round((256 - total) / 2)
    for (t, c, spr), w in zip(parts, widths, strict=True):
        if spr is not None:
            paint_logo(real, spr, x, _NEXT_LOGO_Y + yo)
            hires(shim, t, x + _LOGO_W, 5 + yo, c, 20)
        else:
            hires(shim, t, x, 5 + yo, c, 20)
        x += w + 8

    # Gate on state, NOT tag truthiness: GameInfo.postpone_tag DEFAULTS to
    # "PPD" (and the parser sets it for every game), so a truthiness check
    # would label every ordinary preview "PPD" instead of its start time.
    # Same pattern as the sibling renderers (_scoreboard.py).
    if game.state == "postponed" and game.postpone_tag:
        label = game.postpone_tag
    elif game.start_time:
        label = _format_game_time(game.start_time, tz)
    else:
        label = "TBD"
    sw = text_width(18, label)
    hires(shim, label, js_round((256 - sw) / 2), 38 + yo, pal.IDENT, 18)


def _fit_names(game, away_x0: int, home_logo_w: int) -> int:
    """Largest `_NAME_SIZES` entry at which the away dashes end >= `_GAP`
    before the home dashes start (the smallest when none does)."""
    a_score = text_width(20, str(game.away_score or 0))
    h_score = text_width(20, str(game.home_score or 0))
    for size in _NAME_SIZES:
        away_end = away_x0 + text_width(size, game.away_abbr) + 7 + a_score + 7
        away_end += _DASH_W
        home_x = 250 - h_score - 7 - text_width(size, game.home_abbr)
        home_x -= home_logo_w + 19
        if away_end + _GAP <= home_x:
            return size
    return _NAME_SIZES[-1]


def _render_scored(shim, real, game, yo, ac, hc, logos):
    dotted_divider(real, 4, 252, 31 + yo)
    away_spr = _sprite(game.away_abbr, logos)
    home_spr = _sprite(game.home_abbr, logos)
    home_logo_w = _LOGO_W if home_spr is not None else 0
    # top band, left: [logo] away + score + series dashes
    x = 6
    if away_spr is not None:
        paint_logo(real, away_spr, 4, _LOGO_Y + yo)
        x = 4 + _LOGO_W
    size = _fit_names(game, x, home_logo_w)
    x += hires(shim, game.away_abbr, x, _name_top(size) + yo, ac, size) + 7
    x += hires(shim, str(game.away_score or 0), x, 4 + yo, _score_color(game, "a"), 20)
    series_dashes(real, x + 7, 12 + yo, getattr(game, "series_away_wins", 0), ac)
    # top band, right: score then home (then its logo before it),
    # right-aligned at 250
    rx = 250
    hsw = text_width(20, str(game.home_score or 0))
    rx -= hsw
    hires(shim, str(game.home_score or 0), rx, 4 + yo, _score_color(game, "h"), 20)
    rx -= 7
    hnw = text_width(size, game.home_abbr)
    rx -= hnw
    hires(shim, game.home_abbr, rx, _name_top(size) + yo, hc, size)
    if home_spr is not None:
        rx -= _LOGO_W
        paint_logo(real, home_spr, rx, _LOGO_Y + yo)
    series_dashes(real, rx - 19, 12 + yo, getattr(game, "series_home_wins", 0), hc)

    # bottom band
    if game.state == "live":
        bx = 6
        inn = game.inning or ""
        bx += hires(shim, inn, bx, 35 + yo, pal.LOSS, 18) + 12
        diamond(
            real,
            bx + 8,
            39 + yo,
            6,
            bool(game.on_second),
            pal.IDENT if game.on_second else pal.LABEL,
            1.0 if game.on_second else 0.7,
        )
        diamond(
            real,
            bx,
            51 + yo,
            6,
            bool(game.on_third),
            pal.IDENT if game.on_third else pal.LABEL,
            1.0 if game.on_third else 0.7,
        )
        diamond(
            real,
            bx + 16,
            51 + yo,
            6,
            bool(game.on_first),
            pal.IDENT if game.on_first else pal.LABEL,
            1.0 if game.on_first else 0.7,
        )
        # count, right-anchored at 250, drawn right-to-left: outs . strikes . balls
        cx = 250
        seq = [
            (str(game.outs or 0), pal.LOSS),
            ("·", pal.LABEL),
            (str(game.strikes or 0), pal.YEL),
            ("·", pal.LABEL),
            (str(game.balls or 0), pal.WIN),
        ]
        for t, c in seq:
            w = text_width(18, t)
            cx -= w
            hires(shim, t, cx, 35 + yo, c, 18)
            cx -= 3
    else:
        fw = text_width(18, "FINAL")
        hires(shim, "FINAL", js_round((256 - fw) / 2), 37 + yo, pal.LABEL_HI, 18)
