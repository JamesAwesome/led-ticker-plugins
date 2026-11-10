"""flair.blink — hard on/off text blink animation."""

import pytest
from led_ticker.plugin import ENGINE_TICK_MS, HeadlessCanvas, TickerMessage
from led_ticker.ticker import Ticker

from led_ticker_flair.flair.blink import Blink


def _on(blink: Blink, frame: int) -> bool:
    return blink.frame_for(frame, "NEWS", 160, 24).visible_text == "NEWS"


def test_frame_zero_is_on() -> None:
    assert _on(Blink(), 0)


def test_default_cycle() -> None:
    b = Blink()
    assert ENGINE_TICK_MS == 50  # 1000 ms -> period 20
    assert all(_on(b, f) for f in range(0, 15))
    assert not any(_on(b, f) for f in range(15, 20))
    assert _on(b, 20)


def test_off_phase_blanks() -> None:
    assert Blink().frame_for(15, "NEWS", 160, 24).visible_text == ""


def test_count_stops_on() -> None:
    b = Blink(count=2)
    assert not _on(b, 15)  # still blinking in cycle 1
    assert all(_on(b, f) for f in range(40, 200))


def test_frames_to_rest_counts_to_next_on() -> None:
    b = Blink()
    assert b.frames_to_rest(15, 4) == 5
    assert b.frames_to_rest(3, 4) == 0


def test_fast_rate_refused() -> None:
    with pytest.raises(ValueError, match="WCAG 2.3.1") as exc:
        Blink(period_ms=300)
    assert "allow_fast" in str(exc.value)
    Blink(period_ms=300, allow_fast=True)
    Blink(period_ms=350)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"duty": 0.0},
        {"duty": 1.0},
        {"duty": -0.5},
        {"count": -1},
        {"count": True},
        {"period_ms": 0},
        {"period_ms": -100},
    ],
)
def test_bad_args(kwargs) -> None:
    with pytest.raises(ValueError):
        Blink(**kwargs)


def _lit(canvas: HeadlessCanvas) -> int:
    return sum(1 for rgb in canvas._pixels.values() if rgb != (0, 0, 0))


def test_empty_slice_with_emoji_and_token() -> None:
    msg = TickerMessage(text="HOT :sun: deal", animation=Blink())
    canvas = HeadlessCanvas(width=160, height=16)
    on_canvas = HeadlessCanvas(width=160, height=16)
    msg.draw(on_canvas)  # frame 0: on
    assert _lit(on_canvas) > 0
    msg._frame_count = 15
    msg._effect_frames["animation"] = 15
    msg.draw(canvas)
    assert _lit(canvas) == 0


def test_message_end_cursor_unchanged() -> None:
    msg = TickerMessage(text="HOT :sun: deal", animation=Blink())
    _, on_cursor = msg.draw(HeadlessCanvas(width=160, height=16))
    msg._frame_count = 15
    msg._effect_frames["animation"] = 15
    _, off_cursor = msg.draw(HeadlessCanvas(width=160, height=16))
    assert off_cursor == on_cursor


class _RecordingFrame:
    """Frame whose swap rotates two canvases and records lit-pixel counts."""

    def __init__(self) -> None:
        self.a = HeadlessCanvas(width=160, height=16)
        self.b = HeadlessCanvas(width=160, height=16)
        self.lit: list[int] = []

    def get_clean_canvas(self):
        return self.a

    def swap(self, canvas):
        self.lit.append(_lit(canvas))
        return self.b if canvas is self.a else self.a


async def test_hold_ending_mid_off_settles_to_on(no_sleep_blink) -> None:
    frame = _RecordingFrame()
    msg = TickerMessage(text="NEWS", animation=Blink())
    ticker = Ticker(monitors=[], frame=frame)
    # 0.8 s hold = 16 ticks -> frame 16 (off); settle adds 4 -> frame 20 (on).
    await ticker._swap_and_scroll(frame.get_clean_canvas(), msg, hold_time=0.8)
    assert frame.lit[-1] > 0, "hold ended on an off frame; settle did not run"
    assert 0 in frame.lit, "expected off frames during the hold"
