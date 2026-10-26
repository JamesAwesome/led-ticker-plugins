"""Scale-1 band board: columns, possession dot, timeout pips, down & distance,
red zone, finals, bye, STALE, and the smallsign clearance tripwire."""

import dataclasses

import pytest
from led_ticker.plugin import make_color

import led_ticker_football._scoreboard as sb
from led_ticker_football import _palette as pal
from led_ticker_football._models import Situation, build_demo_games
from led_ticker_football._scoreboard import FootballBandBoard, build_ticker_message

NOW = 1_700_000_000.0
GAMES, _TD = build_demo_games(NOW)
LIVE, HALF, FINAL_OT, NEXT, BYE = GAMES
TOP, BOT = range(0, 8), range(8, 16)
DIM = (70, 70, 70)


def _px(canvas, rows, xs, color):
    want = (color.red, color.green, color.blue)
    return {
        (x, y)
        for (x, y), v in canvas._pixels.items()
        if v == want and y in rows and x in xs
    }


def _lit(canvas, rows, xs):
    return {
        (x, y)
        for (x, y), v in canvas._pixels.items()
        if v != (0, 0, 0) and y in rows and x in xs
    }


def _board(game, tz, **kw):
    return FootballBandBoard(game, now_fn=lambda: NOW, tz=tz, **kw)


def test_band_board_live_columns(smallsign, tz):
    _board(LIVE, tz).draw(smallsign)
    # Chips, both bands lit, right column lit, nothing off-panel.
    assert _px(smallsign, TOP, range(3), pal.chip("PHI")[0])
    assert _px(smallsign, BOT, range(3), pal.chip("NYG")[0])
    assert _lit(smallsign, TOP, range(130, 160)) and _lit(
        smallsign, BOT, range(130, 160)
    )
    assert max(x for (x, _), v in smallsign._pixels.items() if v != (0, 0, 0)) <= 159
    # Possession dot on the NYG (home, bottom) band only.
    shapes = _board(LIVE, tz)
    shapes.draw(smallsign)
    ext = {(n, b): (x0, x1) for n, x0, x1, b in shapes.shape_extents}
    assert ("DOT", 1) in ext and ("DOT", 0) not in ext
    dot = range(*ext[("DOT", 1)])
    assert len(_px(smallsign, BOT, dot, pal.WHITE)) == 9
    assert not _lit(smallsign, TOP, dot)
    # Timeout pips: PHI has 1 left (1 white + 2 dim), NYG 2 (2 white + 1 dim).
    pips = range(*ext[("PIPS", 0)])
    assert len(_px(smallsign, TOP, pips, pal.WHITE)) == 4
    assert len(_px(smallsign, TOP, pips, pal.DIM)) == 8
    assert len(_px(smallsign, BOT, pips, pal.WHITE)) == 8
    assert len(_px(smallsign, BOT, pips, pal.DIM)) == 4
    # Down & distance in cyan on the possessing band; none on the other.
    dd = range(sb.X_SITUATION, sb.X_SITUATION + 60)
    assert _px(smallsign, BOT, dd, pal.CYAN)
    assert not _px(smallsign, TOP, dd, pal.CYAN)
    # Quarter amber top right, clock white bottom right.
    assert _px(smallsign, TOP, range(130, 160), pal.AMBER)
    assert _px(smallsign, BOT, range(130, 160), pal.WHITE)


def test_band_board_draw_returns_width(smallsign, tz):
    _, w = _board(LIVE, tz).draw(smallsign)
    assert w == smallsign.width


def test_red_zone_turns_down_distance_red(smallsign, tz):
    sit = dataclasses.replace(LIVE.situation, red_zone=True, spot="PHI 12")
    _board(dataclasses.replace(LIVE, situation=sit), tz).draw(smallsign)
    dd = range(sb.X_SITUATION, sb.X_SITUATION + 60)
    assert _px(smallsign, BOT, dd, pal.RED)
    assert not _px(smallsign, BOT, dd, pal.CYAN)
    # The possession dot goes red too.
    assert len(_px(smallsign, BOT, range(sb.X_DOT, sb.X_SITUATION), pal.RED)) >= 9


def test_band_board_halftime_hides_situation(smallsign, tz):
    _board(HALF, tz).draw(smallsign)
    assert not _lit(smallsign, BOT, range(sb.X_DOT, 120))
    assert not _lit(smallsign, TOP, range(sb.X_DOT, 120))
    assert _px(smallsign, TOP, range(120, 160), pal.AMBER)  # HALF
    assert not _lit(smallsign, BOT, range(120, 160))  # no clock


def test_band_board_final_hides_situation_and_colors_winner(smallsign, tz):
    _board(FINAL_OT, tz).draw(smallsign)
    col = range(28, 40)
    assert _px(smallsign, BOT, col, pal.GREEN)  # NYG won 27-24
    assert _px(smallsign, TOP, col, pal.LOSER)
    assert not _lit(smallsign, TOP, range(sb.X_DOT, 120))
    assert _px(smallsign, TOP, range(120, 160), pal.WHITE)  # FINAL
    assert _px(smallsign, BOT, range(140, 160), pal.AMBER)  # OT


def test_band_board_highlight_score(smallsign, tz):
    _board(LIVE, tz, highlight=("NYG", 0.0)).draw(smallsign)
    col = range(28, 40)
    assert _px(smallsign, BOT, col, pal.AMBER)
    assert not _px(smallsign, BOT, col, pal.WHITE)
    assert _px(smallsign, TOP, col, pal.WHITE)


def test_band_board_future_and_bye(smallsign, tz):
    _board(NEXT, tz).draw(smallsign)
    assert _px(smallsign, TOP, range(130, 160), pal.AMBER)  # day
    assert _px(smallsign, BOT, range(130, 160), pal.WHITE)  # kickoff
    assert _px(smallsign, BOT, range(5, 60), pal.DIM)  # venue
    smallsign.Clear()
    _board(BYE, tz, bye=True).draw(smallsign)
    assert _px(smallsign, TOP, range(40, 100), pal.GRAY)  # BYE marker after names


def test_band_board_stale_label(smallsign, tz):
    _board(LIVE, tz, stale=True).draw(smallsign)
    # NYG has the ball (bottom band), so STALE sits in the top band's column.
    assert _px(smallsign, TOP, range(sb.X_SITUATION, 130), pal.DIM)
    assert not _px(smallsign, BOT, range(sb.X_SITUATION, 100), pal.DIM)


def test_band_board_bg_color(smallsign, tz):
    _board(LIVE, tz, bg_color=make_color(1, 2, 3)).draw(smallsign)
    assert smallsign._pixels[(100, 0)] == (1, 2, 3)


def test_ticker_message_uses_segments(tz):
    from led_ticker.plugin import FONT_DEFAULT

    msg = build_ticker_message(FINAL_OT, NOW, tz, font=FONT_DEFAULT)
    assert "".join(t for t, _ in msg.segments) == "PHI 24 · NYG 27 · FINAL/OT"


# ------------------------------------------------------- clearance tripwire


def _spy_texts(monkeypatch, canvas, game, tz, **kw):
    """(text, x0, x1, band) per draw_text call on the band board."""
    calls = []
    orig = sb.draw_text

    def spy(c, font, text, x, y, color):
        end = orig(c, font, text, x, y, color)
        calls.append((text, x, end, 0 if y < canvas.height // 2 else 1))
        return end

    monkeypatch.setattr(sb, "draw_text", spy)
    board = _board(game, tz, **kw)
    board.draw(canvas)
    return calls + [(t, x0, x1, b) for t, x0, x1, b in board.shape_extents]


def _assert_band_clearance(calls, width):
    for i, a in enumerate(calls):
        assert a[1] >= 0 and a[2] <= width, f"{a[0]!r} off-panel: {a[1]}..{a[2]}"
        for b in calls[i + 1 :]:
            if a[3] != b[3]:
                continue
            left, right = (a, b) if a[1] <= b[1] else (b, a)
            gap = right[1] - left[2]
            assert gap >= 6, f"{left[0]!r}..{left[2]} / {right[0]!r} @{right[1]}"


WORST_LIVE = dataclasses.replace(
    LIVE,
    away="WSH",
    home="JAX",
    away_score=48,
    home_score=48,
    clock="14:59",
    situation=Situation(
        possession="JAX",
        down_distance="1ST & GOAL",
        spot="WSH 50",
        red_zone=True,
        away_timeouts=3,
        home_timeouts=3,
        last_play=None,
    ),
)
WORST_ENDQ = dataclasses.replace(
    WORST_LIVE, status="STATUS_END_PERIOD", period=3, clock="0:00", situation=None
)
WORST_FINAL = dataclasses.replace(
    WORST_LIVE, state="final", status="STATUS_FINAL", period=5, final_ot=True
)


@pytest.mark.parametrize(
    "game", [WORST_LIVE, WORST_ENDQ, WORST_FINAL], ids=["live", "end-q3", "final-ot"]
)
@pytest.mark.parametrize("stale", [False, True])
def test_band_board_worst_case_clearance(smallsign, tz, monkeypatch, game, stale):
    calls = _spy_texts(monkeypatch, smallsign, game, tz, stale=stale)
    texts = [c[0] for c in calls]
    assert texts.count("48") == 2
    if game is WORST_LIVE:
        assert "1ST & GOAL" in texts
    if game is WORST_ENDQ:
        assert "END Q3" in texts
    if stale:
        assert "STALE" in texts
    _assert_band_clearance(calls, smallsign.width)


def test_band_board_typical_live_clearance(smallsign, tz, monkeypatch):
    _assert_band_clearance(
        _spy_texts(monkeypatch, smallsign, LIVE, tz), smallsign.width
    )
