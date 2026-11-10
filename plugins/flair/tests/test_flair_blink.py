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


@pytest.fixture
def colored_token_registry():
    """Register source `x` = "99" declaring a red `color`; reset afterwards."""
    from led_ticker.color_providers import _ConstantColor
    from led_ticker.plugin import make_color
    from led_ticker.sources import DataRegistry, StaticSource, set_data_registry

    src = StaticSource(id="x", value="99")
    src.color = _ConstantColor(make_color(200, 0, 0))
    src.refresh()
    reg = DataRegistry()
    reg.add(src)
    set_data_registry(reg)
    yield (200, 0, 0)
    set_data_registry(DataRegistry())


def _at_frame(msg: TickerMessage, frame: int) -> None:
    msg._frame_count = frame
    msg._effect_frames["animation"] = frame


def test_empty_slice_with_emoji_and_token(colored_token_registry) -> None:
    tok = colored_token_registry
    msg = TickerMessage(
        text="HOT :x: :sun:", animation=Blink(), font_color=(0, 200, 0), center=False
    )
    on_canvas = HeadlessCanvas(width=160, height=16)
    msg.draw(on_canvas)  # frame 0: on
    assert msg._has_emoji is True
    assert tok in set(on_canvas._pixels.values()), "token color must render when on"
    assert _lit(on_canvas) > 0

    off_canvas = HeadlessCanvas(width=160, height=16)
    _at_frame(msg, 15)
    msg.draw(off_canvas)  # empty slice through the colored-token + emoji path
    assert _lit(off_canvas) == 0


def test_message_end_cursor_unchanged() -> None:
    msg = TickerMessage(text="HOT :sun: deal", animation=Blink())
    _, on_cursor = msg.draw(HeadlessCanvas(width=160, height=16))
    _at_frame(msg, 15)
    _, off_cursor = msg.draw(HeadlessCanvas(width=160, height=16))
    assert off_cursor == on_cursor


class _RecordingFrame:
    """Frame whose swap rotates two canvases, recording per swap the blink
    frame index (msg._effect_frames) and the lit-pixel count."""

    def __init__(self) -> None:
        self.a = HeadlessCanvas(width=160, height=16)
        self.b = HeadlessCanvas(width=160, height=16)
        self.msg = None
        self.log: list[tuple[int, int]] = []

    def get_clean_canvas(self):
        return self.a

    def swap(self, canvas):
        idx = self.msg._effect_frames.get("animation", 0)
        self.log.append((idx, _lit(canvas)))
        return self.b if canvas is self.a else self.a


async def test_hold_ending_mid_off_settles_to_on(no_sleep_blink) -> None:
    frame = _RecordingFrame()
    msg = TickerMessage(text="NEWS", animation=Blink())
    frame.msg = msg
    ticker = Ticker(monitors=[], frame=frame)
    # 0.8 s hold = 16 ticks -> natural end at frame 16 (off); settle adds 4.
    await ticker._swap_and_scroll(frame.get_clean_canvas(), msg, hold_time=0.8)
    by_idx = dict(frame.log)
    assert by_idx[16] == 0, "natural hold end must land in the off phase"
    assert max(by_idx) == 20, "settle must extend the hold to the next on frame"
    assert frame.log[-1][0] == 20 and frame.log[-1][1] > 0
