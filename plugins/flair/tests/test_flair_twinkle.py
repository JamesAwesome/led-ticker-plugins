"""flair.twinkle — per-pixel twinkle text animation (pixel_gain)."""

import statistics
import time

import pytest
from led_ticker.plugin import (
    HeadlessCanvas,
    ScaledCanvas,
    TickerMessage,
    make_color,
    resolve_font,
)

from led_ticker_flair.flair.twinkle import Twinkle

_COLOR = (200, 200, 200)


def test_gain_is_one_for_non_twinklers() -> None:
    from led_ticker_flair.flair._twinkle import is_twinkler

    t = Twinkle(density=0.3, seed=5)
    gain = t.frame_for(9, "X", 160, 6).pixel_gain
    checked = 0
    for y in range(8):
        for x in range(100):
            if not is_twinkler(x, y, 5, 0.3):
                assert gain(x, y) == 1.0
                checked += 1
    assert checked > 300


def test_gain_floor() -> None:
    t = Twinkle(density=1.0, min_brightness=0.2, seed=3)
    for frame in range(0, 80, 3):
        gain = t.frame_for(frame, "X", 160, 6).pixel_gain
        for y in range(4):
            for x in range(40):
                g = gain(x, y)
                assert 0.2 - 1e-9 <= g <= 1.0 + 1e-9


def test_gain_matches_level() -> None:
    from led_ticker_flair.flair._twinkle import is_twinkler, level

    t = Twinkle(density=0.5, speed=1.5, min_brightness=0.1, seed=8)
    gain = t.frame_for(13, "X", 160, 6).pixel_gain
    for y in range(6):
        for x in range(150):  # crosses the row-chunk boundary
            if is_twinkler(x, y, 8, 0.5):
                expect = 0.1 + 0.9 * level(x, y, 13, 8, 1.5)
                assert gain(x, y) == pytest.approx(expect)


def test_pure_function_of_frame() -> None:
    t = Twinkle(seed=2)
    pts = [(x, y) for x in range(0, 200, 7) for y in range(0, 20, 3)]
    a = [t.frame_for(11, "X", 160, 6).pixel_gain(x, y) for x, y in pts]
    # advance other frames, then come back
    for f in (12, 50, 3):
        g = t.frame_for(f, "X", 160, 6).pixel_gain
        [g(x, y) for x, y in pts]
    b = [t.frame_for(11, "X", 160, 6).pixel_gain(x, y) for x, y in pts]
    assert a == b


def test_visible_text_and_rest() -> None:
    t = Twinkle(seed=1)
    assert t.frame_for(4, "HELLO", 160, 30).visible_text == "HELLO"
    assert t.frames_to_rest(3, 5) == 0
    assert t.restart_on_visit is False


def test_speed_cap() -> None:
    with pytest.raises(ValueError):
        Twinkle(speed=2.5)
    Twinkle(speed=2.0)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"density": 0},
        {"density": 1.5},
        {"density": True},
        {"speed": 0},
        {"min_brightness": 1.0},
        {"min_brightness": -0.1},
        {"seed": 1.5},
        {"seed": True},
    ],
)
def test_bad_args(kwargs) -> None:
    with pytest.raises(ValueError):
        Twinkle(**kwargs)


def _bigsign_draw(msg: TickerMessage) -> HeadlessCanvas:
    real = HeadlessCanvas(width=256, height=64)
    msg.draw(ScaledCanvas(real, scale=4, content_height=16))
    return real


def _dimmer_count(real: HeadlessCanvas) -> tuple[int, int]:
    lit = [rgb for rgb in real._pixels.values() if rgb != (0, 0, 0)]
    return sum(1 for rgb in lit if rgb[0] < _COLOR[0]), len(lit)


def _at(msg: TickerMessage, frame: int) -> None:
    msg._frame_count = frame
    msg._effect_frames["animation"] = frame


def test_bigsign_hires_message_twinkles() -> None:
    msg = TickerMessage(
        text="TWINKLE TWINKLE",
        font=resolve_font("Inter-Bold", 28),
        font_color=make_color(*_COLOR),
        animation=Twinkle(seed=4),
    )
    _at(msg, 7)
    dim, lit = _dimmer_count(_bigsign_draw(msg))
    assert lit > 0 and dim > 0


def test_bigsign_bdf_message_twinkles() -> None:
    msg = TickerMessage(
        text="TWINKLE TWINKLE",
        font_color=make_color(*_COLOR),
        animation=Twinkle(seed=4),
    )
    _at(msg, 7)
    dim, lit = _dimmer_count(_bigsign_draw(msg))
    assert lit > 0 and dim > 0


def test_perf_bigsign() -> None:
    def make(anim):
        m = TickerMessage(
            text="TWINKLE TWINKLE 12345",
            font=resolve_font("Inter-Bold", 28),
            font_color=make_color(*_COLOR),
            animation=anim,
        )
        return m

    def timed(msg) -> float:
        samples = []
        for i in range(9):
            _at(msg, i)
            real = HeadlessCanvas(width=256, height=64)
            canvas = ScaledCanvas(real, scale=4, content_height=16)
            t0 = time.perf_counter()
            msg.draw(canvas)
            samples.append(time.perf_counter() - t0)
        return statistics.median(samples[1:])  # drop the cold first row-build

    plain = timed(make(None))
    # Warm the row cache the way steady-state frames see it.
    twinkle_msg = make(Twinkle(seed=4))
    _at(twinkle_msg, 0)
    twinkle_msg.draw(ScaledCanvas(HeadlessCanvas(256, 64), scale=4, content_height=16))
    tw = timed(twinkle_msg)
    assert tw <= 0.005, f"twinkle draw {tw * 1000:.2f} ms"
    assert tw - plain <= 0.0025, f"overhead {(tw - plain) * 1000:.2f} ms"
