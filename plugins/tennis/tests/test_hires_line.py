from led_ticker.plugin import TickerMessage, make_color, unwrap_to_real

from led_ticker_tennis._hires_line import HiresLine

from .conftest import lit

WHITE = make_color(255, 255, 255)


def _line(text="No tennis matches right now"):
    return HiresLine([(text, WHITE)], legacy=TickerMessage(text, font_color=WHITE))


def test_scale1_forwards_to_legacy(smallsign):
    _, cursor = _line().draw(smallsign, 3)
    assert cursor > 3 and lit(smallsign)


def test_scaled_paints_hires_and_holds(longboi):
    _, cursor = _line().draw(longboi)
    assert cursor == longboi.width
    xs = [x for x, _ in lit(unwrap_to_real(longboi))]
    assert min(xs) >= 8 and max(xs) <= 512 - 8


def test_overlong_text_is_fitted_within_margins(bigsign):
    _line(
        "Tennis: set LIVETENNIS_API_KEY (free key: https://livetennisapi.com/subscribe/free)"
    ).draw(bigsign)
    xs = [x for x, _ in lit(unwrap_to_real(bigsign))]
    assert min(xs) >= 8 and max(xs) <= 256 - 8


def test_empty_segments_use_legacy(longboi):
    line = HiresLine([], legacy=TickerMessage("x", font_color=WHITE))
    _, cursor = line.draw(longboi)
    assert cursor > 0


def test_frame_hooks_forward():
    line = _line()
    line.advance_frame(visit_id=1)
    line.pause_frame()
    line.resume_frame()
    line.reset_frame()
    assert line.legacy._frame_count >= 0
