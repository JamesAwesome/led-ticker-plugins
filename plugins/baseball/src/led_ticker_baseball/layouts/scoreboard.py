"""longboi physical scoreboard — port of design scoreboardLong (dc.html:382).

512x64 physical. Full team names px20 top corners, scores px34 beneath,
live cluster from x=176 (inning + outs pips, B/S count), bases diamonds
right of center. next/postponed: centered matchup (full names) + time.

The prototype scoreboardLong deliberately has NO paging dots — the
promoLongCard dot position (w - n*8 - 6, h - 10) collides with the home
score's px34 glyph box on live/final games. `story_index`/`story_total`
are kept in the signature for the uniform layout-renderer contract
(two_row uses them) but are intentionally unused here.

Never raises on missing/None GameInfo fields — every optional numeric or
string field is guarded with `or 0` / `or ""` rather than try/except, so a
genuine bug in this module still surfaces in tests (render-loop breaker
contract: a visual helper must degrade, not crash).
"""

from led_ticker.plugin import safe_scale

from led_ticker_baseball import _palette as pal
from led_ticker_baseball._models import _format_game_time
from led_ticker_baseball._paint import hires, js_round, phys_wrap, text_width
from led_ticker_baseball._primitives import (
    challenge_dashes,
    diamond,
    pip,
    series_dashes,
)
from led_ticker_baseball.teams import MLB_TEAM_NAMES, _team_color


def _name(abbr: str) -> str:
    return MLB_TEAM_NAMES.get(abbr, abbr)


def _score_color(game, side: str):
    if game.state != "final":
        return pal.IDENT
    a, h = game.away_score or 0, game.home_score or 0
    win = a > h if side == "a" else h > a
    return pal.WIN if win else pal.IDENT


def render_scoreboard(
    canvas, game, tz, *, y_offset: int = 0, story_index: int = 0, story_total: int = 1
) -> None:
    shim, real = phys_wrap(canvas)
    yo = y_offset * safe_scale(canvas)
    w = real.width
    ac, hc = _team_color(game.away_abbr), _team_color(game.home_abbr)

    if game.state in ("preview", "postponed"):
        _render_next(shim, game, tz, w, yo, ac, hc)
    else:
        _render_scored(shim, real, game, w, yo, ac, hc)
    # No paging dots — see module docstring (prototype fidelity;
    # score-glyph collision). story_index/story_total intentionally unused.


def _render_next(shim, game, tz, w, yo, ac, hc):
    # centered "Away Full Name @ Home Full Name" at y6 px24, start time /
    # postpone tag centered y40 px22
    parts = [(_name(game.away_abbr), ac), ("@", pal.IDENT), (_name(game.home_abbr), hc)]
    widths = [text_width(24, t) for t, _ in parts]
    total = sum(widths) + 10 * 2
    x = js_round((w - total) / 2)
    for (t, c), tw in zip(parts, widths, strict=True):
        hires(shim, t, x, 6 + yo, c, 24)
        x += tw + 10

    # Gate on state, NOT tag truthiness: GameInfo.postpone_tag DEFAULTS to
    # "PPD" (and the parser sets it for every game), so a truthiness check
    # would label every ordinary preview "PPD" instead of its start time.
    # Same pattern as the sibling renderer (two_row._render_next).
    if game.state == "postponed" and game.postpone_tag:
        label = game.postpone_tag
    elif game.start_time:
        label = _format_game_time(game.start_time, tz)
    else:
        label = "TBD"
    tw = text_width(22, label)
    hires(shim, label, js_round((w - tw) / 2), 40 + yo, pal.IDENT, 22)


def _render_scored(shim, real, game, w, yo, ac, hc):
    anw = hires(shim, _name(game.away_abbr), 8, 6 + yo, ac, 20)
    series_dashes(real, 8 + anw + 8, 8 + yo, getattr(game, "series_away_wins", 0), ac)
    asw = hires(
        shim, str(game.away_score or 0), 8, 28 + yo, _score_color(game, "a"), 34
    )

    hnw = text_width(20, _name(game.home_abbr))
    hires(shim, _name(game.home_abbr), 504 - hnw, 6 + yo, hc, 20)
    series_dashes(
        real, 504 - hnw - 8 - 12, 8 + yo, getattr(game, "series_home_wins", 0), hc
    )
    hsw = text_width(34, str(game.home_score or 0))
    home_score_color = _score_color(game, "h")
    hires(shim, str(game.home_score or 0), 504 - hsw, 28 + yo, home_score_color, 34)

    if game.state == "live":
        # ABS (automated ball-strike) challenge dashes beside each score,
        # mirroring the series-win dashes beside each name. Live-only (a
        # game carries challenge state only while in progress); a None count
        # (ABS not equipped / hydration pending) draws nothing.
        if game.away_challenges is not None:
            challenge_dashes(real, 8 + asw + 8, 34 + yo, game.away_challenges)
        if game.home_challenges is not None:
            challenge_dashes(real, (504 - hsw) - 8 - 12, 34 + yo, game.home_challenges)

        ix = 176
        ix += hires(shim, game.inning or "", ix, 5 + yo, pal.IDENT, 18) + 11
        outs = game.outs or 0
        for o in range(3):
            filled = o < outs
            pip(
                real,
                ix + 5 + o * 14,
                14 + yo,
                5,
                filled,
                pal.LOSS if filled else pal.LABEL,
                1.0 if filled else 0.7,
            )

        cx, cy = 176, 32 + yo
        cx += hires(shim, str(game.balls or 0), cx, cy, pal.WIN, 16) + 3
        cx += hires(shim, "B", cx, cy, pal.IDENT, 16) + 9
        cx += hires(shim, str(game.strikes or 0), cx, cy, pal.YEL, 16) + 3
        hires(shim, "S", cx, cy, pal.IDENT, 16)

        for cx_, cy_, occ in (
            (340, 20, game.on_second),
            (324, 34, game.on_third),
            (356, 34, game.on_first),
        ):
            diamond(
                real,
                cx_,
                cy_ + yo,
                7,
                bool(occ),
                pal.IDENT if occ else pal.LABEL,
                1.0 if occ else 0.7,
            )
    else:
        fw = text_width(22, "FINAL")
        hires(shim, "FINAL", js_round((w - fw) / 2), 20 + yo, pal.LABEL_HI, 22)
