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
    paging_dots(real, 4, 1, 0, 0, scale=2, dim_color=pal.LABEL, active_color=pal.SYM)
    # 4 dots drawn; the current (index 1) uses the brighter active color
    assert any(v == (255, 255, 255) for v in real._pixels.values())


def test_paging_dots_are_scale_sized_blocks_like_flight():
    # Each dot is a scale x scale block spaced 2*scale apart (matches the
    # flight tracker's paging-dot size/shape), not a single pixel.
    real = HeadlessBackend(64, 16).create_canvas()
    scale = 4
    paging_dots(
        real, 3, 0, 0, 0, scale=scale, dim_color=pal.LABEL, active_color=pal.SYM
    )
    active = {xy for xy, v in real._pixels.items() if v == (255, 255, 255)}
    # dot 0 (active) fills the full scale x scale block at the origin
    assert active == {(dx, dy) for dx in range(scale) for dy in range(scale)}
    # dot 1 starts one 2*scale step over (a gap between blocks)
    lit_x = {x for (x, y) in real._pixels}
    assert scale not in lit_x  # column `scale` is the gap before the next dot
    assert 2 * scale in lit_x  # dot 1 begins at 2*scale


def test_hires_substitutes_inter_missing_minus():
    # Inter (hi-res) has no glyph for U+2212 MINUS SIGN — the pre-fix
    # rasterization renders it pixel-for-pixel identical to "?" (tofu).
    # After the fix, hires() must substitute it with an ASCII hyphen-minus
    # so it renders as a real minus glyph, not a "?" box.
    def lit_pixels(text: str) -> set:
        c = _canvas()
        shim, real = phys_wrap(c)
        hires(shim, text, 4, 1, pal.SYM, 22, bold=True)
        return {k for k, v in real._pixels.items() if v != (0, 0, 0)}

    minus_sign = lit_pixels("−")  # U+2212 MINUS SIGN
    question_mark = lit_pixels("?")
    hyphen_minus = lit_pixels("-")  # ASCII hyphen-minus

    # This would FAIL pre-fix: U+2212 rasterized identically to "?" (tofu).
    assert minus_sign == hyphen_minus
    assert minus_sign != question_mark


def test_right_align_negative_ends_flush_like_positive():
    """`hires()` substitutes U+2212 MINUS SIGN -> ASCII hyphen-minus before
    drawing, but pre-fix `right_align_x()` measured the UN-substituted
    string — the minus sign's tofu-box advance differs from the real
    hyphen-minus glyph it's about to draw, so a right-aligned negative
    landed a couple px off the margin the positive case hits exactly.
    Assert both end at the SAME distance from the right edge."""
    c = _canvas()
    shim, real = phys_wrap(c)

    x_pos = right_align_x(22, "252.40", real.width, 4, bold=True)
    end_pos = hires(shim, "252.40", x_pos, 1, pal.PRICE, 22, bold=True)

    x_neg = right_align_x(22, "−252.40", real.width, 4, bold=True)  # U+2212
    end_neg = hires(shim, "−252.40", x_neg, 20, pal.PRICE, 22, bold=True)

    assert (x_pos + end_pos) == (x_neg + end_neg)


def test_hires_leaves_em_dash_unsubstituted():
    # U+2014 EM DASH (model._DASH, the no-data placeholder) IS present in
    # Inter and renders as its own distinct glyph — confirm it's neither
    # tofu ("?") nor coincidentally collapsed onto the hyphen-minus fix.
    def lit_pixels(text: str) -> set:
        c = _canvas()
        shim, real = phys_wrap(c)
        hires(shim, text, 4, 1, pal.SYM, 22, bold=True)
        return {k for k, v in real._pixels.items() if v != (0, 0, 0)}

    em_dash = lit_pixels("—")
    question_mark = lit_pixels("?")
    hyphen_minus = lit_pixels("-")

    assert em_dash != question_mark
    assert em_dash != hyphen_minus


def test_hires_lowers_threshold_so_thin_small_glyphs_render_whole():
    # At the default 128 threshold, Inter's thin strokes drop out at small
    # sizes (the "1" digit loses its stem). hires() uses a lower threshold so
    # sub-50%-coverage edge pixels survive — assert it lights MORE pixels than
    # a default-threshold render of the same small glyph would.
    from led_ticker.plugin import draw_text, resolve_font

    def hires_lit(text: str, size: int) -> int:
        c = _canvas()
        shim, real = phys_wrap(c)
        hires(shim, text, 2, 1, pal.SYM, size, bold=False)
        return sum(1 for v in real._pixels.values() if v != (0, 0, 0))

    def default_lit(text: str, size: int) -> int:
        c = _canvas()
        shim, real = phys_wrap(c)
        font = resolve_font("Inter-Regular", size, 128)  # core default threshold
        draw_text(shim, font, text, 2, 1 + font.ascent, pal.SYM)
        return sum(1 for v in real._pixels.values() if v != (0, 0, 0))

    # "1" at size 11 is the canonical dropout case; the lower threshold must
    # add pixels (the missing stem) vs the default. Would fail if hires()
    # reverted to the default threshold.
    assert hires_lit("111", 11) > default_lit("111", 11)
