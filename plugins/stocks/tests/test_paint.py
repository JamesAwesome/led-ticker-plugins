from led_ticker.plugin import HeadlessBackend, ScaledCanvas

from led_ticker_stocks import _palette as pal
from led_ticker_stocks._paint import hires, paging_dots, phys_wrap, px, right_align_x


def _canvas(w=256, h=64, scale=4):
    # A ScaledCanvas over a real headless canvas, like a bigsign story receives.
    real = HeadlessBackend(w, h).create_canvas()
    return ScaledCanvas(real, scale=scale, content_height=16)


def test_phys_wrap_unwraps_to_real_dims():
    c = _canvas()
    shim, real = phys_wrap(c)
    assert real.width == 256 and real.height == 64
    assert shim.width == 256 and shim.height == 64  # scale-1 shim == physical


def test_hires_lights_physical_pixels_and_returns_advance():
    c = _canvas()
    shim, real = phys_wrap(c)
    adv = hires(shim, "AAPL", 4, 1, pal.SYM, 22, bold=True)
    assert adv > 0
    lit = sum(1 for v in real._pixels.values() if v != (0, 0, 0))
    assert lit > 0
    # glyphs land in the physical top band (y within panel), not scaled 4x
    ys = [y for (x, y), v in real._pixels.items() if v != (0, 0, 0)]
    assert max(ys) < 64


def test_right_align_positions_end_near_right_edge():
    c = _canvas()
    shim, real = phys_wrap(c)
    x = right_align_x(22, "252.40", real.width, 4, bold=True)
    end = hires(shim, "252.40", x, 1, pal.PRICE, 22, bold=True)
    assert x + end <= real.width - 4 + 1  # ends ~4px from the edge
    assert x + end >= real.width - 4 - 6  # and not far short


def test_px_bounds_checked():
    real = HeadlessBackend(10, 10).create_canvas()
    px(real, -1, 0, pal.SYM)  # off-canvas: no error, no write
    px(real, 5, 5, pal.SYM)
    assert real._pixels.get((5, 5)) == (255, 255, 255)
    assert (-1, 0) not in real._pixels


def test_paging_dots_marks_current():
    real = HeadlessBackend(64, 16).create_canvas()
    paging_dots(real, 4, 1, 0, 0, dim_color=pal.LABEL, active_color=pal.SYM)
    # 4 dots drawn; the current (index 1) uses the brighter active color
    assert any(v == (255, 255, 255) for v in real._pixels.values())
