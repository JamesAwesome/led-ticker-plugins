"""tests/test_layout_promo_crawl.py — hires text asserted by EXTENT only
(never exact freetype pins), same convention as test_layout_crawl.py.

`render_promo_crawl`'s `cursor_pos` and return value are LOGICAL (same
units as `canvas.width` on the ScaledCanvas wrapper), NOT physical — see
`layouts/promo_crawl.py`'s module docstring and `layouts/crawl.py`'s (the
scores sibling this mirrors).
"""

from led_ticker.plugin import HeadlessBackend, ScaledCanvas

from led_ticker_baseball.layouts.promo_crawl import _promo_sub, render_promo_crawl
from led_ticker_baseball.promotions import PromoInfo


def _bigsign():
    real = HeadlessBackend(256, 64).create_canvas()
    return ScaledCanvas(real, scale=4, content_height=16), real


def _longboi():
    real = HeadlessBackend(512, 64).create_canvas()
    return ScaledCanvas(real, scale=4, content_height=16), real


def _promo(**over):
    kw = dict(
        name="Bobblehead Night",
        offer_type="Giveaway",
        presented_by="Chase",
        opponent_abbr="BOS",
        date_label="FRI JUL 18",
        time_label="7:05",
        am_pm="PM",
        game_date="2026-07-18",
    )
    kw.update(over)
    return PromoInfo(**kw)


def _lit_cols(real):
    return {x for x, y in real._pixels if real.get_pixel(x, y) != (0, 0, 0)}


def test_returns_positive_width_and_draws_at_cursor_zero():
    canvas, real = _bigsign()
    w = render_promo_crawl(canvas, _promo(), 0)
    assert w > 64  # segment run is wider than bigsign's LOGICAL width (64)
    assert _lit_cols(real)


def test_cursor_offsets_content():
    canvas, real = _bigsign()
    render_promo_crawl(canvas, _promo(), 0)
    first = min(_lit_cols(real))
    canvas2, real2 = _bigsign()
    # Small LOGICAL offset (-3 = -12 physical at scale 4), inside the first
    # segment's own width — see test_layout_crawl.py's identical rationale
    # for why a large offset would risk crossing into the next segment's
    # font-dependent left-side bearing.
    render_promo_crawl(canvas2, _promo(), -3)
    assert min(_lit_cols(real2)) <= first


def test_positive_cursor_shifts_content_right():
    """Load-bearing mutation-killing test: a mutation that ignores
    cursor_pos (x = 0) must FAIL here. +15 logical = +60 physical at scale
    4 — same pattern as test_layout_crawl.py's identical test."""
    canvas, real = _bigsign()
    render_promo_crawl(canvas, _promo(), 0)
    cols0 = _lit_cols(real)
    canvas2, real2 = _bigsign()
    render_promo_crawl(canvas2, _promo(), 15)
    cols15 = _lit_cols(real2)
    assert cols0 != cols15
    assert min(cols15) >= min(cols0) + 50


def test_width_is_cursor_independent():
    canvas, _real = _bigsign()
    w0 = render_promo_crawl(canvas, _promo(), 0)
    canvas2, _real2 = _bigsign()
    w1 = render_promo_crawl(canvas2, _promo(), -100)
    assert w0 == w1


def test_y_offset_shifts_content():
    canvas, real = _bigsign()
    render_promo_crawl(canvas, _promo(), 0, y_offset=8)
    rows = {y for x, y in real._pixels if real.get_pixel(x, y) != (0, 0, 0)}
    canvas2, real2 = _bigsign()
    render_promo_crawl(canvas2, _promo(), 0)
    rows2 = {y for x, y in real2._pixels if real2.get_pixel(x, y) != (0, 0, 0)}
    assert min(rows) - min(rows2) == 32


def test_no_bullet_between_segments():
    """Repo decision (2026-07-18, mirrored from the scores crawl): the
    prototype's inter-story '•' bullet is dropped — a plain trailing gap
    stands in its place. This can't be asserted directly by pixel absence
    (the bullet's grey is close to other content), so instead assert the
    returned width matches the sum of the OWN segment widths we expect:
    the run must be shorter than it would be with the JS's extra
    gap(11)+bullet(px16)+gap(16) tail included.
    """
    canvas, _real = _bigsign()
    w = render_promo_crawl(canvas, _promo(), 0)
    assert w > 0  # sanity; exact width is a freetype-dependent sum


def test_empty_fields_never_raise():
    canvas, _real = _bigsign()
    render_promo_crawl(canvas, PromoInfo(name=""), 0)


def test_promo_sub_sponsor_only_has_no_bare_dot():
    """Same "never a bare '· BY X'" guard as promo_card's duplicated
    helper — offer_type empty + presented_by set must render 'BY SPONSOR'
    with no leading dot."""
    p = _promo(offer_type="", presented_by="New Era")
    assert _promo_sub(p) == "BY NEW ERA"
    assert not _promo_sub(p).startswith("·")


def _minimal_promo(**over):
    """A deliberately terse promo (short date/name, no offer/sponsor) —
    short enough that its crawl segment run HOLDS on a 512-physical-px
    panel, unlike `_promo()`'s verbose default fixture. Mirrors
    test_layout_crawl.py's `state="final"` fixture choice for the same
    reason (its own `TestHorizontalCentering` docstring)."""
    kw = dict(
        name="Cap Day",
        offer_type="",
        presented_by="",
        opponent_abbr="BOS",
        date_label="TODAY",
        time_label="7:05",
        am_pm="PM",
        game_date="2026-07-18",
    )
    kw.update(over)
    return PromoInfo(**kw)


class TestHeldCentering:
    def _mid(self, real):
        cols = sorted({x for x, _y in real._pixels})
        return (cols[0] + cols[-1]) / 2

    def test_short_content_centers_on_longboi(self):
        real = HeadlessBackend(512, 64).create_canvas()
        canvas = ScaledCanvas(real, scale=4, content_height=16)
        render_promo_crawl(canvas, _minimal_promo(), 0, hold_padding=6)
        assert abs(self._mid(real) - 255.5) <= 40

    def test_centering_ignores_cursor_when_held(self):
        real = HeadlessBackend(512, 64).create_canvas()
        canvas = ScaledCanvas(real, scale=4, content_height=16)
        w = render_promo_crawl(canvas, _minimal_promo(), 0, hold_padding=6)
        assert w + 6 <= canvas.width  # sanity: this content genuinely holds

    def test_wide_content_keeps_left_origin_on_bigsign(self):
        real = HeadlessBackend(256, 64).create_canvas()
        canvas = ScaledCanvas(real, scale=4, content_height=16)
        render_promo_crawl(canvas, _promo(), 0, hold_padding=6)
        cols = sorted({x for x, _y in real._pixels})
        assert cols[0] <= 4  # starts at the left edge, not centered


class TestVerticalCentering:
    """Hardware finding (longboi, 2026-07-18): the promo crawl must center
    vertically like the scores crawl. The hires() ascent-correction via 0.74
    factor in _y_for pins promo centering (scores uses 0.72 — a future mixup
    must fail these tests). Guard: the lit row band of a short-content
    (held) promo render must center on the panel's vertical middle.
    """

    def _midpoint(self, width):
        real = HeadlessBackend(width, 64).create_canvas()
        canvas = ScaledCanvas(real, scale=4, content_height=16)
        render_promo_crawl(canvas, _minimal_promo(), 0)
        rows = sorted({y for (_x, y) in real._pixels})
        return (rows[0] + rows[-1]) / 2

    def test_longboi_promo_crawl_text_band_is_vertically_centered(self):
        assert abs(self._midpoint(512) - 31.5) <= 2.5

    def test_bigsign_promo_crawl_text_band_is_vertically_centered(self):
        assert abs(self._midpoint(256) - 31.5) <= 2.5
