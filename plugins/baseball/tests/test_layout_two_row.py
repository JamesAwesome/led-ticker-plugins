"""tests/test_layout_two_row.py — hires text asserted by EXTENT/regions
only (never exact freetype pins). GameInfo fixtures mirror the audit
branch's WORST case.

HeadlessBackend takes (width, height) positionally (see
led_ticker/backends/headless.py) — there is no rows/cols/chain_length kwarg
surface (that's an RgbMatrixBackend shape). HeadlessCanvas has no
iter_coords()/iter_pixels(); its supported read surface is get_pixel(x, y)
plus the `_pixels` dict it serializes from — sibling plugin tests
(test_paint.py, test_primitives.py) already reach into `_pixels` directly
for "any lit pixel" checks, so we follow that precedent here.
"""

from zoneinfo import ZoneInfo

from led_ticker.plugin import HeadlessBackend, ScaledCanvas

from led_ticker_baseball._models import GameInfo
from led_ticker_baseball.layouts.two_row import render_two_row

TZ = ZoneInfo("America/New_York")


def _bigsign():
    real = HeadlessBackend(256, 64).create_canvas()
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
        outs=1,
        on_first=True,
        on_second=False,
        on_third=False,
    )
    kw.update(over)
    return GameInfo(**kw)


def _lit_coords(real):
    return {xy for xy, v in real._pixels.items() if v != (0, 0, 0)}


def _lit_rows(real):
    return {y for x, y in _lit_coords(real)}


def _lit_in(real, x0, x1, y0, y1):
    return any(
        real.get_pixel(x, y) != (0, 0, 0) for x in range(x0, x1) for y in range(y0, y1)
    )


def test_live_card_has_top_band_divider_and_bottom_band():
    canvas, real = _bigsign()
    render_two_row(canvas, _live_game(), TZ)
    rows = _lit_rows(real)
    assert rows & set(range(4, 28))  # top band content
    assert 31 in rows  # dotted divider at y31
    assert rows & set(range(35, 58))  # bottom band content


def test_live_card_bases_cluster_and_count_right_anchored():
    canvas, real = _bigsign()
    render_two_row(canvas, _live_game(on_second=True), TZ)
    # bases cluster region (after the inning text, left third of bottom band)
    assert _lit_in(real, 20, 80, 33, 58)
    # count is right-anchored at x=250
    assert _lit_in(real, 200, 251, 35, 56)
    assert not _lit_in(real, 251, 256, 35, 56)


def test_final_card_centers_FINAL_and_no_bases():
    canvas, real = _bigsign()
    render_two_row(canvas, _live_game(state="final", inning=None), TZ)
    assert _lit_in(real, 90, 166, 37, 58)  # centered FINAL region
    assert not _lit_in(real, 0, 40, 33, 58)  # no inning triangle at left


def test_y_offset_shifts_everything():
    canvas, real = _bigsign()
    render_two_row(canvas, _live_game(), TZ, y_offset=8)
    canvas2, real2 = _bigsign()
    render_two_row(canvas2, _live_game(), TZ)
    # y_offset arrives in LOGICAL units; the widget contract multiplies by
    # scale (4) before applying it to physical coords — confirmed against
    # flight's hero_layout.py (`dy = y_offset * scale`).
    assert min(_lit_rows(real)) - min(_lit_rows(real2)) == 32


def test_never_raises_on_missing_fields():
    canvas, real = _bigsign()
    g = _live_game(balls=None, strikes=None, outs=None, inning=None)
    render_two_row(canvas, g, TZ)  # must not raise (breaker contract)


def test_preview_state_centers_matchup_and_time():
    canvas, real = _bigsign()
    g = _live_game(state="preview", inning=None, away_score=None, home_score=None)
    render_two_row(canvas, g, TZ)
    rows = _lit_rows(real)
    assert rows & set(range(5, 25))  # matchup line
    assert rows & set(range(38, 56))  # start-time / TBD line


def test_postponed_state_uses_postpone_tag_label():
    canvas, real = _bigsign()
    g = _live_game(state="postponed", inning=None, postpone_tag="PPD")
    render_two_row(canvas, g, TZ)
    rows = _lit_rows(real)
    assert rows & set(range(38, 56))  # tag label line lit


def test_paging_dots_drawn_when_story_total_gt_1():
    canvas, real = _bigsign()
    render_two_row(canvas, _live_game(), TZ, story_index=0, story_total=3)
    # paging dots reserved region: near bottom-right (x = 256 - 3*8 - 4 = 228)
    assert _lit_in(real, 220, 256, 58, 64)


def test_no_paging_dots_when_story_total_1():
    canvas, real = _bigsign()
    render_two_row(canvas, _live_game(), TZ, story_index=0, story_total=1)
    assert not _lit_in(real, 220, 256, 58, 64)
