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
    assert "20 ms" in str(exc.value)
    Blink(period_ms=300, allow_fast=True)


def test_min_safe_period_boundary() -> None:
    # 17 frames x 20 ms = 340 ms -> 2.94 Hz at the fastest engine cadence.
    assert Blink(period_ms=850).period == 17
    for bad in (800, 825, 350):
        with pytest.raises(ValueError, match="WCAG 2.3.1"):
            Blink(period_ms=bad)
    assert Blink(period_ms=800, allow_fast=True).period == 16


def test_off_phase_beyond_settle_cap_refused() -> None:
    with pytest.raises(ValueError, match="settle limit"):
        Blink(period_ms=3000, duty=0.5)  # 30 off frames
    with pytest.raises(ValueError, match="settle limit"):
        Blink(period_ms=4000, duty=0.5, allow_fast=True)
    # Boundary: 20 off frames accepted, 21 refused.
    assert (
        Blink(period_ms=2000, duty=0.5).period - Blink(period_ms=2000, duty=0.5).on
        == 20
    )
    with pytest.raises(ValueError, match="settle limit"):
        Blink(period_ms=2100, duty=0.5)  # 42 frames, on 21, off 21
    Blink(period_ms=3000, duty=0.75)  # 15 off frames, long period fine


def test_locks_resolution_false() -> None:
    from led_ticker_flair.flair.twinkle import Twinkle

    assert Blink.locks_resolution is False
    assert Twinkle.locks_resolution is False


async def test_scroll_cadence_20ms_stays_under_3hz(monkeypatch) -> None:
    """Regression: the counter advances once per scroll step, so the
    minimum allowed period must hold <= 3 Hz even at scroll_step 20 ms."""
    import asyncio

    slept = [0.0]
    real_sleep = asyncio.sleep

    async def fake_sleep(d, *a, **k):
        slept[0] += d
        await real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    class _F:
        def __init__(self) -> None:
            self.a = HeadlessCanvas(width=160, height=16)
            self.b = HeadlessCanvas(width=160, height=16)
            self.log: list[bool] = []

        def get_clean_canvas(self):
            return self.a

        def swap(self, canvas):
            self.log.append(_lit(canvas) > 0)
            return self.b if canvas is self.a else self.a

    f = _F()
    msg = TickerMessage(
        text="LONG BLINKING HEADLINE THAT OVERFLOWS THE SMALLSIGN PANEL WIDTH FOR SURE",
        animation=Blink(period_ms=850),
    )
    t = Ticker(monitors=[], frame=f)
    t.scroll_speed = 0.02
    await t._swap_and_scroll(f.get_clean_canvas(), msg, hold_time=0.05)
    ons = sum(1 for a, b in zip(f.log, f.log[1:], strict=False) if b and not a)
    assert ons >= 5, "need enough blink cycles for a meaningful rate"
    assert slept[0] > 0
    assert ons / slept[0] <= 3.0, f"{ons / slept[0]:.2f} Hz"


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
        {"period_ms": float("inf")},
        {"period_ms": float("nan")},
        {"period_ms": True},
    ],
)
def test_bad_args(kwargs) -> None:
    with pytest.raises(ValueError):
        Blink(**kwargs)


def test_period_ms_non_finite_or_huge_refused() -> None:
    for bad in (float("inf"), float("-inf"), float("nan"), 1e300, 60_001, "900"):
        with pytest.raises(ValueError, match="period_ms must be a finite number"):
            Blink(period_ms=bad, allow_fast=True)
    assert Blink(period_ms=60_000, duty=0.99).period == 1200


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


@pytest.mark.parametrize("bad", ["false", "true", 1, 0, None, "no"])
def test_allow_fast_must_be_bool(bad) -> None:
    with pytest.raises(ValueError, match="allow_fast must be a bool"):
        Blink(period_ms=100, allow_fast=bad)
