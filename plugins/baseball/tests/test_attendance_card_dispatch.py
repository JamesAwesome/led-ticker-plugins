from led_ticker.plugin import HeadlessBackend, ScaledCanvas, SegmentMessage, colors

from led_ticker_baseball._attendance_card import MLBAttendanceCard
from led_ticker_baseball.attendance import AttendanceGame


def _legacy():
    return SegmentMessage([("att", colors.RGB_WHITE)], center=True)


def _card(**over):
    kw = dict(
        record=AttendanceGame(
            paid=46537,
            capacity=56000,
            avg=39442,
            venue="Dodger Stadium",
            home_abbr="LAD",
        ),
        legacy=_legacy(),
        story_index=0,
        story_total=1,
    )
    kw.update(over)
    return MLBAttendanceCard(**kw)


def test_scale_one_forwards_to_legacy():
    real = HeadlessBackend(160, 16).create_canvas()
    out, _ = _card().draw(ScaledCanvas(real, scale=1, content_height=16), 0)
    assert out is not None


def test_held_card_returns_logical_width():
    real = HeadlessBackend(512, 64).create_canvas()
    canvas = ScaledCanvas(real, scale=4, content_height=16)
    _out, cursor = _card().draw(canvas, 0)
    assert cursor == canvas.width  # 128 logical


def test_no_attendance_falls_back_to_legacy():
    """A team game not yet Final (paid=None) draws the legacy line verbatim
    through the wrapper (readable, scaled), NOT the hero card. Distinguished
    by PIXELS: the card's output must equal a direct legacy render on an
    identical wrapper — cursor value can't tell them apart, since a centered
    SegmentMessage returns canvas.width, same as the hero card."""
    legacy = _legacy()  # the same SegmentMessage the card wraps
    card = _card(
        record=AttendanceGame(
            paid=None,
            capacity=56000,
            avg=39442,
            venue="Dodger Stadium",
            home_abbr="LAD",
        ),
        legacy=legacy,
    )
    real_a = HeadlessBackend(512, 64).create_canvas()
    canvas_a = ScaledCanvas(real_a, scale=4, content_height=16)
    card.draw(canvas_a, 0)
    # direct legacy render on an identical fresh wrapper, same args
    real_b = HeadlessBackend(512, 64).create_canvas()
    canvas_b = ScaledCanvas(real_b, scale=4, content_height=16)
    legacy.draw(canvas_b, 0)
    # forwarding through the wrapper renders pixel-identical to the legacy
    # line; forwarding the unwrapped real canvas (the bug) would not
    assert real_a._pixels == real_b._pixels


def test_fill_clock_advances_only_unpaused():
    card = _card()
    card.advance_frame()
    card.advance_frame()
    assert card._fill_ticks == 2
    card.pause_frame()
    card.advance_frame()
    assert card._fill_ticks == 2
    card.resume_frame()
    card.advance_frame()
    assert card._fill_ticks == 3


def test_fill_clock_resets_on_visit():
    """Restart-on-visit (statcast pattern): the bar re-fills each appearance."""
    card = _card()
    card.advance_frame()
    card.advance_frame()
    card.advance_frame()
    assert card._fill_ticks == 3
    card.reset_frame()
    card.reset_frame()  # core's double call
    assert card._fill_ticks == 0
