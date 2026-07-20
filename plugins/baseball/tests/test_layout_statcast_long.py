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
