import dataclasses

import pytest
from led_ticker.plugin import make_color

import led_ticker_hockey._scoreboard as sb
from led_ticker_hockey import _palette as pal
from led_ticker_hockey._models import Situation, build_demo_games
from led_ticker_hockey._scoreboard import HockeyBandBoard, build_ticker_message

NOW = 1_700_000_000.0


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


TOP, BOT = range(0, 8), range(8, 16)


def _board(game, tz, **kw):
    return HockeyBandBoard(game, now_fn=lambda: NOW, tz=tz, **kw)


def test_band_board_lights_both_bands_and_right_column(smallsign, tz):
    _board(build_demo_games(NOW)[0], tz).draw(smallsign)
    assert _lit(smallsign, TOP, range(160)) and _lit(smallsign, BOT, range(160))
    phi = pal.chip("PHI")[0]
    assert _px(smallsign, TOP, range(3), phi)
    right = range(130, 160)
    assert _lit(smallsign, TOP, right) and _lit(smallsign, BOT, right)
    assert max(x for (x, _), v in smallsign._pixels.items() if v != (0, 0, 0)) <= 159


def test_band_board_draw_returns_width(smallsign, tz):
    _, w = _board(build_demo_games(NOW)[0], tz).draw(smallsign)
    assert w == smallsign.width


def test_band_board_pp_on_home_band_only(smallsign, tz):
    _board(build_demo_games(NOW)[0], tz).draw(smallsign)
    xs = range(84, 125)
    assert _px(smallsign, BOT, xs, pal.AMBER)
    assert not _px(smallsign, TOP, xs, pal.AMBER)


def test_band_board_final_winner_green(smallsign, tz):
    _board(build_demo_games(NOW)[2], tz).draw(smallsign)
    col = range(28, 36)
    assert _px(smallsign, TOP, col, pal.GREEN)  # PHI won 3-2
    assert not _px(smallsign, BOT, col, pal.GREEN)
    assert _px(smallsign, BOT, col, pal.LOSER)


def test_band_board_highlight_score(smallsign, tz):
    _board(build_demo_games(NOW)[0], tz, highlight=("NYI", 0.0)).draw(smallsign)
    col = range(28, 36)
    assert _px(smallsign, BOT, col, pal.AMBER)
    assert not _px(smallsign, BOT, col, pal.WHITE)
    assert _px(smallsign, TOP, col, pal.WHITE)


def test_band_board_stale_replaces_sog_label(smallsign, tz):
    g = build_demo_games(NOW)[0]
    _board(g, tz).draw(smallsign)
    fresh = {k: v for k, v in smallsign._pixels.items() if v == (70, 70, 70)}
    smallsign.Clear()
    _board(g, tz, stale=True).draw(smallsign)
    stale = {k: v for k, v in smallsign._pixels.items() if v == (70, 70, 70)}
    assert stale and stale != fresh
    # values are kept
    assert _px(smallsign, TOP, range(60, 80), pal.CYAN)
    assert _px(smallsign, BOT, range(60, 80), pal.CYAN)


def test_band_board_empty_net_marker(smallsign, tz):
    from dataclasses import replace

    from led_ticker_hockey._models import Situation

    g = replace(build_demo_games(NOW)[0], situation=Situation(None, None, "PHI"))
    _board(g, tz).draw(smallsign)
    assert _px(smallsign, TOP, range(84, 100), pal.AMBER)
    assert not _px(smallsign, BOT, range(84, 100), pal.AMBER)


def test_band_board_future_layout(smallsign, tz):
    _board(build_demo_games(NOW)[3], tz).draw(smallsign)
    assert _lit(smallsign, TOP, range(160)) and _lit(smallsign, BOT, range(160))
    assert _px(smallsign, TOP, range(130, 160), pal.AMBER)
    assert _px(smallsign, BOT, range(130, 160), pal.WHITE)
    assert _px(smallsign, BOT, range(5, 60), pal.DIM)


def test_band_board_does_not_fill_bg_color(smallsign, tz):
    """Core fills `bg_color` before every draw; the board must not clear a
    scroll section's earlier widgets."""
    smallsign.SetPixel(100, 0, 9, 9, 9)
    _board(build_demo_games(NOW)[0], tz, bg_color=make_color(1, 2, 3)).draw(smallsign)
    assert smallsign._pixels[(100, 0)] == (9, 9, 9)


def _fresh(smallsign):
    return type(smallsign)(smallsign.width, smallsign.height)


@pytest.mark.parametrize("idx", [0, 3], ids=["live", "future"])
def test_band_board_honours_cursor_pos(smallsign, tz, idx):
    """A scroll section hands the board a moving cursor: it must paint
    there and report its right edge."""
    game = build_demo_games(NOW)[idx]
    _board(game, tz).draw(smallsign)
    lit0 = _lit(smallsign, range(16), range(160))
    assert lit0
    moved = _fresh(smallsign)
    _, cursor = _board(game, tz).draw(moved, 20)
    assert cursor == 20 + 160
    assert _lit(moved, range(16), range(160)) == {
        (x + 20, y) for x, y in lit0 if x + 20 < 160
    }
    left = _fresh(smallsign)
    _, cursor = _board(game, tz).draw(left, -30)
    assert cursor == -30 + 160
    assert _lit(left, range(16), range(160)) == {
        (x - 30, y) for x, y in lit0 if x >= 30
    }


def test_band_board_shapes_follow_y_offset(smallsign, tz):
    """PushUp/PushDown hand every draw a y_offset: the chips must move with
    the text, not sit at rest."""
    game = build_demo_games(NOW)[0]
    _board(game, tz).draw(smallsign)
    chips0 = _lit(smallsign, range(16), range(3))
    assert chips0
    moved = _fresh(smallsign)
    _board(game, tz).draw(moved, y_offset=4)
    assert _lit(moved, range(16), range(3)) == {
        (x, y + 4) for x, y in chips0 if y + 4 < 16
    }
    whole = _lit(smallsign, range(16), range(160))
    assert _lit(moved, range(16), range(160)) == {
        (x, y + 4) for x, y in whole if y + 4 < 16
    }


def test_ticker_message_uses_segments(tz):
    from led_ticker.plugin import FONT_DEFAULT

    msg = build_ticker_message(build_demo_games(NOW)[2], NOW, tz, font=FONT_DEFAULT)
    assert "".join(t for t, _ in msg.segments) == "PHI 3 · NYI 2 · FINAL/OT"


# ------------------------------------------ STALE, clearance, intermission

DIM = (70, 70, 70)
LIVE, INTERMISSION, FINAL_OT, NEXT = build_demo_games(NOW)


def test_band_board_stale_shown_without_sog(smallsign, tz):
    g = dataclasses.replace(LIVE, away_sog=None, home_sog=None)
    _board(g, tz, stale=True).draw(smallsign)
    dim = {k for k, v in smallsign._pixels.items() if v == DIM}
    assert {y for _, y in dim} & set(TOP) and {y for _, y in dim} & set(BOT)


def _spy_texts(monkeypatch, canvas, game, tz, **kw):
    """(text, x0, x1, band) per draw_text call on the band board."""
    calls = []
    orig = sb.draw_text

    def spy(c, font, text, x, y, color):
        end = orig(c, font, text, x, y, color)
        calls.append((text, x, end, 0 if y < canvas.height // 2 else 1))
        return end

    monkeypatch.setattr(sb, "draw_text", spy)
    _board(game, tz, **kw).draw(canvas)
    return calls


def _assert_band_clearance(calls, width):
    for i, a in enumerate(calls):
        assert a[1] >= 0 and a[2] <= width, f"{a[0]!r} off-panel: {a[1]}..{a[2]}"
        for b in calls[i + 1 :]:
            if a[3] != b[3]:
                continue
            left, right = (a, b) if a[1] <= b[1] else (b, a)
            gap = right[1] - left[2]
            assert gap >= 6, f"{left[0]!r}..{left[2]} / {right[0]!r} @{right[1]}"


WORST_SMALL_LIVE = dataclasses.replace(
    LIVE,
    away_score=10,
    home_score=10,
    away_sog=99,
    home_sog=99,
    period=5,
    period_type="OT",  # "2OT"
    clock_seconds=754,  # 12:34
    clock_running=False,
    situation=Situation(pp_team="NYI", pp_seconds=119, en_team="PHI"),
)
WORST_SMALL_INT = dataclasses.replace(
    WORST_SMALL_LIVE, period=2, period_type="REG", in_intermission=True
)


@pytest.mark.parametrize(
    "game", [WORST_SMALL_LIVE, WORST_SMALL_INT], ids=["2ot", "2nd-int"]
)
@pytest.mark.parametrize("stale", [False, True])
def test_band_board_worst_case_clearance(smallsign, tz, monkeypatch, game, stale):
    calls = _spy_texts(monkeypatch, smallsign, game, tz, stale=stale)
    texts = [c[0] for c in calls]
    assert "10" in texts and "99" in texts
    if not game.in_intermission:
        assert "EN" in texts and any(t.startswith("PP ") for t in texts)
    if stale:
        assert texts.count("STALE") == 2
    _assert_band_clearance(calls, smallsign.width)


def test_band_board_typical_live_clearance(smallsign, tz, monkeypatch):
    calls = _spy_texts(monkeypatch, smallsign, LIVE, tz)
    _assert_band_clearance(calls, smallsign.width)


def test_band_board_intermission_hides_pp_and_en(smallsign, tz, monkeypatch):
    calls = _spy_texts(monkeypatch, smallsign, WORST_SMALL_INT, tz)
    texts = [c[0] for c in calls]
    assert "EN" not in texts and not any(t.startswith("PP") for t in texts)
