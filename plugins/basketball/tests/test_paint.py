"""Paint helpers: the logo painter clips through a real `ShiftedReal`."""

from led_ticker.plugin import HeadlessBackend

from led_ticker_basketball import _logos
from led_ticker_basketball._paint import ShiftedReal, fit_text, rect, text_width


def test_paint_logo_clips_on_real_shifted_real():
    real = HeadlessBackend(256, 64).create_canvas()
    landed = []
    orig = real.SetPixel

    def spy(x, y, r, g, b):
        landed.append((x, y))
        orig(x, y, r, g, b)

    real.SetPixel = spy
    shifted = ShiftedReal(real, -20)
    sprite = _logos.sprite("PHI", 36)
    assert sprite is not None
    _logos.paint_logo(shifted, sprite, 0, 14)
    assert 0 < len(landed) < len(sprite.pixels)
    assert all(0 <= x < 16 for x, _ in landed)  # 36 px sprite shifted 20 left


def test_rect_is_inclusive_and_clipped():
    real = HeadlessBackend(10, 4).create_canvas()
    rect(real, -2, 1, 1, 9, _red())
    lit = {xy for xy, v in real._pixels.items() if v != (0, 0, 0)}
    assert lit == {(x, y) for x in range(2) for y in range(1, 4)}


def test_fit_text_ellipsizes_at_the_floor():
    assert fit_text("HI", 1000, 20) == "HI"
    long = "MADISON SQUARE GARDEN"
    cut = fit_text(long, text_width(20, long) // 2, 20)
    assert cut.endswith("…") and text_width(20, cut) <= text_width(20, long) // 2


def _red():
    from led_ticker.plugin import make_color

    return make_color(255, 0, 0)
