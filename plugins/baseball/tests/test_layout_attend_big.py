"""tests/test_layout_attend_big.py — hires text asserted by EXTENT/region
only (never exact freetype pins), same convention as the sibling layout
test files (test_layout_statcast_big.py / test_layout_promo_card.py).

Region bands below were adjusted from the task-4 brief's first draft to the
rendered extent (never pinned to exact rows) — see the module comments at
each adjusted assertion.
"""

from led_ticker.plugin import HeadlessBackend, ScaledCanvas

from led_ticker_baseball.attendance import AttendanceGame, CrowdRecord
from led_ticker_baseball.layouts.attend_big import render_attend_big


def _bigsign():
    real = HeadlessBackend(256, 64).create_canvas()
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
    canvas, real = _bigsign()
    render_attend_big(canvas, _team(), 1.0)
    assert _lit_in(real, 4, 80, 0, 10)  # ATTENDANCE label
    assert _lit_in(real, 4, 140, 10, 38)  # paid number
    assert _lit_in(real, 4, 252, 48, 58)  # capacity bar band


def test_team_cap_right_anchored():
    canvas, real = _bigsign()
    render_attend_big(canvas, _team(), 1.0)
    # "56,000 CAP" ends at x=252 (right margin); something lit near the
    # right edge on the label row
    assert any(x >= 210 for (x, y) in _lit(real) if 38 <= y <= 48)


def test_team_max_width_attendance_columns_stay_on_panel():
    """Positioning tripwire: the widest realistic crowd must not push the
    flowed % FULL / VS AVG columns off the 256 panel."""
    canvas, real = _bigsign()
    render_attend_big(canvas, _team(paid=56000, capacity=56000, avg=39000), 1.0)
    assert not any(x >= 256 for (x, _y) in _lit(real))  # nothing clips the edge


def test_team_long_venue_never_overlaps_bar():
    """Positioning tripwire: a long venue name is fit-belted; no venue pixel
    may land in the bar band (y49-57) or past the right edge."""
    canvas, real = _bigsign()
    render_attend_big(
        canvas, _team(venue="Great American Ball Park Extended Name"), 1.0
    )
    assert not any(x >= 256 for (x, _y) in _lit(real))


def test_team_no_avg_omits_tick(monkeypatch):
    """avg=None (early season) -> no season-avg tick drawn; the SAME record
    WITH avg present DOES draw the tick. The pair proves this test can tell
    tick-present from tick-absent.

    GOTCHA (task-4/5 brief): `real._pixels` values are plain (r, g, b) tuples
    and a Color is NEVER == a tuple in the stub, so the old `v == pal.IDENT`
    comparison was unconditionally False — the test passed whether or not the
    "no tick" behavior worked. Compare against the tuple form. The tick bleeds
    1px above/below the bar (rows 47-59 for a y=49,h=9 bar)."""
    from led_ticker_baseball import _palette as pal

    ident = (pal.IDENT.red, pal.IDENT.green, pal.IDENT.blue)

    canvas, real = _bigsign()
    render_attend_big(canvas, _team(avg=None), 1.0)
    no_tick = [
        (x, y) for (x, y), v in real._pixels.items() if v == ident and 47 <= y <= 59
    ]
    assert no_tick == []  # avg=None -> tick absent

    canvas2, real2 = _bigsign()
    render_attend_big(canvas2, _team(avg=39442), 1.0)
    with_tick = [
        (x, y) for (x, y), v in real2._pixels.items() if v == ident and 47 <= y <= 59
    ]
    assert with_tick  # avg present -> tick IS drawn (proves discrimination)


def test_bar_animates_with_progress():
    canvas0, real0 = _bigsign()
    canvas1, real1 = _bigsign()
    render_attend_big(canvas0, _team(), 0.1)
    render_attend_big(canvas1, _team(), 1.0)

    def fill_cols(real):
        from led_ticker_baseball import _palette as pal

        # GOTCHA (task-4 brief): `real._pixels` values are plain (r, g, b)
        # tuples, and a Color is never == a tuple in the stub — comparing
        # `v != track` with `track` left as a Color would make every pixel
        # (including the untouched track background) count as "not track",
        # making this assertion vacuously true at any progress. Convert to
        # the tuple form before comparing.
        c = pal.dim(pal.LABEL, 0.32)
        track = (c.red, c.green, c.blue)
        return {
            x
            for (x, y), v in real._pixels.items()
            if 49 <= y <= 56 and v != track and v != (0, 0, 0)
        }

    assert len(fill_cols(real0)) < len(fill_cols(real1))  # bar grew


def test_league_regions_present():
    canvas, real = _bigsign()
    rec = CrowdRecord(
        value=45123,
        venue="Dodger Stadium",
        home_abbr="LAD",
        is_pct=False,
        fill_frac=0.9,
        attendance=45123,
        capacity=50000,
    )
    render_attend_big(canvas, rec, 1.0, label="BIGGEST CROWD")
    assert _lit_in(real, 4, 130, 0, 10)  # label
    assert _lit_in(real, 4, 160, 12, 40)  # big value
    assert _lit_in(real, 4, 252, 50, 60)  # fill bar band


def test_team_venue_never_clips_bottom_edge():
    """The venue name sits just below the bar; at size 8 its cap-top glyph
    must fit within the 64-row panel (rows 0-63). A y-target too low clips
    the bottom of every letter off-canvas (the x-based tripwires can't catch
    a vertical clip). Uses a long venue so the row is densely populated.

    Two assertions, because the naive "no pixel at y>=64" check is trivially
    true either way: core's hi-res rasterizer bounds-checks each row against
    the panel height and silently drops anything >= panel_h before it ever
    reaches `real.SetPixel` — so an out-of-canvas glyph row never shows up
    as an out-of-bounds pixel, it just vanishes. The actual visible defect
    is a SHORTENED glyph (missing its bottom ~2 of 6 rows, and shifted low
    to start with): at the buggy y-target, the on-canvas venue rows are only
    60-63 (span 3); at the correct one they're the full 58-63 (span 5). The
    second assertion is the one that actually fails at the bug and passes
    at the fix — confirmed empirically (see task-4 report)."""
    canvas, real = _bigsign()
    render_attend_big(canvas, _team(venue="Great American Ball Park"), 1.0)
    lit = {xy for xy, v in real._pixels.items() if v != (0, 0, 0)}
    venue_rows = {y for (_x, y) in lit if y >= 58}
    assert lit and not any(y >= 64 for (_x, y) in lit)
    assert venue_rows and max(venue_rows) - min(venue_rows) >= 5


def test_never_raises_on_empty_team():
    canvas, real = _bigsign()
    render_attend_big(
        canvas,
        AttendanceGame(paid=None, capacity=0, avg=None, venue="", home_abbr=""),
        1.0,
    )
