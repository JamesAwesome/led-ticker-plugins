"""Scale-1 band board: columns, possession dot, timeout pips, down & distance,
red zone, finals, bye, STALE, and the smallsign clearance tripwire."""

import dataclasses

import pytest

import led_ticker_football._scoreboard as sb
from led_ticker_football import _palette as pal
from led_ticker_football._models import Situation, build_demo_games
from led_ticker_football._scoreboard import FootballBandBoard, build_ticker_message
from led_ticker_football.emoji import BALL

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


def test_band_board_keeps_core_bg_fill(smallsign, tz):
    # Core fills `bg_color` before every draw; the board paints over it and
    # never clears it (a Fill here would wipe earlier side-by-side widgets).
    smallsign.Fill(1, 2, 3)
    _board(LIVE, tz).draw(smallsign)
    assert smallsign._pixels[(100, 0)] == (1, 2, 3)


def _fresh():
    from led_ticker.plugin import HeadlessBackend

    return HeadlessBackend(160, 16).create_canvas()


def test_band_board_honours_cursor_pos(smallsign, tz):
    """A `ticker` / `one_at_a_time` section hands the board a moving cursor:
    it must paint there and report its right edge, or two cards in a
    side-by-side scroll paint on top of each other."""
    _board(LIVE, tz).draw(smallsign)
    lit0 = _lit(smallsign, range(16), range(160))
    assert lit0
    moved = _fresh()
    _, cursor = _board(LIVE, tz).draw(moved, 20)
    assert cursor == 20 + 160
    assert _lit(moved, range(16), range(160)) == {
        (x + 20, y) for x, y in lit0 if x + 20 < 160
    }
    left = _fresh()
    _, cursor = _board(LIVE, tz).draw(left, -30)
    assert cursor == -30 + 160
    assert _lit(left, range(16), range(160)) == {
        (x - 30, y) for x, y in lit0 if x >= 30
    }


@pytest.mark.parametrize("game", [LIVE, NEXT], ids=["live", "next"])
def test_icon_follows_cursor_pos(smallsign, tz, game):
    board = _board(game, tz)
    board.draw(smallsign)
    icon0 = next(e for e in board.shape_extents if e[0] == "ICON")
    moved = _board(game, tz)
    moved.draw(_fresh(), 20)
    icon1 = next(e for e in moved.shape_extents if e[0] == "ICON")
    assert icon1 == ("ICON", icon0[1] + 20, icon0[2] + 20, icon0[3])


@pytest.mark.parametrize("game", [LIVE, NEXT], ids=["live", "next"])
def test_icon_follows_y_offset(smallsign, tz, game):
    board = _board(game, tz)
    board.draw(smallsign)
    _, x0, x1, _ = next(e for e in board.shape_extents if e[0] == "ICON")
    lit0 = _lit(smallsign, TOP, range(x0, x1))
    assert len(lit0) == len(BALL)
    moved = _fresh()
    _board(game, tz).draw(moved, y_offset=4)
    assert _lit(moved, range(16), range(x0, x1)) >= {(x, y + 4) for x, y in lit0}


def test_band_board_shapes_follow_y_offset(smallsign, tz):
    """PushUp/PushDown hand every draw a y_offset: chips, the possession
    dot and the pips must move with the text, not sit at rest."""
    _board(LIVE, tz).draw(smallsign)
    lit0 = _lit(smallsign, range(16), range(0, sb.X_SITUATION))
    moved = _fresh()
    _board(LIVE, tz).draw(moved, y_offset=4)
    assert _lit(moved, range(16), range(0, sb.X_SITUATION)) == {
        (x, y + 4) for x, y in lit0 if y + 4 < 16
    }


def test_band_board_stale_sits_opposite_the_ball_when_away_has_it(smallsign, tz):
    sit = dataclasses.replace(LIVE.situation, possession="PHI")
    game = dataclasses.replace(LIVE, situation=sit)
    _board(game, tz, stale=True).draw(smallsign)
    assert _px(smallsign, BOT, range(sb.X_SITUATION, 130), pal.DIM)
    assert not _px(smallsign, TOP, range(sb.X_SITUATION, 100), pal.DIM)


def test_band_board_wide_scores_push_shapes_right(smallsign, tz, monkeypatch):
    game = dataclasses.replace(LIVE, away_score=100, home_score=100)
    calls = _spy_texts(monkeypatch, smallsign, game, tz)
    score_end = max(x1 for t, _x0, x1, _b in calls if t == "100")
    dot = next(c for c in calls if c[0] == "DOT")
    assert dot[1] >= score_end + sb._GAP
    dd = next(c for c in calls if c[0] == LIVE.situation.down_distance)
    assert dd[1] > sb.X_SITUATION


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
    """Every pair on a band keeps 6 px, except the sport icon and the item it
    labels (the next one to its right), which may sit `_ICON_GAP` apart."""
    for i, a in enumerate(calls):
        assert a[1] >= 0 and a[2] <= width, f"{a[0]!r} off-panel: {a[1]}..{a[2]}"
        for b in calls[i + 1 :]:
            if a[3] != b[3]:
                continue
            left, right = (a, b) if a[1] <= b[1] else (b, a)
            gap = right[1] - left[2]
            if left[0] == "ICON" and gap == sb._ICON_GAP:
                continue
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


def test_band_board_future_venue_clears_kickoff(smallsign, tz, monkeypatch):
    long_venue = dataclasses.replace(
        NEXT, venue="EverBank Stadium at the Jacksonville Sports Complex"
    )
    calls = _spy_texts(monkeypatch, smallsign, long_venue, tz)
    venue = next(c for c in calls if c[0].startswith("EVERBANK"))
    assert venue[0].endswith("…")
    _assert_band_clearance(_coalesce(calls), smallsign.width)
    calls = _spy_texts(monkeypatch, smallsign, NEXT, tz)
    _assert_band_clearance(_coalesce(calls), smallsign.width)


def _coalesce(calls):
    """Merge texts drawn flush against each other on one band (`NYG`, ` @ `,
    `PHI` is one run whose spaces carry its gaps) into one extent."""
    out = []
    for text, x0, x1, band in calls:
        if out and out[-1][3] == band and out[-1][2] == x0:
            pt, px0, _, _ = out[-1]
            out[-1] = (pt + text, px0, x1, band)
        else:
            out.append((text, x0, x1, band))
    return out


def _icon(board):
    return [e for e in board.shape_extents if e[0] == "ICON"]


def test_future_icon_left_of_matchup(smallsign, tz, monkeypatch):
    calls = _spy_texts(monkeypatch, smallsign, NEXT, tz)
    assert ("ICON", 0, sb._ICON, 0) in calls
    top_texts = [c for c in calls if c[3] == 0 and c[0] != "ICON"]
    assert min(c[1] for c in top_texts) == sb._ICON + sb._ICON_GAP
    venue = next(c for c in calls if c[3] == 1 and c[1] < 100)
    assert venue[1] == sb.X_ABBREV
    assert len(_lit(smallsign, TOP, range(0, sb._ICON))) == len(BALL)


@pytest.mark.parametrize(
    "game,status", [(LIVE, "Q4"), (HALF, "HALF"), (FINAL_OT, "FINAL")]
)
def test_live_and_final_icon_left_of_status(smallsign, tz, monkeypatch, game, status):
    calls = _spy_texts(monkeypatch, smallsign, game, tz)
    icon = next(c for c in calls if c[0] == "ICON")
    st = next(c for c in calls if c[0] == status and c[3] == 0)
    assert icon[3] == 0
    assert icon[2] + sb._ICON_GAP == st[1]
    _assert_band_clearance(calls, smallsign.width)


def test_icon_drops_when_top_band_crowded(smallsign, tz, monkeypatch):
    # The away team has the ball (its down & distance is on the top band)
    # and the top status is long: the icon would crowd `1ST & GOAL`.
    sit = dataclasses.replace(WORST_LIVE.situation, possession=WORST_LIVE.away)
    game = dataclasses.replace(WORST_LIVE, situation=sit)
    monkeypatch.setattr(sb, "status_lines", lambda *_a: ("DELAYED", "2:00"))
    calls = _spy_texts(monkeypatch, smallsign, game, tz)
    assert "DELAYED" in [c[0] for c in calls]
    assert not [c for c in calls if c[0] == "ICON"]
    _assert_band_clearance(calls, smallsign.width)


def test_future_icon_bye_long_codes_clear(smallsign, tz, monkeypatch):
    game = dataclasses.replace(BYE, away="WSH", home="JAX")
    calls = _spy_texts(monkeypatch, smallsign, game, tz, bye=True)
    assert " BYE" in [c[0] for c in calls]
    _assert_band_clearance(_coalesce(calls), smallsign.width)


def test_future_icon_drops_when_matchup_crowds_date(smallsign, tz, monkeypatch):
    monkeypatch.setattr(sb, "status_lines", lambda *_a: ("WEDNESDAY DEC 31", "1:00 PM"))
    calls = _spy_texts(monkeypatch, smallsign, BYE, tz, bye=True)
    assert not [c for c in calls if c[0] == "ICON"]
    top = [c for c in calls if c[3] == 0]
    assert min(c[1] for c in top) == sb.X_ABBREV
