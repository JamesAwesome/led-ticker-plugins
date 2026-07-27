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


def test_no_attendance_hires_fallback_at_scale_gt_1():
    """No attendance (paid=None) + non-empty fallback_segments at scale>1
    renders a HIRES line, not the block-scaled legacy BDF.

    Two guards: (1) the mutation-proof one — the identical card but with
    fallback_segments=[] forwards to the BDF `legacy` line instead (the
    actual regression this test exists to catch), so the two renders must
    differ pixel-for-pixel; (2) a vertical-span check, upper-bounded so a
    block-scaled BDF line (which also clears a naive lower-bound-only
    check) can't slip through — well past a plain BDF cell's ~12px span,
    and comfortably under the ~35px a BDF line reaches once block-scaled
    through this same scale=4 wrapper."""
    record = AttendanceGame(
        paid=None,
        capacity=56000,
        avg=39442,
        venue="Dodger Stadium",
        home_abbr="LAD",
    )
    card = _card(
        record=record,
        fallback_segments=[("PHI · Citizens Bank Park", colors.RGB_WHITE)],
    )
    real = HeadlessBackend(512, 64).create_canvas()
    canvas = ScaledCanvas(real, scale=4, content_height=16)
    card.draw(canvas, 0)
    lit_rows = {y for (x, y), v in real._pixels.items() if v != (0, 0, 0)}
    assert lit_rows
    assert 12 <= max(lit_rows) - min(lit_rows) <= 30

    bdf_card = _card(
        record=record,
        fallback_segments=[],
    )
    real_bdf = HeadlessBackend(512, 64).create_canvas()
    canvas_bdf = ScaledCanvas(real_bdf, scale=4, content_height=16)
    bdf_card.draw(canvas_bdf, 0)
    assert real._pixels != real_bdf._pixels


def test_no_attendance_scale_one_still_bdf_ignores_fallback_segments():
    """At scale<=1 the card forwards to `legacy` (BDF) verbatim, even when
    `fallback_segments` is populated — the hires fallback is scale>1 only."""
    legacy = _legacy()
    card = _card(
        record=AttendanceGame(
            paid=None,
            capacity=56000,
            avg=39442,
            venue="Dodger Stadium",
            home_abbr="LAD",
        ),
        legacy=legacy,
        fallback_segments=[("PHI · Citizens Bank Park", colors.RGB_WHITE)],
    )
    real_a = HeadlessBackend(160, 16).create_canvas()
    canvas_a = ScaledCanvas(real_a, scale=1, content_height=16)
    card.draw(canvas_a, 0)

    real_b = HeadlessBackend(160, 16).create_canvas()
    canvas_b = ScaledCanvas(real_b, scale=1, content_height=16)
    legacy.draw(canvas_b, 0)
    assert real_a._pixels == real_b._pixels


def test_no_attendance_empty_fallback_segments_forwards_to_legacy():
    """Safety net: an empty `fallback_segments` at scale>1 forwards to
    `legacy` rather than blanking or crashing (mirrors
    `test_no_attendance_falls_back_to_legacy`, explicit about the empty-list
    trigger)."""
    legacy = _legacy()
    card = _card(
        record=AttendanceGame(
            paid=None,
            capacity=56000,
            avg=39442,
            venue="Dodger Stadium",
            home_abbr="LAD",
        ),
        legacy=legacy,
        fallback_segments=[],
    )
    real_a = HeadlessBackend(512, 64).create_canvas()
    canvas_a = ScaledCanvas(real_a, scale=4, content_height=16)
    card.draw(canvas_a, 0)

    real_b = HeadlessBackend(512, 64).create_canvas()
    canvas_b = ScaledCanvas(real_b, scale=4, content_height=16)
    legacy.draw(canvas_b, 0)
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
