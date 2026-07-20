"""tests/test_layout_statcast_big.py — hires text asserted by EXTENT/region
only (never exact freetype pins), same convention as the sibling layout
test files (test_layout_promo_card.py / test_layout_standings_board.py).

`render_statcast_big`'s public signature keeps `y_offset`/`story_index`/
`story_total` keyword-only (task-5 brief interface, binding for Task 7), so
calls below pass `y_offset=` by keyword rather than positionally. `progress`
is positional (mirrors `render_statcast_long`'s shape) — existing calls pass
`1.0` (at-rest) so they assert the resting card.
"""

from led_ticker.plugin import HeadlessBackend, ScaledCanvas

from led_ticker_baseball.layouts.statcast_big import render_statcast_big
from led_ticker_baseball.statcast import StatRecord

_BOX_X0, _BOX_X1 = 146, 250
_BOX_Y0, _BOX_Y1 = 13, 46
MAGENTA = (255, 80, 255)  # pal.MAGENTA's plain-tuple form (see test_palette.py)
# trajectory.draw_trajectory's trail color: pal.dim(pal.MAGENTA, 0.5) — every
# arc point except the bright leading-edge/ball is painted this dimmed shade.
MAGENTA_TRAIL = (127, 40, 127)


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


def _pitch_rec():
    return StatRecord(
        value=101.4,
        person_id=2,
        team_abbr="NYY",
        exit_velo=None,
        launch_angle=None,
        distance=None,
        bb_type="",
        result="",
        pitch_velo=101.4,
        pitch_name="Fastball",
    )


def _hr_rec():
    """Exact fixture from the task brief: a no-doubter HR ("clears" act in
    trajectory.plan_arc — the ball intentionally lands a hair past the box's
    right edge to sell "over the wall"; see trajectory.py's own comment)."""
    return StatRecord(
        value=451,
        person_id=3,
        team_abbr="PHI",
        exit_velo=112,
        launch_angle=29,
        distance=451,
        bb_type="fly_ball",
        result="HOME RUN",
        pitch_velo=94.1,
        pitch_name="Slider",
    )


def _double_rec():
    """A "fair" (non-HR, non-liner) batted ball — used for the box-
    containment test so the arc's landing point stays inside the box.
    (A HOME RUN's "clears" act intentionally lands the ball a hair past the
    box's right edge — see trajectory.py's `end_x = w` comment — so it's the
    wrong fixture for asserting strict containment.)"""
    return StatRecord(
        value=380,
        person_id=4,
        team_abbr="PHI",
        exit_velo=100.0,
        launch_angle=25,
        distance=380,
        bb_type="fly_ball",
        result="DOUBLE",
        pitch_velo=92.0,
        pitch_name="Slider",
    )


def _lit_in(real, x0, x1, y0, y1):
    return any(
        real.get_pixel(x, y) != (0, 0, 0) for x in range(x0, x1) for y in range(y0, y1)
    )


def _magenta_pixels(real):
    return [(x, y) for x, y in real._pixels if real.get_pixel(x, y) == MAGENTA]


def test_big_regions_present():
    canvas, real = _bigsign()
    render_statcast_big(canvas, _rec(), "RAMIREZ", 1.0)
    assert _lit_in(real, 4, 80, 0, 10)  # STATCAST label top-left
    assert _lit_in(real, 4, 200, 10, 28)  # player name
    assert _lit_in(real, 4, 120, 24, 52)  # big exit-velo headline
    assert _lit_in(real, 4, 252, 52, 64)  # bottom la/dist/pitch row


def test_big_never_raises_on_empty_context():
    canvas, real = _bigsign()
    render_statcast_big(canvas, StatRecord(value=0, person_id=0, team_abbr=""), "", 1.0)


def test_big_y_offset_shifts_content():
    canvas, real = _bigsign()
    render_statcast_big(canvas, _rec(), "RAMIREZ", 1.0)
    rows = {y for x, y in real._pixels if real.get_pixel(x, y) != (0, 0, 0)}
    canvas2, real2 = _bigsign()
    render_statcast_big(canvas2, _rec(), "RAMIREZ", 1.0, y_offset=8)
    rows2 = {y for x, y in real2._pixels if real2.get_pixel(x, y) != (0, 0, 0)}
    assert min(rows2) - min(rows) == 32


def test_big_batted_draws_arc_in_box():
    canvas, real = _bigsign()
    render_statcast_big(canvas, _hr_rec(), "RAMIREZ", 1.0)
    assert _lit_in(real, _BOX_X0, _BOX_X1, _BOX_Y0, _BOX_Y1)
    # A HOME RUN's "clears" act lands its bright leading-edge/ball pixels a
    # hair past the box's right edge by design (see trajectory.py's
    # `end_x = w` comment) — the rest of the arc's flight path paints inside
    # the box in the dimmed trail shade, so check for either.
    assert any(
        real.get_pixel(x, y) in (MAGENTA, MAGENTA_TRAIL)
        for x in range(_BOX_X0, _BOX_X1)
        for y in range(_BOX_Y0, _BOX_Y1)
    )


def test_big_pitch_record_draws_no_arc():
    canvas, real = _bigsign()
    render_statcast_big(canvas, _pitch_rec(), "COLE", 1.0)
    assert not any(
        real.get_pixel(x, y) in (MAGENTA, MAGENTA_TRAIL)
        for x in range(_BOX_X0, _BOX_X1)
        for y in range(_BOX_Y0, _BOX_Y1)
    )


def test_big_arc_stays_within_box():
    # A "fair" double (not a HR "clears" act, whose landing ball
    # intentionally lands a hair past the box's right edge — see
    # trajectory.py) so a genuine box-overrun bug isn't masked by that
    # by-design overflow.
    canvas, real = _bigsign()
    render_statcast_big(canvas, _double_rec(), "RAMIREZ", 1.0)
    magenta = _magenta_pixels(real)
    # Exclude the bottom la/dist/pitch text row (y >= 52, per
    # test_big_regions_present) — its "dist" text is unconditionally
    # colored MAGENTA regardless of the arc (existing layout behavior, not
    # part of "the arc path/ball"); only pixels above that row could
    # plausibly be the arc bleeding into other card content.
    arc_magenta = [(x, y) for x, y in magenta if y < 52]
    assert arc_magenta  # sanity: the arc actually painted something
    assert not any(
        x < _BOX_X0 or x >= _BOX_X1 or y < _BOX_Y0 or y >= _BOX_Y1
        for x, y in arc_magenta
    )


def test_big_progress_advances_arc():
    canvas_early, real_early = _bigsign()
    render_statcast_big(canvas_early, _rec(), "RAMIREZ", 0.1)
    canvas_full, real_full = _bigsign()
    render_statcast_big(canvas_full, _rec(), "RAMIREZ", 1.0)
    lit_early = sum(
        1 for x, y in real_early._pixels if real_early.get_pixel(x, y) != (0, 0, 0)
    )
    lit_full = sum(
        1 for x, y in real_full._pixels if real_full.get_pixel(x, y) != (0, 0, 0)
    )
    assert lit_full > lit_early
