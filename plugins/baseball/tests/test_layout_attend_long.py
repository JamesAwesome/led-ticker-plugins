"""tests/test_layout_attend_long.py — hires text asserted by EXTENT/region
only (never exact freetype pins), same convention as the sibling layout
test files (test_layout_attend_big.py / test_layout_statcast_long.py).

Unlike the big card, the long card's "% FULL"/"VS AVG" columns sit at FIXED
x-origins (`cx = 228 + i*96`) — no flow-collision risk from a wide paid
number (that's the big card's own tripwire; see
`test_long_fixed_columns_do_not_flow` below for the long-card equivalent
guarantee, phrased the other way around: fixed, not flowed).
"""

from led_ticker.plugin import HeadlessBackend, ScaledCanvas

from led_ticker_baseball import _palette as pal
from led_ticker_baseball.attendance import AttendanceGame, CrowdRecord
from led_ticker_baseball.layouts.attend_long import render_attend_long


def _longboi():
    real = HeadlessBackend(512, 64).create_canvas()
    return ScaledCanvas(real, scale=4, content_height=16), real


def _team(**over):
    kw = dict(
        paid=46537, capacity=56000, avg=39442, venue="Dodger Stadium", home_abbr="LAD"
    )
    kw.update(over)
    return AttendanceGame(**kw)


def _lit_in(real, x0, x1, y0, y1):
    return any(
        real.get_pixel(x, y) != (0, 0, 0) for x in range(x0, x1) for y in range(y0, y1)
    )


def _lit(real):
    return {xy for xy, v in real._pixels.items() if v != (0, 0, 0)}


def test_team_regions_present():
    canvas, real = _longboi()
    render_attend_long(canvas, _team(), 1.0)
    assert _lit_in(real, 6, 200, 0, 34)  # paid number (big amber readout)
    assert _lit_in(real, 228, 420, 0, 40)  # fixed % FULL / VS AVG columns
    assert _lit_in(real, 6, 506, 52, 62)  # capacity bar band


def test_team_cap_right_anchored():
    canvas, real = _longboi()
    render_attend_long(canvas, _team(), 1.0)
    # "56,000 CAP" right-anchored to x=506; something lit near the right
    # edge on the row-40 label band
    assert any(x >= 460 for (x, y) in _lit(real) if 38 <= y <= 49)


def test_long_fixed_columns_do_not_flow():
    """Long card columns are at fixed cx=228/324 — a wide attendance number
    must not shift them (unlike the big card). Rendering min and max crowds
    lights the same column x-origins."""
    canvas_a, real_a = _longboi()
    canvas_b, real_b = _longboi()
    render_attend_long(canvas_a, _team(paid=15000), 1.0)
    render_attend_long(canvas_b, _team(paid=56000), 1.0)

    def band(real):
        return {x for (x, y) in _lit(real) if 4 <= y <= 24 and x >= 228}

    # the % FULL / VS AVG columns occupy the same x region regardless of
    # paid width
    assert min(band(real_a)) == min(band(real_b))


def test_long_venue_belt_and_edge():
    canvas, real = _longboi()
    render_attend_long(
        canvas, _team(venue="Guaranteed Rate Field At The Ballpark"), 1.0
    )
    assert not any(x >= 512 for (x, _y) in _lit(real))


def test_team_no_avg_omits_tick():
    """avg=None (early season) -> no season-avg tick drawn."""
    canvas, real = _longboi()
    render_attend_long(canvas, _team(avg=None), 1.0)
    tick = [
        (x, y) for (x, y), v in real._pixels.items() if v == pal.IDENT and 51 <= y <= 63
    ]
    assert tick == []


def test_bar_animates_with_progress():
    canvas0, real0 = _longboi()
    canvas1, real1 = _longboi()
    render_attend_long(canvas0, _team(), 0.1)
    render_attend_long(canvas1, _team(), 1.0)

    def fill_cols(real):
        # GOTCHA (task-4/5 brief): `real._pixels` values are plain (r, g, b)
        # tuples, and a Color is never == a tuple in the stub — compare
        # against the tuple form, not the Color object.
        c = pal.dim(pal.LABEL, 0.32)
        track = (c.red, c.green, c.blue)
        return {
            x
            for (x, y), v in real._pixels.items()
            if 52 <= y <= 61 and v != track and v != (0, 0, 0)
        }

    assert len(fill_cols(real0)) < len(fill_cols(real1))  # bar grew


def test_team_venue_never_clips_vertically():
    """The venue name sits on the row-40 band (well clear of the bar at
    y52-61); verify its cap-top glyph never clips the panel bottom (rows
    0-63). Uses a long venue so the row is densely populated.

    Two assertions, because the naive "no pixel at y>=64" check is
    trivially true either way: core's hi-res rasterizer bounds-checks each
    row against the panel height and silently drops anything >= panel_h
    before it ever reaches `real.SetPixel` — an out-of-canvas glyph row
    never shows up as an out-of-bounds pixel, it just vanishes. The actual
    visible defect would be a SHORTENED glyph (missing its bottom rows);
    the second assertion is the one that would actually fail on a clip."""
    canvas, real = _longboi()
    render_attend_long(
        canvas, _team(venue="Great American Ball Park Extended Name"), 1.0
    )
    lit = {xy for xy, v in real._pixels.items() if v != (0, 0, 0)}
    venue_rows = {y for (_x, y) in lit if 35 <= y <= 49}
    assert lit and not any(y >= 64 for (_x, y) in lit)
    assert venue_rows and max(venue_rows) - min(venue_rows) >= 4


def test_long_league_regions_present():
    canvas, real = _longboi()
    rec = CrowdRecord(
        value=45123,
        venue="Dodger Stadium",
        home_abbr="LAD",
        is_pct=False,
        fill_frac=0.9,
        attendance=45123,
        capacity=50000,
    )
    render_attend_long(canvas, rec, 1.0, label="BIGGEST CROWD")
    assert _lit_in(real, 6, 200, 0, 10)  # label
    assert _lit_in(real, 6, 250, 0, 34)  # big value
    assert _lit_in(real, 6, 506, 52, 62)  # fill bar band


def test_never_raises_on_empty_team():
    canvas, real = _longboi()
    render_attend_long(
        canvas,
        AttendanceGame(paid=None, capacity=0, avg=None, venue="", home_abbr=""),
        1.0,
    )


def test_never_raises_on_empty_league():
    canvas, real = _longboi()
    render_attend_long(
        canvas,
        CrowdRecord(value=0, venue="", home_abbr="", is_pct=False),
        1.0,
        label="",
    )
