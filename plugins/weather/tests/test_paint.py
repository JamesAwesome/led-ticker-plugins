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


class TestBlitEmojiScaled:
    def test_k1_matches_direct_draw(self, lit):
        from led_ticker.plugin import HeadlessBackend, draw_emoji_at

        direct = HeadlessBackend(16, 8).create_canvas()
        draw_emoji_at(direct, "sun", 0, 0)
        blitted = HeadlessBackend(16, 8).create_canvas()
        paint.blit_emoji_scaled(blitted, "sun", 0, 0, 1)
        for y in range(8):
            for x in range(8):
                assert blitted.get_pixel(x, y) == direct.get_pixel(x, y)

    def test_k2_expands_each_pixel_to_2x2(self):
        from led_ticker.plugin import HeadlessBackend

        one = HeadlessBackend(16, 8).create_canvas()
        paint.blit_emoji_scaled(one, "rain", 0, 0, 1)
        two = HeadlessBackend(32, 16).create_canvas()
        paint.blit_emoji_scaled(two, "rain", 0, 0, 2)
        for y in range(8):
            for x in range(8):
                p = one.get_pixel(x, y)
                for j in range(2):
                    for i in range(2):
                        assert two.get_pixel(x * 2 + i, y * 2 + j) == p

    def test_offset_and_bounds_clip(self):
        from led_ticker.plugin import HeadlessBackend

        real = HeadlessBackend(20, 20).create_canvas()
        # 8*3=24 wide from x=10 overflows a 20-wide canvas: must not raise
        paint.blit_emoji_scaled(real, "sun", 10, 10, 3)
        assert real.count_nonzero() > 0

    def test_every_curated_weather_slug_blits(self):
        from led_ticker.plugin import HeadlessBackend

        for slug in (
            "sun",
            "moon",
            "cloud",
            "partly_cloudy",
            "rain",
            "snow",
            "thunder",
            "fog",
        ):
            real = HeadlessBackend(16, 8).create_canvas()
            paint.blit_emoji_scaled(real, slug, 0, 0, 1)
            assert real.count_nonzero() > 0, slug


class TestBlitHiresDownscaled:
    def test_downscales_hires_sprite_into_target_box(self):
        from led_ticker.plugin import HeadlessBackend

        real = HeadlessBackend(24, 24).create_canvas()
        paint.blit_hires_downscaled(real, "sun", 0, 0, 24)
        # A 32x32 sun downscaled to 24 lights a substantial share of the box.
        assert real.count_nonzero() > 24 * 24 * 0.15

    def test_target_16_fits_and_lights(self):
        from led_ticker.plugin import HeadlessBackend

        real = HeadlessBackend(16, 16).create_canvas()
        paint.blit_hires_downscaled(real, "rain", 0, 0, 16)
        assert real.count_nonzero() > 0
        # Nothing drawn outside the 16x16 box.
        big = HeadlessBackend(40, 40).create_canvas()
        paint.blit_hires_downscaled(big, "rain", 0, 0, 16)
        for y in range(40):
            for x in range(40):
                if x >= 16 or y >= 16:
                    assert big.get_pixel(x, y) == (0, 0, 0)

    def test_offset_and_bounds_clip_no_raise(self):
        from led_ticker.plugin import HeadlessBackend

        real = HeadlessBackend(20, 20).create_canvas()
        paint.blit_hires_downscaled(real, "sun", 8, 8, 24)  # overflows: must not raise
        assert real.count_nonzero() > 0

    def test_every_hero_hires_slug_downscales(self):
        from led_ticker.plugin import HeadlessBackend

        from led_ticker_weather.forecast_data import KIND_SLUGS

        for _, hires_slug in KIND_SLUGS.values():
            real = HeadlessBackend(24, 24).create_canvas()
            paint.blit_hires_downscaled(real, hires_slug, 0, 0, 24)
            assert real.count_nonzero() > 0, hires_slug

    def test_downscale_compute_is_cached(self):
        from led_ticker.plugin import HeadlessBackend

        paint._downscaled_pixels.cache_clear()
        real = HeadlessBackend(24, 24).create_canvas()
        paint.blit_hires_downscaled(real, "sun", 0, 0, 24)
        misses_after_first = paint._downscaled_pixels.cache_info().misses
        assert misses_after_first == 1

        # Repeat calls (including at a different x/y offset) must hit the
        # cache rather than recomputing the downscale.
        paint.blit_hires_downscaled(real, "sun", 4, 4, 24)
        paint.blit_hires_downscaled(real, "sun", 0, 0, 24)
        info = paint._downscaled_pixels.cache_info()
        assert info.misses == misses_after_first
        assert info.hits >= 2


class TestCenterGroupX:
    def test_full_count_fills_from_x0(self):
        # 6 cells of pitch 57 across a 344 span starting at 162: ~x0.
        xs = paint.center_group_x(162, 506, 6, (506 - 162) / 6)
        assert xs[0] == 162
        assert xs[-1] == paint.js_round(162 + 5 * ((506 - 162) / 6))

    def test_fewer_cells_center_symmetrically(self):
        pitch = (506 - 162) / 6
        xs = paint.center_group_x(162, 506, 3, pitch)
        left_margin = xs[0] - 162
        right_margin = 506 - (xs[-1] + pitch)
        assert abs(left_margin - right_margin) <= 1

    def test_single_cell_centered(self):
        xs = paint.center_group_x(0, 160, 1, 53)
        assert xs == [paint.js_round((160 - 53) / 2)]

    def test_returns_n_positions(self):
        assert len(paint.center_group_x(0, 200, 4, 40)) == 4


class TestSpreadCellsX:
    # longboi strip geometry: x0=162, x1=506, design pitch (6 slots) ≈ 57.3,
    # icon cell 24. cap = 2*57.3 ≈ 114.7.
    X0, X1, DP, CW = 162, 506, (506 - 162) / 6, 24

    def test_justify_hugs_both_edges(self):
        # 6 days: ideal spacing 64 <= cap 114.7 -> justify. First cell's left
        # edge sits at x0, last cell's right edge at x1 (±1 rounding).
        xs = paint.spread_cells_x(self.X0, self.X1, 6, self.CW, self.DP)
        assert abs(xs[0] - self.X0) <= 1
        assert abs((xs[-1] + self.CW) - self.X1) <= 1

    def test_justify_reaches_further_than_center_group(self):
        # 4 days justify (ideal 106.7 <= cap 114.7). The discriminator vs the
        # old center-group fill: spread's last cell reaches the strip's right
        # edge, center_group leaves it well short.
        spread = paint.spread_cells_x(self.X0, self.X1, 4, self.CW, self.DP)
        cg = paint.center_group_x(self.X0, self.X1, 4, self.DP)
        assert abs((spread[-1] + self.CW) - self.X1) <= 1  # spread hugs x1
        assert (cg[-1] + self.DP) < self.X1 - 40  # center-group stops short

    def test_sparse_feed_caps_and_centers(self):
        # 2 days: ideal 320 > cap 114.7 -> cap the spacing, center the pair.
        xs = paint.spread_cells_x(self.X0, self.X1, 2, self.CW, self.DP)
        c0 = xs[0] + self.CW / 2
        c1 = xs[1] + self.CW / 2
        assert abs((c1 - c0) - 2 * self.DP) <= 1  # spacing capped at 2*pitch
        midpoint = (c0 + c1) / 2
        assert abs(midpoint - (self.X0 + self.X1) / 2) <= 1  # centered

    def test_single_cell_centered(self):
        xs = paint.spread_cells_x(self.X0, self.X1, 1, self.CW, self.DP)
        assert xs == [paint.js_round((self.X0 + self.X1) / 2 - self.CW / 2)]

    def test_empty_when_no_cells(self):
        assert paint.spread_cells_x(self.X0, self.X1, 0, self.CW, self.DP) == []


class TestSpleen:
    def test_width_is_monospace_6px(self):
        assert paint.spleen_width("86/66") == 30
        assert paint.spleen_width("") == 0

    def test_advance_equals_width(self, bigsign):
        # call form: spleen(shim, text, x, y_top, rgb)
        shim, _ = paint.phys_wrap(bigsign)
        adv = paint.spleen(shim, "80°", 5, 5, IDENT)
        assert adv == paint.spleen_width("80°") == 18

    def test_ink_top_is_y_top_no_cap_top(self, bigsign, lit):
        # Digits, uppercase, %, ° rasterize with ink-top at y_top (the
        # forecast's content set). Measured; guards no-cap_top assumption.
        # / and lowercase sit ±1px per font's per-glyph bbox (not drawn here).
        shim, real = paint.phys_wrap(bigsign)
        for char, x_start in [("8", 4), ("T", 20)]:
            paint.spleen(shim, char, x_start, 20, IDENT)
            pts = lit(real, x_start, 0, x_start + 12, 64)
            assert pts, f"no pixels for glyph {char!r}"
            top = min(y for _, y, _ in pts)
            assert top == 20, f"glyph '{char}' ink-top at {top}, expected 20"

    def test_center_positions_symmetrically(self, bigsign, lit):
        shim, real = paint.phys_wrap(bigsign)
        paint.spleen_center(shim, "88", 100, 10, IDENT)  # width 12 -> x 94..106
        xs = [x for x, _, _ in lit(real, 0, 0, 256, 64)]
        assert min(xs) >= 94 and max(xs) <= 106

    def test_segs_render_each_color(self, bigsign, lit):
        shim, real = paint.phys_wrap(bigsign)
        paint.spleen_segs(shim, [("8", HI), ("/", LABEL), ("6", LO)], 100, 10)
        colors = {p for _, _, p in lit(real, 0, 0, 256, 64)}
        # HI is warm (r>b), LO is cool (b>r): both segments rendered.
        assert any(c[0] > c[2] for c in colors)  # warm (HI) present
        assert any(c[2] > c[0] for c in colors)  # cool (LO) present
