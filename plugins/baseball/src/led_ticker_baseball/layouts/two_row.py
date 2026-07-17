"""bigsign two-row scores card — port of design twoRowScores (dc.html:343).

256x64 physical. Top band: AWAY score ...dashes... HOME score. Dotted
divider at y31. Bottom band: live (inning triangle red, bases cluster,
count right-anchored) or centered FINAL, or a "next"-game matchup + start
time for preview/postponed states.

Engine rotates stories (the prototype self-pages via its own clock); paging
dots reflect the caller-supplied (story_index, story_total) instead.

Never raises on missing/None GameInfo fields — every optional numeric or
string field is guarded with `or 0` / `or ""` rather than try/except, so a
genuine bug in this module still surfaces in tests (render-loop breaker
contract: a visual helper must degrade, not crash).
"""

from led_ticker.plugin import safe_scale

from led_ticker_baseball import _palette as pal
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


def render_two_row(
    canvas, game, tz, *, y_offset: int = 0, story_index: int = 0, story_total: int = 1
) -> None:
    shim, real = phys_wrap(canvas)
    yo = y_offset * safe_scale(canvas)
    ac, hc = _team_color(game.away_abbr), _team_color(game.home_abbr)

    if game.state in ("preview", "postponed"):
        _render_next(shim, game, tz, yo, ac, hc)
    else:
        _render_scored(shim, real, game, yo, ac, hc)

    if story_total > 1:
        paging_dots(real, story_total, story_index, 256 - story_total * 8 - 4, 60 + yo)


def _score_color(game, side: str):
    if game.state != "final":
        return pal.IDENT
    a, h = game.away_score or 0, game.home_score or 0
    win = a > h if side == "a" else h > a
    return pal.WIN if win else pal.IDENT


def _render_next(shim, game, tz, yo, ac, hc):
    # centered "AWY @ HOM" at y5 px20, start time / postpone tag centered y38 px18
    parts = [(game.away_abbr, ac), ("@", pal.IDENT), (game.home_abbr, hc)]
    widths = [text_width(20, t) for t, _ in parts]
    total = sum(widths) + 8 * 2
    x = js_round((256 - total) / 2)
    for (t, c), w in zip(parts, widths, strict=True):
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


def _render_scored(shim, real, game, yo, ac, hc):
    dotted_divider(real, 4, 252, 31 + yo)
    # top band, left: away + score + series dashes
    x = 6
    x += hires(shim, game.away_abbr, x, 4 + yo, ac, 20) + 7
    x += hires(shim, str(game.away_score or 0), x, 4 + yo, _score_color(game, "a"), 20)
    series_dashes(real, x + 7, 12 + yo, getattr(game, "series_away_wins", 0), ac)
    # top band, right: score then home, right-aligned at 250
    rx = 250
    hsw = text_width(20, str(game.home_score or 0))
    rx -= hsw
    hires(shim, str(game.home_score or 0), rx, 4 + yo, _score_color(game, "h"), 20)
    rx -= 7
    hnw = text_width(20, game.home_abbr)
    rx -= hnw
    hires(shim, game.home_abbr, rx, 4 + yo, hc, 20)
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
        hires(shim, "FINAL", js_round((256 - fw) / 2), 37 + yo, pal.LABEL, 18)
