"""tests/test_mask.py — masked text blits + clipped scroll (`_mask.py`).

Hi-res text is asserted by EXTENT/membership, never exact freetype pins
(same convention as test_paint.py / the layout suites) — EXCEPT the width
assertion, which compares against `_paint.text_width`'s own return (the same
freetype call both sides make, so it can't drift independently of a font
update).

HeadlessCanvas's supported read surface is `get_pixel(x, y)`; this test file
also reaches into `_pixels` directly for "any lit pixel" / "lit in region"
checks, following the precedent in test_paint.py / test_primitives.py /
test_layout_crawl.py.
"""

from led_ticker.plugin import HeadlessBackend

from led_ticker_baseball import _mask, _paint
from led_ticker_baseball import _palette as pal


def _real(w=256, h=64):
    return HeadlessBackend(w, h).create_canvas()


def _lit(real):
    return {xy for xy, v in real._pixels.items() if v != (0, 0, 0)}


def _lit_in_cols(real, x0, x1):
    return {(x, y) for (x, y) in _lit(real) if x0 <= x < x1}


def _lit_outside_cols(real, x0, x1):
    return {(x, y) for (x, y) in _lit(real) if not (x0 <= x < x1)}


def test_mask_width_matches_text_width():
    mask = _mask.text_mask("HELLO", 16)
    assert mask.w == _paint.text_width(16, "HELLO", bold=True)


def test_mask_width_matches_text_width_regular_weight():
    mask = _mask.text_mask("HELLO", 16, bold=False)
    assert mask.w == _paint.text_width(16, "HELLO", bold=False)


def test_mask_has_lit_pixels():
    mask = _mask.text_mask("10", 20)
    assert len(mask.pixels) > 0


def test_lru_cache_returns_same_object_for_repeated_args():
    a = _mask.text_mask("SAME TEXT", 18, bold=True)
    b = _mask.text_mask("SAME TEXT", 18, bold=True)
    assert a is b


def test_lru_cache_distinguishes_bold():
    a = _mask.text_mask("SAME TEXT", 18, bold=True)
    b = _mask.text_mask("SAME TEXT", 18, bold=False)
    assert a is not b


def test_blit_clips_hard_at_band_edges():
    """A wide string blitted into a narrow band must show ZERO lit pixels
    outside [x0, x1) and at least one lit pixel inside it."""
    real = _real(w=320, h=64)
    text = "HAWAIIAN SHIRT & BEACH TOWEL GIVEAWAY"
    mask = _mask.text_mask(text, 22)
    assert mask.w > 100  # sanity: this string is much wider than the band
    x0, x1 = 40, 90
    _mask.blit_mask(real, mask, x0, 20, pal.IDENT, x0=x0, x1=x1)
    assert _lit_outside_cols(real, x0, x1) == set()
    assert len(_lit_in_cols(real, x0, x1)) > 0


def test_fitting_text_is_static_and_starts_at_x0():
    """mask.w <= region: two different clocks render byte-identical frames,
    and the leftmost lit column sits at x0 (no scroll offset applied)."""
    real_a = _real()
    real_b = _real()
    text = "HI"
    x0, x1 = 10, 200
    _mask.mask_scroll(real_a, text, x0, x1, 5, pal.IDENT, 16, 0)
    _mask.mask_scroll(real_b, text, x0, x1, 5, pal.IDENT, 16, 999_999)
    assert real_a._pixels == real_b._pixels
    lit = _lit(real_a)
    assert lit  # sanity: something was drawn
    # Leftmost lit column sits at x0 (no scroll offset) — allow a couple px
    # of slack for the glyph's own left-side bearing (freetype rasterizer
    # detail, not a mask-positioning bug).
    leftmost = min(x for x, _y in lit)
    assert x0 <= leftmost <= x0 + 3


def test_overflowing_text_scrolls_and_stays_in_band():
    """mask.w > region: different clocks must produce different frames, and
    across many sampled clocks no lit pixel ever escapes [x0, x1)."""
    real_ref = _real()
    text = "HAWAIIAN SHIRT & BEACH TOWEL GIVEAWAY"
    x0, x1 = 6, 150
    _mask.mask_scroll(real_ref, text, x0, x1, 18, pal.IDENT, 22, 0)
    ref_pixels = dict(real_ref._pixels)

    differed = False
    for i in range(10):
        clock_ms = i * 1237  # arbitrary, non-multiple-of-period spacing
        real = _real()
        _mask.mask_scroll(real, text, x0, x1, 18, pal.IDENT, 22, clock_ms)
        assert _lit_outside_cols(real, x0, x1) == set(), (
            f"scroll escaped band at clock_ms={clock_ms}"
        )
        if dict(real._pixels) != ref_pixels:
            differed = True
    assert differed, "10 sampled clocks produced identical frames — not scrolling"


def test_brightness_dims_channels_exactly():
    real_full = _real()
    real_dim = _real()
    mask = _mask.text_mask("10", 20)
    _mask.blit_mask(real_full, mask, 5, 5, pal.IDENT, x0=0, x1=256, brightness=1.0)
    _mask.blit_mask(real_dim, mask, 5, 5, pal.IDENT, x0=0, x1=256, brightness=0.5)
    for dx, dy in mask.pixels:
        x, y = 5 + dx, 5 + dy
        full = real_full.get_pixel(x, y)
        dimmed = real_dim.get_pixel(x, y)
        expect = (
            pal.dim(pal.IDENT, 0.5).red,
            pal.dim(pal.IDENT, 0.5).green,
            pal.dim(pal.IDENT, 0.5).blue,
        )
        assert dimmed == expect
        assert full == (255, 255, 255)
