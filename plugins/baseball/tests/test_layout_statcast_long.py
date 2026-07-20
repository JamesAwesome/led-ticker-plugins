"""tests/test_layout_statcast_long.py — hires text asserted by EXTENT/region
only (never exact freetype pins), same convention as the sibling layout
test files (test_layout_statcast_big.py / test_layout_promo_card.py).

The longboi (512px) statcast hero card is the only layout with the
animated trajectory panel (`trajectory.py`); the pitch-record branch below
is load-bearing — it must never draw the magenta arc path.
"""

from led_ticker.plugin import HeadlessBackend, ScaledCanvas

from led_ticker_baseball import _palette as pal
from led_ticker_baseball.layouts.statcast_long import render_statcast_long
from led_ticker_baseball.statcast import StatRecord


def _longboi():
    real = HeadlessBackend(512, 64).create_canvas()
    return ScaledCanvas(real, scale=4, content_height=16), real


def _rec(**over):
    kw = dict(
        value=451,
        person_id=1,
        team_abbr="PHI",
        exit_velo=114.2,
        launch_angle=28,
        distance=451,
        bb_type="fly_ball",
        result="HOME RUN",
        pitch_velo=94.1,
        pitch_name="SL",
    )
    kw.update(over)
    return StatRecord(**kw)


def _lit_in(real, x0, x1, y0, y1):
    return any(
        real.get_pixel(x, y) != (0, 0, 0) for x in range(x0, x1) for y in range(y0, y1)
    )


def test_long_regions_present():
    canvas, real = _longboi()
    render_statcast_long(canvas, _rec(), "RAMIREZ", 1.0)
    assert _lit_in(real, 6, 300, 2, 30)  # player name (left block)
    assert _lit_in(real, 6, 200, 30, 46)  # result
    assert _lit_in(real, 176, 400, 4, 52)  # three stat columns
    assert _lit_in(real, 396, 502, 18, 46)  # trajectory panel box


def test_long_pitch_record_draws_no_arc_panel_magenta():
    """A pitch superlative (no launch angle / distance) must not draw the
    magenta trajectory path — the panel folds to pitch emphasis."""
    canvas, real = _longboi()
    pitch_rec = _rec(
        exit_velo=None, launch_angle=None, distance=None, bb_type="", result=""
    )
    render_statcast_long(canvas, pitch_rec, "OKADA", 1.0)
    magenta = (pal.MAGENTA.red, pal.MAGENTA.green, pal.MAGENTA.blue)
    # no magenta path pixels inside the arc box (allow the DISTANCE label
    # which is LABEL-grey, not magenta)
    arc = [
        (x, y)
        for (x, y), v in real._pixels.items()
        if v == magenta and 396 <= x < 502 and 18 <= y < 46
    ]
    assert arc == []


def test_long_progress_advances_arc():
    canvas0, real0 = _longboi()
    canvas1, real1 = _longboi()
    render_statcast_long(canvas0, _rec(), "RAMIREZ", 0.1)
    render_statcast_long(canvas1, _rec(), "RAMIREZ", 1.0)
    lit0 = {xy for xy, v in real0._pixels.items() if v != (0, 0, 0)}
    lit1 = {xy for xy, v in real1._pixels.items() if v != (0, 0, 0)}
    assert len(lit0) < len(lit1)


def test_long_never_raises_on_empty():
    canvas, real = _longboi()
    render_statcast_long(
        canvas, StatRecord(value=0, person_id=0, team_abbr=""), "", 1.0
    )


def _no_label_pixels_past_distance_guard(real):
    """No pal.LABEL-colored pixel at x >= 390 in rows 44-58 — that band is
    the PITCH column's `sec` text (px9, y48); the STATCAST label and column
    labels are also LABEL-colored but sit at x<=360, so x>=390 isolates the
    PITCH sec region from any legitimate LABEL-colored content."""
    label = (pal.LABEL.red, pal.LABEL.green, pal.LABEL.blue)
    return not any(
        v == label and x >= 390 and 44 <= y <= 58 for (x, y), v in real._pixels.items()
    )


def test_long_pitch_sec_never_overlaps_distance():
    """A long pitch name (Knuckle Curve / KC) must not paint its `sec`
    text into the magenta distance readout's column (x >= 396). Pre-fix,
    the full pitch name produced 'KNUCKLE CURVE MPH', which overflows past
    x=396 at px9 and bleeds into the trajectory/distance panel."""
    canvas, real = _longboi()
    rec = _rec(
        pitch_type="KC",
        pitch_name="Knuckle Curve",
        exit_velo=114.2,
        launch_angle=28,
        distance=451,
        bb_type="fly_ball",
        result="HOME RUN",
    )
    render_statcast_long(canvas, rec, "RAMIREZ", 1.0)
    assert _no_label_pixels_past_distance_guard(real)


def test_long_pitch_sec_fits_even_absurd_name():
    """Belt: even with no pitch_type abbreviation and an absurdly long
    pitch_name, fit_text must ellipsize the sec text within the column so
    it never reaches the distance panel guard column."""
    canvas, real = _longboi()
    rec = _rec(
        pitch_type="",
        pitch_name="Absurdly Long Pitch Name That Should Never Happen",
        exit_velo=114.2,
        launch_angle=28,
        distance=451,
        bb_type="fly_ball",
        result="HOME RUN",
    )
    render_statcast_long(canvas, rec, "RAMIREZ", 1.0)
    assert _no_label_pixels_past_distance_guard(real)


def test_long_pitch_panel_name_never_clips_edge():
    """A pitch superlative with a common compound name (4-Seam Fastball)
    must not clip off the panel's right edge. The pitch-superlative
    branch's big panel element must use the short pitch_type abbreviation
    (fit_text-clamped) rather than the full pitch name, which can run past
    the canvas edge (pre-fix: rightmost lit x=511 on a 512px canvas)."""
    canvas, real = _longboi()
    rec = _rec(
        exit_velo=None,
        launch_angle=None,
        distance=None,
        bb_type="",
        result="",
        pitch_velo=99.1,
        pitch_name="4-Seam Fastball",
        pitch_type="FF",
    )
    render_statcast_long(canvas, rec, "OKADA", 1.0)
    lit_xs = [x for (x, _y), v in real._pixels.items() if v != (0, 0, 0)]
    assert lit_xs, "expected some lit pixels"
    assert max(lit_xs) <= 505  # inside the 6px right margin (512 - 6 - 1)


def test_long_pitch_panel_shows_abbreviation():
    """Sanity: the edge-clip fix doesn't blank the panel — the pitch_type
    abbreviation still renders (WIN-colored) in the panel region at the
    big-element rows."""
    canvas, real = _longboi()
    rec = _rec(
        exit_velo=None,
        launch_angle=None,
        distance=None,
        bb_type="",
        result="",
        pitch_velo=99.1,
        pitch_name="4-Seam Fastball",
        pitch_type="FF",
    )
    render_statcast_long(canvas, rec, "OKADA", 1.0)
    win = (pal.WIN.red, pal.WIN.green, pal.WIN.blue)
    assert any(
        v == win and x >= 396 and 20 <= y <= 44 for (x, y), v in real._pixels.items()
    )
