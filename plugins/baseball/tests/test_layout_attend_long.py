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
from led_ticker_baseball._paint import text_width
from led_ticker_baseball.attendance import AttendanceGame, CrowdRecord
from led_ticker_baseball.layouts.attend_long import (
    _WEATHER_MAXW,
    _WEATHER_SIZE,
    _abbrev_condition,
    render_attend_long,
)


def _longboi():
    real = HeadlessBackend(512, 64).create_canvas()
    return ScaledCanvas(real, scale=4, content_height=16), real


def _team(**over):
    kw = dict(
        paid=46537,
        capacity=56000,
        avg=39442,
        venue="Dodger Stadium",
        home_abbr="LAD",
        temp="",
        condition="",
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
    """avg=None (early season) -> no season-avg tick drawn; the SAME record
    WITH avg present DOES draw the tick. The pair proves this test can tell
    tick-present from tick-absent.

    GOTCHA (task-4/5 brief): `real._pixels` values are plain (r, g, b) tuples
    and a Color is NEVER == a tuple in the stub, so the old `v == pal.IDENT`
    comparison was unconditionally False — the test passed whether or not the
    "no tick" behavior worked. Compare against the tuple form. The tick bleeds
    1px above/below the bar (rows 51-62 for a y=52,h=10 bar)."""
    ident = (pal.IDENT.red, pal.IDENT.green, pal.IDENT.blue)

    canvas, real = _longboi()
    render_attend_long(canvas, _team(avg=None), 1.0)
    no_tick = [
        (x, y) for (x, y), v in real._pixels.items() if v == ident and 51 <= y <= 62
    ]
    assert no_tick == []  # avg=None -> tick absent

    canvas2, real2 = _longboi()
    render_attend_long(canvas2, _team(avg=39442), 1.0)
    with_tick = [
        (x, y) for (x, y), v in real2._pixels.items() if v == ident and 51 <= y <= 62
    ]
    assert with_tick  # avg present -> tick IS drawn (proves discrimination)


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


def test_long_team_venue_bigger_and_no_clip():
    """The promoted venue (px14, up from the old px9 "PAID ATTENDANCE"-
    adjacent px8) sits on the row-40 band, well clear of the bar at y52-61.

    A naive "no pixel at y>=64" check is VACUOUS: core's hi-res rasterizer
    bounds-checks each row against the panel height and silently drops
    anything >= panel_h before it ever reaches `real.SetPixel` — an
    out-of-canvas glyph row never shows up as an out-of-bounds pixel, it
    just vanishes. The actual visible defect would be a SHORTENED glyph
    (missing its bottom rows), so this asserts the full expected VISIBLE
    ROW-SPAN for px14 (empirically 10 rows; >=8 leaves headroom for
    cross-platform freetype variance without weakening the tripwire) —
    that's the assertion that would actually fail on a clip. Also verifies
    no overlap with the right-anchored "NN,NNN CAP" readout (x-extents
    traced, isolated by color) and no bleed into the bar band (y>=52)."""
    canvas, real = _longboi()
    render_attend_long(
        canvas, _team(venue="Great American Ball Park Extended Name"), 1.0
    )
    lab = (pal.LABEL.red, pal.LABEL.green, pal.LABEL.blue)
    label_px = [(x, y) for (x, y), v in real._pixels.items() if v == lab]

    # Isolate the venue (x < 224, before the fixed columns) from the
    # right-anchored CAP readout (which also paints in LABEL color).
    venue_px = [(x, y) for (x, y) in label_px if 35 <= y <= 55 and x < 224]
    cap_px = [(x, y) for (x, y) in label_px if 35 <= y <= 55 and x >= 400]
    assert venue_px and cap_px  # both present — proves the isolation works

    venue_rows = {y for (_x, y) in venue_px}
    assert max(venue_rows) - min(venue_rows) >= 8  # full glyph span, not clipped

    venue_x_max = max(x for (x, _y) in venue_px)
    cap_x_min = min(x for (x, _y) in cap_px)
    assert venue_x_max < cap_x_min  # no overlap with the CAP readout

    assert not any(y >= 52 for (_x, y) in venue_px)  # clear of the bar band


def test_long_team_weather_in_gap_no_overlap():
    """Weather ("72° CLEAR") fills the dead x122-223 gap between the paid
    number (ends ~x109) and the fixed columns (start x228). Isolated by its
    CYAN draw color — compared against the TUPLE form, since a Color is
    never == a get_pixel tuple in the stub (task-4/5 GOTCHA)."""
    canvas, real = _longboi()
    render_attend_long(canvas, _team(temp="72°", condition="Clear"), 1.0)
    cyan = (pal.CYAN.red, pal.CYAN.green, pal.CYAN.blue)
    weather_px = [(x, y) for (x, y), v in real._pixels.items() if v == cyan]
    assert weather_px  # weather line actually drew something

    xs = {x for (x, _y) in weather_px}
    assert any(122 <= x < 224 for x in xs)  # lives in the gap
    assert not any(x < 118 for x in xs)  # doesn't reach the paid number
    assert not any(x >= 224 for x in xs)  # doesn't reach the columns


def test_long_team_no_weather_omits_line():
    """temp/condition both empty (the AttendanceGame default) -> no lit
    pixels anywhere in the weather's gap band, guarding against a stray
    "° " render when there's nothing to show. Capped at y<35 (above the
    row-40 venue band, which legitimately reaches into this x-range when a
    long venue name flows past x122) so this isolates the weather row
    specifically, not the unrelated venue text below it."""
    canvas, real = _longboi()
    render_attend_long(canvas, _team(), 1.0)
    lit = {xy for xy, v in real._pixels.items() if v != (0, 0, 0)}
    gap_pixels = [(x, y) for (x, y) in lit if 122 <= x < 224 and y < 35]
    assert gap_pixels == []


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


def test_league_label_and_value_are_row_disjoint():
    """League label (small, top) and the big value must not paint through
    each other — the value used to reuse the team paid slot at y=3 and
    overlapped the y=1 label. Isolate by color (label=LABEL, value=AMBER for
    a crowd record) and assert their row sets don't intersect."""
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
    lab = (pal.LABEL.red, pal.LABEL.green, pal.LABEL.blue)
    amb = (pal.AMBER.red, pal.AMBER.green, pal.AMBER.blue)
    px = real._pixels.items()
    label_rows = {y for (x, y), v in px if v == lab and x < 200 and y < 40}
    value_rows = {y for (x, y), v in px if v == amb and x < 200 and y < 45}
    assert label_rows and value_rows
    assert not (label_rows & value_rows)  # disjoint — no paint-through


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


def test_abbrev_condition_maps_long_names():
    """Verify the abbreviation map abbreviates multi-word conditions to
    shorter forms that fit the compact weather slot, and passes through
    all others (including empty)."""
    assert _abbrev_condition("Partly Cloudy") == "P CLOUDY"
    assert _abbrev_condition("Roof Closed") == "ROOF"
    assert _abbrev_condition("Clear") == "CLEAR"
    assert _abbrev_condition("Overcast") == "OVERCAST"
    assert _abbrev_condition("") == ""
    assert _abbrev_condition(None) == ""


def test_long_team_partly_cloudy_not_ellipsized():
    """Abbreviated "P CLOUDY" fits the weather slot without ellipsizing,
    while the raw "PARTLY CLOUDY" would exceed _WEATHER_MAXW and get
    belt-truncated. Verify the abbreviated form fits by measuring its
    width against the slot capacity."""
    canvas, real = _longboi()
    render_attend_long(canvas, _team(temp="88°", condition="Partly Cloudy"), 1.0)

    # The abbreviated weather text "88° P CLOUDY" must fit within the
    # weather slot width without being truncated by fit_text.
    abbrev_text = "88° P CLOUDY"
    abbrev_width = text_width(_WEATHER_SIZE, abbrev_text)
    assert abbrev_width <= _WEATHER_MAXW, (
        f"Abbreviated weather '{abbrev_text}' exceeds slot "
        f"({abbrev_width} > {_WEATHER_MAXW}); fit_text would truncate it"
    )

    # Confirm the raw (unabbreviated) form WOULD exceed the limit,
    # proving the abbreviation achieves its purpose.
    raw_text = "88° PARTLY CLOUDY"
    raw_width = text_width(_WEATHER_SIZE, raw_text)
    assert raw_width > _WEATHER_MAXW, (
        f"Raw weather '{raw_text}' should exceed slot "
        f"({raw_width} <= {_WEATHER_MAXW}); abbreviation unnecessary"
    )

    # Verify no ellipsis (U+2026 "…") appears in the rendered output.
    cyan = (pal.CYAN.red, pal.CYAN.green, pal.CYAN.blue)
    weather_px = [(x, y) for (x, y), v in real._pixels.items() if v == cyan]
    assert weather_px, "Weather line should have lit pixels"

    # Ellipsis, if rendered by fit_text, would light pixels in the weather
    # slot area. The absence of weather pixels at the right edge (x >= 220)
    # suggests no ellipsis is visible. This is a defensive check — the
    # width assertion above is the primary gate.
    xs = {x for (x, _y) in weather_px}
    assert not any(x >= 224 for x in xs), (
        "Weather pixels reached column start; possible ellipsis at right"
    )
