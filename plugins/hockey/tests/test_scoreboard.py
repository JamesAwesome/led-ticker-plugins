from led_ticker.plugin import make_color

from led_ticker_hockey import _palette as pal
from led_ticker_hockey._models import build_demo_games
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


def test_band_board_bg_color(smallsign, tz):
    _board(build_demo_games(NOW)[0], tz, bg_color=make_color(1, 2, 3)).draw(smallsign)
    assert smallsign._pixels[(100, 0)] == (1, 2, 3)


def test_ticker_message_uses_segments(tz):
    from led_ticker.plugin import FONT_DEFAULT

    msg = build_ticker_message(build_demo_games(NOW)[2], NOW, tz, font=FONT_DEFAULT)
    assert "".join(t for t, _ in msg.segments) == "PHI 3 · NYI 2 · FINAL/OT"
