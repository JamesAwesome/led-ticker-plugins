from led_ticker.plugin import unwrap_to_real

from led_ticker_flight import paint
from led_ticker_flight.palette import IDENT, LABEL, LIVE


def lit(canvas_or_real):
    return dict(unwrap_to_real(canvas_or_real)._pixels)


def test_dim_scales_channels():
    c = paint.dim((200, 100, 50), 0.5)
    assert (c.red, c.green, c.blue) == (100, 50, 25)


def test_phys_wrap_identity_coords(bigsign):
    shim, real = paint.phys_wrap(bigsign)
    assert real.width == 256 and real.height == 64
    assert shim.scale == 1 and shim.y_offset_real == 0


def test_px_bounds_guard(smallsign):
    paint.px(smallsign, -1, 0, (255, 0, 0))
    paint.px(smallsign, 0, 99, (255, 0, 0))
    paint.px(smallsign, 3, 4, (255, 0, 0))
    assert set(lit(smallsign)) == {(3, 4)}


def test_hires_draws_at_physical_position(bigsign):
    shim, real = paint.phys_wrap(bigsign)
    w = paint.hires(shim, "UA2341", 35, 1, IDENT, 26)
    assert w > 40  # 6 chars at 26px are wide
    pixels = lit(real)
    assert pixels, "hires text lit nothing"
    ys = [y for (_, y) in pixels]
    xs = [x for (x, _) in pixels]
    # glyphs sit in the y1..~y27 band, start at x>=35 (no exact pins: freetype varies)
    assert min(ys) >= 1 and max(ys) <= 34
    assert min(xs) >= 35
    assert all(rgb == (255, 255, 255) for rgb in pixels.values())


def test_paging_dots(bigsign):
    shim, real = paint.phys_wrap(bigsign)
    paint.paging_dots(real, 4, n=3, cur=1, x=100, y=50)
    pixels = lit(real)
    assert pixels[(100, 50)] == LABEL  # dot 0
    assert pixels[(108, 50)] == IDENT  # dot 1 (current), step = 2*scale = 8
    assert pixels[(116, 50)] == LABEL  # dot 2
    assert (100, 54) not in pixels  # dots are scale-tall (rows 50..53)


def test_live_pulse_duty_cycle(smallsign):
    paint.live_pulse(smallsign, 1, clock_ms=0)  # phase 0 < 0.12 -> full
    on = lit(smallsign)[(158, 1)]
    assert on == LIVE
    smallsign2 = type(smallsign)(160, 16)
    paint.live_pulse(smallsign2, 1, clock_ms=5000)  # phase 0.5 -> dim 0.18
    dimmed = lit(smallsign2)[(158, 1)]
    assert dimmed == (int(0 * 0.18), int(255 * 0.18), int(0 * 0.18))


def test_draw_empty_radar_and_text(smallsign):
    paint.draw_empty(smallsign, clock_ms=800, wide=False)  # sweep at x=40
    pixels = lit(smallsign)
    col_x = {x for (x, y) in pixels if x == 40}
    assert col_x, "radar column missing at x=40"
    center = pixels[(40, 8)]
    edge = pixels.get((40, 0), (0, 0, 0))
    assert sum(center) > sum(edge)  # brightest at vertical center
    # NO TRAFFIC text: some non-radar pixels away from x=40
    assert any(x != 40 for (x, y) in pixels)


def test_draw_empty_wide_label(longboi):
    paint.draw_empty(longboi, clock_ms=0, wide=True)
    assert lit(longboi), "wide empty state lit nothing"
