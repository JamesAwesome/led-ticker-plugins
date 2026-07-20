"""tests/test_statcast_card_dispatch.py — MLBStatcastCard scale dispatch +
restart-on-visit flight clock.

Mirrors tests/test_promo_card_dispatch.py's shape for the scale-1 forward
and held-width assertions; the flight-clock tests are the crux (restart-on-
visit is the OPPOSITE of MLBPromoCard's clock, which survives visits).
"""

from led_ticker.plugin import HeadlessBackend, ScaledCanvas, SegmentMessage, colors

from led_ticker_baseball._statcast_card import MLBStatcastCard
from led_ticker_baseball.statcast import StatRecord


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
        pitch_name="SL",
    )


def _legacy():
    return SegmentMessage([("HR", colors.RGB_WHITE)], center=True)


def _card(**over):
    kw = dict(
        record=_rec(),
        player_name="RAMIREZ",
        legacy=_legacy(),
        story_index=0,
        story_total=1,
    )
    kw.update(over)
    return MLBStatcastCard(**kw)


def test_scale_one_forwards_to_legacy():
    real = HeadlessBackend(160, 16).create_canvas()
    canvas = ScaledCanvas(real, scale=1, content_height=16)
    card = _card()
    out, cursor = card.draw(canvas, 0)
    # legacy SegmentMessage draws; cursor is its own returned width, not canvas.width
    assert out is not None


def test_held_card_returns_logical_width():
    real = HeadlessBackend(512, 64).create_canvas()
    canvas = ScaledCanvas(real, scale=4, content_height=16)
    _out, cursor = _card().draw(canvas, 0)
    assert cursor == canvas.width  # 128 logical — engine hold branch


def test_flight_clock_advances_only_unpaused():
    card = _card()
    card.advance_frame()
    card.advance_frame()
    assert card._flight_ticks == 2
    card.pause_frame()
    card.advance_frame()
    assert card._flight_ticks == 2
    card.resume_frame()
    card.advance_frame()
    assert card._flight_ticks == 3


def test_flight_clock_resets_on_visit():
    """Restart-on-visit: the ball flies fresh each appearance — the
    OPPOSITE of the promo card. reset_frame (incl. the double call) zeroes
    the flight clock."""
    card = _card()
    card.advance_frame()
    card.advance_frame()
    card.advance_frame()
    assert card._flight_ticks == 3
    card.reset_frame()
    card.reset_frame()  # core's double call
    assert card._flight_ticks == 0
