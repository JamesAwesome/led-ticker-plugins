"""paint.py helpers — ported from baseball _paint.py (see that module's
docstrings for the cap-top derivation)."""

from led_ticker_weather import paint
from led_ticker_weather.palette import AMBER, CYAN, HI, IDENT, LABEL, LO


class TestJsRound:
    def test_half_up_at_boundary(self):
        assert paint.js_round(2.5) == 3  # Python round() would give 2

    def test_negative_half(self):
        assert paint.js_round(-2.5) == -2  # JS Math.round(-2.5) == -2

    def test_plain_values(self):
        assert paint.js_round(2.4) == 2
        assert paint.js_round(2.6) == 3


class TestCapTop:
    def test_formula(self):
        # y_target - size + js_round(size * 0.72), the baseball formula
        assert paint.cap_top(13, 27) == 13 - 27 + paint.js_round(27 * 0.72)

    def test_shifts_up(self):
        assert paint.cap_top(10, 12) < 10


class TestPalette:
    def test_semantic_tokens_match_handoff(self):
        assert IDENT == (255, 255, 255)
        assert LABEL == (70, 90, 130)
        assert AMBER == (255, 180, 0)
        assert HI == (255, 148, 36)
        assert LO == (70, 180, 255)
        assert CYAN == (0, 200, 255)


class TestPx:
    def test_sets_pixel_with_brightness(self, smallsign):
        paint.px(smallsign, 3, 4, (200, 100, 50), 0.5)
        assert smallsign.get_pixel(3, 4) == (100, 50, 25)

    def test_out_of_bounds_is_noop(self, smallsign):
        paint.px(smallsign, -1, 0, (255, 255, 255))
        paint.px(smallsign, 160, 0, (255, 255, 255))
        paint.px(smallsign, 0, 16, (255, 255, 255))
        assert smallsign.count_nonzero() == 0


class TestHires:
    def test_draws_ink_and_returns_positive_advance(self, bigsign, lit):
        shim, real = paint.phys_wrap(bigsign)
        adv = paint.hires(shim, "78", 10, 10, IDENT, 20)
        assert adv > 0
        assert lit(real, 10, 10, 10 + adv + 2, 40)  # shape-level, never exact-pin

    def test_advance_is_relative_not_absolute(self, bigsign):
        shim, _ = paint.phys_wrap(bigsign)
        a0 = paint.hires(shim, "78", 0, 10, IDENT, 20)
        a50 = paint.hires(shim, "78", 50, 10, IDENT, 20)
        assert a0 == a50  # advance width, not end-x


class TestTextWidth:
    def test_matches_hires_advance(self, bigsign):
        shim, _ = paint.phys_wrap(bigsign)
        assert paint.text_width(20, "78/64") == paint.hires(
            shim, "78/64", 0, 10, IDENT, 20
        )

    def test_wider_text_measures_wider(self):
        assert paint.text_width(12, "100") > paint.text_width(12, "7")


class TestFitText:
    def test_fits_unchanged(self):
        assert paint.fit_text("BOS", 500, 11) == "BOS"

    def test_truncates_with_ellipsis(self):
        long = "SOUTH BURLINGTON HEIGHTS"
        out = paint.fit_text(long, 60, 11)
        assert out.endswith("…")
        assert paint.text_width(11, out) <= 60

    def test_strips_trailing_space_before_ellipsis(self):
        out = paint.fit_text("AB CDEFGHIJ", 30, 11)
        assert " …" not in out


class TestVdivider:
    def test_dotted_every_third_row(self, bigsign, lit):
        _, real = paint.phys_wrap(bigsign)
        paint.vdivider(real, 112, 6, 58)
        pts = lit(real, 112, 6, 113, 58)
        assert [(x, y) for x, y, _ in pts] == [(112, y) for y in range(6, 58, 3)]

    def test_dim_label_color(self, bigsign):
        _, real = paint.phys_wrap(bigsign)
        paint.vdivider(real, 112, 6, 58)
        r, g, b = real.get_pixel(112, 6)
        assert (r, g, b) == (int(70 * 0.4), int(90 * 0.4), int(130 * 0.4))
