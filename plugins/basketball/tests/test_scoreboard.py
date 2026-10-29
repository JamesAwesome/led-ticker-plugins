"""Scale-1 single-band board: columns, clutch clock, finals, the next-game
row, STALE, highlight fades, cursor/y offsets, and the smallsign clearance
tripwire."""

import dataclasses

import pytest
from led_ticker.plugin import FONT_DEFAULT, HeadlessBackend, measure_width

import led_ticker_basketball._scoreboard as sb
from led_ticker_basketball import _palette as pal
from led_ticker_basketball._models import build_demo_games
from led_ticker_basketball._scoreboard import BasketballBandBoard, build_ticker_message
from led_ticker_basketball.emoji import BALL

NOW = 1_700_000_000.0
LIVE, HALF, FINAL_OT, NEXT = build_demo_games(NOW)[0]
ROWS = range(16)


def _board(game, tz, **kw):
    return BasketballBandBoard(game, now_fn=lambda: NOW, tz=tz, **kw)


def _fresh():
    return HeadlessBackend(160, 16).create_canvas()


def _px(canvas, xs, color):
    want = (color.red, color.green, color.blue)
    return {(x, y) for (x, y), v in canvas._pixels.items() if v == want and x in xs}


_ALL = range(160)


def _lit(canvas, xs=_ALL):
    return {
        (x, y) for (x, y), v in canvas._pixels.items() if v != (0, 0, 0) and x in xs
    }


def _spy(monkeypatch, canvas, game, tz, **kw):
    """(text, x0, x1, color) per draw_text call, and the board."""
    calls = []
    orig = sb.draw_text

    def spy(c, font, text, x, y, color):
        end = orig(c, font, text, x, y, color)
        calls.append((text, x, x + measure_width(font, text, c), color))
        return end

    monkeypatch.setattr(sb, "draw_text", spy)
    board = _board(game, tz, **kw)
    board.draw(canvas)
    return calls, board


def _rgb(c):
    return (c.red, c.green, c.blue)


def test_band_board_live_columns(smallsign, tz, monkeypatch):
    calls, board = _spy(monkeypatch, smallsign, LIVE, tz)
    chips = {(x0, x1) for _n, x0, x1 in board.shape_extents}
    assert chips == {(0, 2), (157, 159)}
    assert _px(smallsign, range(3), pal.chip("PHI")[0]) == {
        (x, y) for x in range(3) for y in ROWS
    }
    assert len(_px(smallsign, range(157, 160), pal.chip("NY")[0])) == 3 * 16
    by_text = {t: (x0, x1, _rgb(c)) for t, x0, x1, c in calls}
    assert by_text["PHI"][2] == _rgb(pal.chip("PHI")[0])
    assert by_text["NY"][2] == _rgb(pal.chip("NY")[0])
    assert by_text["PHI"][0] >= 3 + sb._GAP
    assert by_text["NY"][1] <= 157 - sb._GAP
    # Away run left, home run right, centre between them.
    assert by_text["PHI"][1] < by_text["98"][0] < by_text["Q4"][0]
    assert by_text["Q4"][0] < by_text["101"][0] < by_text["NY"][0]
    assert any(t.startswith("Q4") for t, *_ in calls)
    assert _rgb(next(c for t, _a, _b, c in calls if t == "Q4")) == _rgb(pal.AMBER)
    assert max(x for x, _ in _lit(smallsign)) <= 159


def test_band_board_centre_is_centred(smallsign, tz, monkeypatch):
    calls, _ = _spy(monkeypatch, smallsign, HALF, tz)
    half = next(c for c in calls if c[0] == "HALF")
    assert abs((half[1] + half[2]) / 2 - 80) <= 1


def test_band_board_draw_returns_width(smallsign, tz):
    _, w = _board(LIVE, tz).draw(smallsign)
    assert w == smallsign.width


def test_band_board_clutch_clock_is_red(smallsign, tz, monkeypatch):
    calls, _ = _spy(monkeypatch, smallsign, LIVE, tz)
    clock = next(c for c in calls if c[0].strip() == "1:48")
    assert _rgb(clock[3]) == _rgb(pal.RED)
    calm = dataclasses.replace(LIVE, clock="7:12")
    calls, _ = _spy(monkeypatch, _fresh(), calm, tz)
    clock = next(c for c in calls if c[0].strip() == "7:12")
    assert _rgb(clock[3]) == _rgb(pal.WHITE)


def test_band_board_final_colors_and_ot(smallsign, tz, monkeypatch):
    calls, _ = _spy(monkeypatch, smallsign, FINAL_OT, tz)
    colors = {t: _rgb(c) for t, _a, _b, c in calls}
    assert colors["118"] == _rgb(pal.GREEN)  # NY won 118-115
    assert colors["115"] == _rgb(pal.LOSER)
    assert colors["FINAL"] == _rgb(pal.WHITE)
    assert colors["/OT"] == _rgb(pal.AMBER)
    final = next(c for c in calls if c[0] == "FINAL")
    ot = next(c for c in calls if c[0] == "/OT")
    assert ot[1] == final[2]  # one run, drawn flush


def test_band_board_halftime_and_end_period(smallsign, tz, monkeypatch):
    calls, _ = _spy(monkeypatch, smallsign, HALF, tz)
    assert [(t, _rgb(c)) for t, _a, _b, c in calls if t == "HALF"] == [
        ("HALF", _rgb(pal.AMBER))
    ]
    end = dataclasses.replace(LIVE, status="STATUS_END_PERIOD", period=3, clock="0.0")
    calls, _ = _spy(monkeypatch, _fresh(), end, tz)
    texts = [c[0] for c in calls]
    assert "END Q3" in texts and not any("0.0" in t for t in texts)


def test_band_board_future_row(smallsign, tz, monkeypatch):
    calls, board = _spy(monkeypatch, smallsign, NEXT, tz)
    colors = {t: _rgb(c) for t, _a, _b, c in calls}
    assert colors["NY"] == _rgb(pal.chip("NY")[0])
    assert colors["PHI"] == _rgb(pal.chip("PHI")[0])
    assert colors[" @ "] == _rgb(pal.GRAY)
    chips = {(x0, x1) for n, x0, x1 in board.shape_extents if n == "CHIP"}
    assert chips == {(0, 2), (157, 159)}
    time_call = next(c for c in calls if c[0].startswith("7:30"))
    assert _rgb(time_call[3]) == _rgb(pal.WHITE)
    assert time_call[2] <= 157 - sb._GAP
    day = next(c for c in calls if _rgb(c[3]) == _rgb(pal.AMBER))
    assert day[2] + sb._GAP <= time_call[1]
    assert not any("XFINITY" in t.upper() for t, *_ in calls)  # no venue
    _assert_clearance(_coalesce(calls), board.shape_extents, 160)
    # Neutral site and a TBD tip-off.
    calls, _ = _spy(
        monkeypatch, _fresh(), dataclasses.replace(NEXT, neutral_site=True), tz
    )
    assert " VS " in [c[0] for c in calls]
    calls, _ = _spy(monkeypatch, _fresh(), dataclasses.replace(NEXT, time_tbd=True), tz)
    tbd = next(c for c in calls if c[0] == "TBD")
    assert _rgb(tbd[3]) == _rgb(pal.DIM)


def test_band_board_future_stale_left_of_day_when_it_fits(smallsign, tz, monkeypatch):
    # A short day label (no start time yet: `TBD`) leaves room for the flag.
    short = dataclasses.replace(NEXT, start_utc=None)
    calls, board = _spy(monkeypatch, smallsign, short, tz, stale=True)
    stale = next(c for c in calls if c[0] == "STALE")
    day = next(c for c in calls if c[0] == "TBD")
    assert _rgb(stale[3]) == _rgb(pal.DIM)
    assert stale[2] + sb._GAP <= day[1]
    _assert_clearance(_coalesce(calls), board.shape_extents, 160)
    # A full date + tip-off leaves no room: the flag is dropped, never the date.
    calls, board = _spy(monkeypatch, _fresh(), NEXT, tz, stale=True)
    texts = [c[0] for c in calls]
    assert "STALE" not in texts and any(t.startswith("7:30") for t in texts)
    _assert_clearance(_coalesce(calls), board.shape_extents, 160)


def test_band_board_stale_after_or_replacing_centre(smallsign, tz, monkeypatch):
    calls, _ = _spy(monkeypatch, smallsign, HALF, tz, stale=True)
    half = next(c for c in calls if c[0] == "HALF")
    stale = next(c for c in calls if c[0] == "STALE")
    assert _rgb(stale[3]) == _rgb(pal.DIM)
    assert stale[1] >= half[2] + sb._GAP
    calls, _ = _spy(monkeypatch, _fresh(), LIVE, tz, stale=True)
    texts = [c[0] for c in calls]
    assert "STALE" in texts and "Q4" not in texts  # no room: STALE replaces


def test_band_board_honours_cursor_pos(smallsign, tz):
    _board(LIVE, tz).draw(smallsign)
    lit0 = _lit(smallsign)
    assert lit0
    moved = _fresh()
    _, cursor = _board(LIVE, tz).draw(moved, 20)
    assert cursor == 20 + 160
    assert _lit(moved) == {(x + 20, y) for x, y in lit0 if x + 20 < 160}
    left = _fresh()
    _, cursor = _board(LIVE, tz).draw(left, -30)
    assert cursor == -30 + 160
    assert _lit(left) == {(x - 30, y) for x, y in lit0 if x >= 30}


def test_band_board_follows_y_offset(smallsign, tz):
    _board(LIVE, tz).draw(smallsign)
    lit0 = _lit(smallsign)
    moved = _fresh()
    _board(LIVE, tz).draw(moved, y_offset=4)
    assert _lit(moved) == {(x, y + 4) for x, y in lit0 if y + 4 < 16}


def test_band_board_keeps_core_bg_fill(smallsign, tz):
    smallsign.Fill(1, 2, 3)
    _board(LIVE, tz).draw(smallsign)
    assert smallsign._pixels[(80, 0)] == (1, 2, 3)


def test_band_board_highlight_fades_toward_rest_color(smallsign, tz, monkeypatch):
    def score_color(game, hl, text):
        calls, _ = _spy(monkeypatch, _fresh(), game, tz, highlight=hl)
        return next(_rgb(c) for t, _a, _b, c in calls if t == text)

    ny = _rgb(pal.chip("NY")[0])
    assert score_color(LIVE, {"NY": 0.0}, "101") == ny
    assert score_color(LIVE, {"NY": 1.0}, "101") == _rgb(pal.WHITE)
    mid = score_color(LIVE, {"NY": 0.5}, "101")
    assert mid == _rgb(pal.lerp(pal.chip("NY")[0], pal.WHITE, 0.5))
    assert mid not in (ny, _rgb(pal.WHITE))
    assert score_color(LIVE, {"NY": 0.0}, "98") == _rgb(pal.WHITE)  # PHI untouched
    # A final fades to the colour the score RESTS at (green winner).
    assert score_color(FINAL_OT, {"NY": 1.0}, "118") == _rgb(pal.GREEN)
    assert score_color(FINAL_OT, {"NY": 0.0}, "118") == ny


def test_ticker_message_uses_segments(tz):
    msg = build_ticker_message(FINAL_OT, NOW, tz, font=FONT_DEFAULT)
    assert "".join(t for t, _ in msg.segments) == "PHI 115 · NY 118 · FINAL/OT"
    stale = build_ticker_message(FINAL_OT, NOW, tz, stale=True)
    assert "".join(t for t, _ in stale.segments).endswith(" STALE")


# ------------------------------------------------------- clearance tripwire


def _coalesce(calls):
    """Merge texts drawn flush (`NY`, ` @ `, `PHI`; `Q4`, ` 1:48`): one run
    whose own spaces carry its gaps."""
    out = []
    for text, x0, x1, color in sorted(calls, key=lambda c: c[1]):
        if out and out[-1][2] == x0:
            pt, px0, _, pc = out[-1]
            out[-1] = (pt + text, px0, x1, pc)
        else:
            out.append((text, x0, x1, color))
    return out


def _assert_clearance(calls, shapes, width):
    # Shape extents are INCLUSIVE (rect bounds); text extents end-exclusive.
    items = [(t, x0, x1) for t, x0, x1, _c in calls] + [
        (n, x0, x1 + 1) for n, x0, x1 in shapes
    ]
    items.sort(key=lambda i: i[1])
    for item in items:
        assert item[1] >= 0 and item[2] <= width, f"{item!r} off-panel"
    for a, b in zip(items, items[1:], strict=False):
        # The ball may sit `_ICON_GAP` from the names it labels.
        if a[0] == "ICON" and b[1] - a[2] == sb._ICON_GAP:
            continue
        assert b[1] - a[2] >= 6, f"{a!r} / {b!r}"


WORST = dataclasses.replace(
    LIVE,
    away="UTAH",
    home="WSH",
    away_score=148,
    home_score=148,
    period=6,
    clock="0:00.0",
    status="STATUS_IN_PROGRESS",
    away_leader=None,
    home_leader=None,
)


@pytest.mark.parametrize("stale", [False, True])
def test_band_board_worst_case_clearance(smallsign, tz, monkeypatch, stale):
    calls, board = _spy(monkeypatch, smallsign, WORST, tz, stale=stale)
    texts = [c[0] for c in calls]
    assert texts.count("148") == 2
    assert not any(t.startswith("2OT") for t in texts)  # the centre shrank
    if stale:
        # No room for the clock AND the flag: STALE replaces the centre
        # (a stale clock is the one thing the board must not assert).
        assert "STALE" in texts
        assert not any(t.startswith("0:") for t in texts)
    else:
        assert any(
            t == "0:00.0" or (t.startswith("0:") and t.endswith("…")) for t in texts
        )
    _assert_clearance(_coalesce(calls), board.shape_extents, smallsign.width)


@pytest.mark.parametrize("game", [LIVE, HALF, FINAL_OT], ids=["live", "half", "final"])
@pytest.mark.parametrize("stale", [False, True])
def test_band_board_typical_clearance(smallsign, tz, monkeypatch, game, stale):
    calls, board = _spy(monkeypatch, smallsign, game, tz, stale=stale)
    _assert_clearance(_coalesce(calls), board.shape_extents, smallsign.width)


def test_band_board_worst_final_shrinks_to_f_ot(smallsign, tz, monkeypatch):
    game = dataclasses.replace(
        FINAL_OT, away="UTAH", home="WSH", away_score=148, home_score=147
    )
    calls, board = _spy(monkeypatch, smallsign, game, tz, stale=False)
    texts = [c[0] for c in calls]
    _assert_clearance(_coalesce(calls), board.shape_extents, smallsign.width)
    assert "FINAL" in texts or "F" in texts
    assert "/OT" in texts


def test_band_board_worst_future_shrinks_day_label(smallsign, tz, monkeypatch):
    game = dataclasses.replace(NEXT, away="UTAH", home="WSH", neutral_site=True)
    calls, board = _spy(monkeypatch, smallsign, game, tz, stale=True)
    texts = [c[0] for c in calls]
    assert any(t.startswith("7:30") for t in texts)  # the tip-off survives
    _assert_clearance(_coalesce(calls), board.shape_extents, smallsign.width)


def test_band_board_never_raises_on_sparse_game(smallsign, tz):
    bare = dataclasses.replace(NEXT, start_utc=None, broadcast="", venue="")
    _board(bare, tz).draw(smallsign)
    _board(dataclasses.replace(LIVE, clock="", status="STATUS_DELAYED"), tz).draw(
        _fresh()
    )


def test_band_board_centre_ellipsizes_last(smallsign, tz, monkeypatch):
    # `END 2OT` has no clock to fall back to and is wider than the window.
    end = dataclasses.replace(WORST, status="STATUS_END_PERIOD")
    calls, board = _spy(monkeypatch, smallsign, end, tz)
    centre = [c for c in calls if c[0] not in ("UTAH", "WSH", "148")]
    assert len(centre) == 1 and centre[0][0].endswith("…")
    assert centre[0][0].startswith("END")
    assert _rgb(centre[0][3]) == _rgb(pal.AMBER)
    _assert_clearance(_coalesce(calls), board.shape_extents, smallsign.width)


def test_band_board_cancelled_final(smallsign, tz, monkeypatch):
    canc = dataclasses.replace(FINAL_OT, status="STATUS_CANCELED")
    calls, _ = _spy(monkeypatch, smallsign, canc, tz)
    colors = {t: _rgb(c) for t, _a, _b, c in calls}
    assert colors["CANC"] == _rgb(pal.WHITE)
    assert colors["118"] == _rgb(pal.WHITE)  # no winner on a cancelled game
    assert "/OT" not in colors


_LEFT = max(sb.X_ABBREV, sb._CHIP + sb._GAP)


def _no_ball(monkeypatch, canvas, game, tz, **kw):
    """The same card with the ball made impossible to fit: today's layout."""
    with monkeypatch.context() as m:
        m.setattr(sb, "_ICON", 200)
        calls, _ = _spy(m, canvas, game, tz, **kw)
    return [c[:3] for c in calls]


def _icons(board):
    return [e for e in board.shape_extents if e[0] == "ICON"]


SHORT = dataclasses.replace(NEXT, start_utc=None)  # `TBD`: a short right side


def test_future_ball_when_it_fits(smallsign, tz, monkeypatch):
    calls, board = _spy(monkeypatch, smallsign, SHORT, tz)
    assert _icons(board) == [("ICON", _LEFT, _LEFT + 7)]
    away = next(c for c in calls if c[0] == SHORT.away)
    assert away[1] == _LEFT + sb._ICON + sb._ICON_GAP
    ball = _lit(smallsign, range(_LEFT, _LEFT + 8))
    assert len(ball) == len(BALL) and {y for _, y in ball} <= set(range(4, 12))
    _assert_clearance(_coalesce(calls), board.shape_extents, 160)


@pytest.mark.parametrize(
    "day,tip", [("TONIGHT", "7:00 PM"), ("WED DEC 25", "10:00 PM")], ids=str
)
def test_future_ball_keeps_the_day_and_tip(smallsign, tz, monkeypatch, day, tip):
    monkeypatch.setattr(sb, "status_lines", lambda *_a: (day, tip))
    game = dataclasses.replace(NEXT, away="PHI", home="BOS")
    expected = _no_ball(monkeypatch, _fresh(), game, tz)
    calls, board = _spy(monkeypatch, smallsign, game, tz)
    assert [c[0] for c in calls] == [c[0] for c in expected]
    if not _icons(board):
        assert [c[:3] for c in calls] == expected
    _assert_clearance(_coalesce(calls), board.shape_extents, 160)


def test_future_ball_drops_when_it_would_cost_the_tip(smallsign, tz, monkeypatch):
    # Long names leave only room for the run picked without the ball:
    # no ball, and the card is exactly today's.
    monkeypatch.setattr(sb, "status_lines", lambda *_a: ("DEC 25", "10:00 PM"))
    game = dataclasses.replace(NEXT, away="UTAH", home="PHI")
    calls, board = _spy(monkeypatch, smallsign, game, tz)
    assert not _icons(board)
    assert [c[:3] for c in calls] == _no_ball(monkeypatch, _fresh(), game, tz)


def test_future_ball_never_costs_stale(smallsign, tz, monkeypatch):
    # STALE fits beside the short `TBD` card today: the ball must not cost it.
    expected = _no_ball(monkeypatch, _fresh(), SHORT, tz, stale=True)
    assert "STALE" in [c[0] for c in expected]
    calls, board = _spy(monkeypatch, smallsign, SHORT, tz, stale=True)
    texts = [c[0] for c in calls]
    assert "STALE" in texts
    if not _icons(board):
        assert [c[:3] for c in calls] == expected
    _assert_clearance(_coalesce(calls), board.shape_extents, 160)


@pytest.mark.parametrize(
    "away,home", [("NY", "PHI"), ("UTAH", "PHI"), ("PHI", "GS")], ids=str
)
@pytest.mark.parametrize("stale", [False, True])
def test_future_ball_never_costs_any_text(
    smallsign, tz, monkeypatch, away, home, stale
):
    game = dataclasses.replace(NEXT, away=away, home=home)
    expected = _no_ball(monkeypatch, _fresh(), game, tz, stale=stale)
    calls, board = _spy(monkeypatch, smallsign, game, tz, stale=stale)
    # Same texts in the same order (only the names may shift for the ball).
    assert [c[0] for c in calls] == [c[0] for c in expected]
    if not _icons(board):
        assert [c[:3] for c in calls] == expected
    _assert_clearance(_coalesce(calls), board.shape_extents, 160)


def test_ball_follows_cursor_and_y_offset(smallsign, tz):
    board = _board(SHORT, tz)
    board.draw(smallsign)
    lit0 = _lit(smallsign, range(_LEFT, _LEFT + 8))
    moved = _fresh()
    shifted = _board(SHORT, tz)
    shifted.draw(moved, 20, y_offset=2)
    assert _icons(shifted) == [("ICON", _LEFT + 20, _LEFT + 27)]
    assert _lit(moved, range(_LEFT + 20, _LEFT + 28)) == {
        (x + 20, y + 2) for x, y in lit0
    }
