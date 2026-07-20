"""tests/test_layout_statcast_big.py — hires text asserted by EXTENT/region
only (never exact freetype pins), same convention as the sibling layout
test files (test_layout_promo_card.py / test_layout_standings_board.py).

`render_statcast_big`'s public signature keeps `y_offset`/`story_index`/
`story_total` keyword-only (task-5 brief interface, binding for Task 7), so
calls below pass `y_offset=` by keyword rather than positionally.
"""

from led_ticker.plugin import HeadlessBackend, ScaledCanvas

from led_ticker_baseball.layouts.statcast_big import render_statcast_big
from led_ticker_baseball.statcast import StatRecord


def _bigsign():
    real = HeadlessBackend(256, 64).create_canvas()
    return ScaledCanvas(real, scale=4, content_height=16), real


def _rec():
    return StatRecord(
        value=451,
        person_id=1,
        team_abbr="PHI",
        exit_velo=114.2,
        launch_angle=28,
        distance=451,
        bb_type="fly_ball",
        result="HOME RUN",
        pitch_velo=94.1,
        pitch_name="Slider",
    )


def _lit_in(real, x0, x1, y0, y1):
    return any(
        real.get_pixel(x, y) != (0, 0, 0) for x in range(x0, x1) for y in range(y0, y1)
    )


def test_big_regions_present():
    canvas, real = _bigsign()
    render_statcast_big(canvas, _rec(), "RAMIREZ")
    assert _lit_in(real, 4, 80, 0, 10)  # STATCAST label top-left
    assert _lit_in(real, 4, 200, 10, 28)  # player name
    assert _lit_in(real, 4, 120, 24, 52)  # big exit-velo headline
    assert _lit_in(real, 4, 252, 52, 64)  # bottom la/dist/pitch row


def test_big_never_raises_on_empty_context():
    canvas, real = _bigsign()
    render_statcast_big(canvas, StatRecord(value=0, person_id=0, team_abbr=""), "")


def test_big_y_offset_shifts_content():
    canvas, real = _bigsign()
    render_statcast_big(canvas, _rec(), "RAMIREZ")
    rows = {y for x, y in real._pixels if real.get_pixel(x, y) != (0, 0, 0)}
    canvas2, real2 = _bigsign()
    render_statcast_big(canvas2, _rec(), "RAMIREZ", y_offset=8)
    rows2 = {y for x, y in real2._pixels if real2.get_pixel(x, y) != (0, 0, 0)}
    assert min(rows2) - min(rows) == 32
