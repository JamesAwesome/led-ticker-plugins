from led_ticker.plugin import unwrap_to_real

from led_ticker_flight import paint
from led_ticker_flight.palette import IDENT, LABEL


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


def test_draw_empty_bigsign_label_falls_back_to_fit(bigsign):
    # wide=True (256 phys >= 200) picks the long label, but the bigsign has
    # only 64 LOGICAL cells and "NO TRAFFIC OVERHEAD" measures ~95 — the
    # fit-fallback must swap in the short "NO TRAFFIC" so nothing clips at
    # either edge. clock_ms=1600 parks the radar sweep mid-canvas (real
    # x=128) so the edge columns are text-only evidence. Margin check is
    # the layout-guards-sweep 6px floor (2026-07-16) applied to a
    # single centered label: distance to each panel edge, not to a
    # neighboring block.
    paint.draw_empty(bigsign, clock_ms=1600, wide=True)
    real = unwrap_to_real(bigsign)
    text_xs = [x for (x, _y) in lit(real) if x != 128]  # exclude radar column
    assert text_xs, "empty-state label lit nothing"
    assert min(text_xs) >= 6, "label within 6px of the left edge"
    assert real.width - 1 - max(text_xs) >= 6, "label within 6px of the right edge"


def test_draw_empty_longboi_keeps_long_label(longboi):
    # longboi's 128 logical cells fit the 19-char label (~95) — the fallback
    # must NOT fire there. The long label spans ~380 real px; the short one
    # would only span ~200. Same 6px-floor margin check as the bigsign case.
    paint.draw_empty(longboi, clock_ms=1600, wide=True)
    real = unwrap_to_real(longboi)
    xs = [x for (x, _y) in lit(real) if x != 256]  # exclude radar column
    assert xs, "empty-state label lit nothing"
    assert max(xs) - min(xs) > 300
    assert min(xs) >= 6, "label within 6px of the left edge"
    assert real.width - 1 - max(xs) >= 6, "label within 6px of the right edge"
