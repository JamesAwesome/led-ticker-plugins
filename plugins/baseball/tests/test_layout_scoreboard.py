"""tests/test_layout_scoreboard.py — hires text asserted by EXTENT/regions
only (never exact freetype pins). GameInfo fixtures mirror the two_row
suite's conventions.

HeadlessBackend takes (width, height) positionally (see
led_ticker/backends/headless.py) — there is no rows/cols/chain_length kwarg
surface (that's an RgbMatrixBackend shape).
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from led_ticker.plugin import HeadlessBackend, ScaledCanvas

from led_ticker_baseball._models import GameInfo
from led_ticker_baseball.layouts.scoreboard import render_scoreboard

TZ = ZoneInfo("America/New_York")


def _longboi():
    real = HeadlessBackend(512, 64).create_canvas()
    return ScaledCanvas(real, scale=4, content_height=16), real


def _live_game(**over):
    kw = dict(
        away_abbr="TB",
        home_abbr="BOS",
        away_score=0,
        home_score=10,
        state="live",
        inning="▼8",
        balls=1,
        strikes=2,
        outs=2,
        on_first=True,
        on_second=True,
        on_third=False,
    )
    kw.update(over)
    return GameInfo(**kw)


def _lit_coords(real):
    return {xy for xy, v in real._pixels.items() if v != (0, 0, 0)}


def _lit_in(real, x0, x1, y0, y1):
    return any(
        real.get_pixel(x, y) != (0, 0, 0) for x in range(x0, x1) for y in range(y0, y1)
    )


def test_live_thirds_left_name_score_right_name_score_center_cluster():
    canvas, real = _longboi()
    render_scoreboard(canvas, _live_game(), TZ)
    assert _lit_in(real, 8, 160, 6, 30)  # away name (px20, top-left)
    assert _lit_in(real, 8, 120, 28, 62)  # away score (px34, bottom-left)
    assert _lit_in(real, 380, 504, 6, 30)  # home name right
    assert _lit_in(real, 176, 310, 5, 30)  # inning + outs pips
    assert _lit_in(real, 176, 300, 32, 52)  # B/S count row
    assert _lit_in(real, 315, 365, 12, 44)  # bases diamond cluster


def test_outs_pips_two_filled_one_empty():
    canvas, real = _longboi()
    render_scoreboard(canvas, _live_game(outs=2), TZ)
    # pips are red discs; the third (empty) is a dim LABEL ring -> its center is dark
    # centers: ix advances past inning text; assert at least two red-ish pixels
    reds = sum(
        1
        for x in range(176, 320)
        for y in range(8, 22)
        if real.get_pixel(x, y)[0] > 150 and real.get_pixel(x, y)[1] < 80
    )
    assert reds >= 2


def test_final_centers_FINAL():
    canvas, real = _longboi()
    render_scoreboard(canvas, _live_game(state="final", inning=None), TZ)
    assert _lit_in(real, 200, 312, 20, 48)


def test_never_raises_on_sparse_game():
    canvas, real = _longboi()
    render_scoreboard(canvas, _live_game(balls=None, outs=None, inning=None), TZ)


def test_preview_state_centers_matchup_and_time():
    canvas, real = _longboi()
    g = _live_game(state="preview", inning=None, away_score=None, home_score=None)
    render_scoreboard(canvas, g, TZ)
    assert _lit_in(real, 100, 412, 6, 30)  # matchup line
    assert _lit_in(real, 200, 312, 40, 62)  # start-time / TBD line


def test_postponed_state_uses_postpone_tag_label():
    canvas, real = _longboi()
    g = _live_game(state="postponed", inning=None, postpone_tag="PPD")
    render_scoreboard(canvas, g, TZ)
    assert _lit_in(real, 200, 312, 40, 62)  # tag label line lit


def test_preview_with_start_time_renders_time_not_ppd():
    """Regression: GameInfo.postpone_tag DEFAULTS to "PPD" (and the parser
    sets it for every game), so a truthiness gate on the tag made every
    ordinary preview render "PPD" instead of its start time. The label
    branch must gate on state == "postponed", not tag truthiness.

    Without exact-pinning freetype: render a preview and a postponed game
    with identical other fields and assert their lit-pixel sets DIFFER —
    identical sets means both rendered the same label (the bug)."""
    start = datetime(2026, 7, 17, 19, 10, tzinfo=TZ)
    common = dict(state="preview", inning=None, away_score=None, home_score=None)
    canvas_p, real_p = _longboi()
    render_scoreboard(canvas_p, _live_game(**common, start_time=start), TZ)
    canvas_x, real_x = _longboi()
    render_scoreboard(
        canvas_x,
        _live_game(**{**common, "state": "postponed"}, start_time=start),
        TZ,
    )
    assert _lit_coords(real_p) != _lit_coords(real_x)


def test_preview_start_time_differs_from_tbd():
    """A preview WITH a start_time must render differently from one
    without (which falls back to "TBD")."""
    common = dict(state="preview", inning=None, away_score=None, home_score=None)
    canvas_t, real_t = _longboi()
    render_scoreboard(
        canvas_t,
        _live_game(**common, start_time=datetime(2026, 7, 17, 19, 10, tzinfo=TZ)),
        TZ,
    )
    canvas_n, real_n = _longboi()
    render_scoreboard(canvas_n, _live_game(**common, start_time=None), TZ)
    assert _lit_coords(real_t) != _lit_coords(real_n)


def test_y_offset_shifts_everything():
    canvas, real = _longboi()
    render_scoreboard(canvas, _live_game(), TZ, y_offset=8)
    canvas2, real2 = _longboi()
    render_scoreboard(canvas2, _live_game(), TZ)
    rows = {y for x, y in _lit_coords(real)}
    rows2 = {y for x, y in _lit_coords(real2)}
    assert min(rows) - min(rows2) == 32


def test_paging_dots_drawn_when_story_total_gt_1():
    canvas, real = _longboi()
    # preview state: no score digits reach the bottom-right corner, so the
    # paging-dots region (w - n*8 - 6, h - 10) is unambiguous here — a live
    # game's score glyphs can extend into this same corner (see the
    # "no dots" test below), so region checks against a scored game would
    # be unreliable.
    g = _live_game(state="preview", inning=None, away_score=None, home_score=None)
    render_scoreboard(canvas, g, TZ, story_index=0, story_total=3)
    assert _lit_in(real, 470, 512, 54, 64)


def test_no_paging_dots_when_story_total_1():
    canvas, real = _longboi()
    g = _live_game(state="preview", inning=None, away_score=None, home_score=None)
    render_scoreboard(canvas, g, TZ, story_index=0, story_total=1)
    assert not _lit_in(real, 470, 512, 54, 64)
