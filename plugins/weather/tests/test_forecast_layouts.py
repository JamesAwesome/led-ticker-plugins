"""Per-sign forecast renderers. Hires text is asserted shape-level only
(never exact-pinned — freetype varies across platforms); lowres emoji
blits and dotted dividers are exact SetPixel math and may be pinned."""

from led_ticker_weather.forecast_data import DEMO_DATA
from led_ticker_weather.forecast_layouts import render_strip_small


def _colors(real, x0, y0, x1, y1):
    return {
        real.get_pixel(x, y)
        for y in range(y0, y1)
        for x in range(x0, x1)
        if real.get_pixel(x, y) != (0, 0, 0)
    }


class TestRenderStripSmall:
    def test_three_columns_of_content(self, smallsign):
        render_strip_small(smallsign, DEMO_DATA, "imperial")
        for i in range(3):
            x0 = 2 + i * 53
            assert _colors(smallsign, x0, 0, x0 + 50, 16), f"column {i} empty"

    def test_day_labels_amber_top_band(self, smallsign):
        render_strip_small(smallsign, DEMO_DATA, "imperial")
        # label band (rows 0-7) carries amber text right of the icon
        # (text block starts at x + _SMALL_TEXT_DX = 2 + 13 = 15)
        assert (255, 180, 0) in _colors(smallsign, 15, 0, 55, 8)

    def test_hi_lo_white_bottom_band(self, smallsign):
        render_strip_small(smallsign, DEMO_DATA, "imperial")
        assert (255, 255, 255) in _colors(smallsign, 15, 8, 55, 16)

    def test_icon_in_left_slot(self, smallsign):
        render_strip_small(smallsign, DEMO_DATA, "imperial")
        # today = partly -> partly_cloudy lowres sprite in rows 4-12
        assert _colors(smallsign, 2, 4, 16, 12)

    def test_dotted_separators_between_columns(self, smallsign):
        render_strip_small(smallsign, DEMO_DATA, "imperial")
        for i in range(2):
            sep_x = 2 + i * 53 + 53 - 3
            pts = [y for y in range(16) if smallsign.get_pixel(sep_x, y) != (0, 0, 0)]
            assert pts == list(range(2, 14, 2)), f"separator {i}"

    def test_degrades_below_three_columns_on_short_feed(self, smallsign):
        import attrs

        short = attrs.evolve(DEMO_DATA, days=DEMO_DATA.days[:1])
        render_strip_small(smallsign, short, "imperial")
        # columns 0-1 drawn, column 2 empty
        assert _colors(smallsign, 2, 0, 55, 16)
        assert not _colors(smallsign, 110, 0, 158, 16)

    def test_y_offset_shifts_content_down(self, smallsign):
        render_strip_small(smallsign, DEMO_DATA, "imperial", y_offset=4)
        assert not _colors(smallsign, 0, 0, 160, 4)

    def test_strip_worst_case_avoids_separator_collision(self, smallsign):
        """F1 regression: the widest hi/lo pair ('-99/-99', 7 chars at
        FONT_SMALL's advance) must clear the dotted separator instead of
        painting into it (the old _SMALL_TEXT_DX=17 collided here)."""
        import attrs

        from led_ticker_weather.palette import LABEL

        sep_color = tuple(int(c * 0.3) for c in LABEL)
        worst_cur = attrs.evolve(DEMO_DATA.current, hi_f=-99, lo_f=-99)
        worst_days = tuple(
            attrs.evolve(d, hi_f=-99, lo_f=-99) for d in DEMO_DATA.days[:2]
        )
        worst = attrs.evolve(DEMO_DATA, current=worst_cur, days=worst_days)
        render_strip_small(smallsign, worst, "imperial")

        for i in range(2):
            sep_x = 2 + i * 53 + 53 - 3
            next_x0 = 2 + (i + 1) * 53
            # from the separator column through the gap before the next
            # cell's icon, only the dim separator color may appear — no
            # text ink at or beyond the separator's x.
            region = _colors(smallsign, sep_x, 0, next_x0, 16)
            assert region == {sep_color}, f"separator {i}: {region}"

    def test_strip_icons_stay_lowres_through_scale1_wrapper(self):
        """A bigsign/longboi section with an explicit `scale = 1` override
        still wraps in a ScaledCanvas (core wraps whenever
        `scale > 1 OR content_height < canvas.height`) — core's hires gate
        on `draw_emoji_at` is `is_scaled(canvas)`, not `scale > 1`, so
        without `max_emoji_height=8` a 32x32 hires sprite would land in the
        strip's 8-logical-row icon slot instead of the curated 8x8 lowres
        one, overpainting neighboring text and spilling outside the
        vertically-centered 16-row content band."""
        from led_ticker.plugin import HeadlessBackend, ScaledCanvas

        real = HeadlessBackend(256, 64).create_canvas()
        canvas = ScaledCanvas(real, scale=1, content_height=16)
        render_strip_small(canvas, DEMO_DATA, "imperial")

        band_y0, band_y1 = canvas.y_offset_real, canvas.y_offset_real + 16
        # Nothing lit outside the vertically-centered 16-row content band.
        assert not _colors(real, 0, 0, real.width, band_y0)
        assert not _colors(real, 0, band_y1, real.width, real.height)

        # First icon slot has ink, but no more than an 8x8 sprite's worth
        # of lit pixels (a 32x32 hires sprite would light far more).
        icon_x0 = 2 + 3
        lit_count = sum(
            1
            for y in range(band_y0, band_y1)
            for x in range(icon_x0, icon_x0 + 8)
            if real.get_pixel(x, y) != (0, 0, 0)
        )
        assert 0 < lit_count <= 64


class TestStripCell:
    def _cell(self, real, geo, day=None):
        from led_ticker_weather.forecast_data import DayForecast
        from led_ticker_weather.forecast_layouts import _strip_cell
        from led_ticker_weather.paint import phys_wrap

        shim, unwrapped = phys_wrap(real)
        d = day or DayForecast(label="WED", kind="thunder", hi_f=79, lo_f=68, pop=60)
        _strip_cell(shim, unwrapped, 10.0, 33.5, d, geo, "imperial", 0)
        return unwrapped

    def test_big_geo_stacks_temps(self, bigsign, lit):
        from led_ticker.plugin import unwrap_to_real

        from led_ticker_weather.forecast_layouts import _BIG_GEO

        real = self._cell(unwrap_to_real(bigsign), _BIG_GEO)
        # warm hi in the tempY band, cool lo one line below (stacked)
        hi_band = {p for _, _, p in lit(real, 10, 37, 44, 49)}
        lo_band = {p for _, _, p in lit(real, 10, 49, 44, 61)}
        assert any(r > b for r, _, b in hi_band)  # warm-ish ink present
        assert any(b > r for r, _, b in lo_band)  # cool-ish ink present

    def test_big_geo_icon_is_16px_lowres_blit(self, bigsign, lit):
        from led_ticker.plugin import unwrap_to_real

        from led_ticker_weather.forecast_layouts import _BIG_GEO

        real = self._cell(unwrap_to_real(bigsign), _BIG_GEO)
        pts = lit(real, 10, _BIG_GEO.icon_y, 44, _BIG_GEO.icon_y + 16)
        assert pts  # icon ink in the 16px slot
        assert not lit(real, 10, _BIG_GEO.icon_y + 16, 44, 37)  # none below it

    def test_long_geo_horizontal_temps_and_pop(self, longboi, lit):
        from led_ticker.plugin import unwrap_to_real

        from led_ticker_weather.forecast_layouts import _LONG_GEO

        real = self._cell(unwrap_to_real(longboi), _LONG_GEO)
        assert lit(real, 10, _LONG_GEO.temp_y, 44, _LONG_GEO.temp_y + 12)
        # pop >= 50 renders cyan-ish (0,200,255): green+blue, no red
        pop_ink = {p for _, _, p in lit(real, 10, 52, 44, 62)}
        assert any(r == 0 and b > 0 for r, g, b in pop_ink)

    def test_long_geo_low_pop_is_dim_label(self, longboi, lit):
        from led_ticker.plugin import unwrap_to_real

        from led_ticker_weather.forecast_data import DayForecast
        from led_ticker_weather.forecast_layouts import _LONG_GEO

        d = DayForecast(label="SAT", kind="sunny", hi_f=83, lo_f=62, pop=5)
        real = self._cell(unwrap_to_real(longboi), _LONG_GEO, day=d)
        pop_ink = {p for _, _, p in lit(real, 10, 52, 44, 62)}
        assert pop_ink
        assert all(b >= g >= r for r, g, b in pop_ink)  # LABEL 70,90,130 ramp

    def test_day_label_amber_in_top_band(self, bigsign, lit):
        from led_ticker.plugin import unwrap_to_real

        from led_ticker_weather.forecast_layouts import _BIG_GEO

        real = self._cell(unwrap_to_real(bigsign), _BIG_GEO)
        ink = {p for _, _, p in lit(real, 10, 0, 44, 13)}
        assert any(r > 200 and g > 100 and b == 0 for r, g, b in ink)


class TestRenderHeroBig:
    def test_hero_and_strip_regions_populated(self, bigsign, lit):
        from led_ticker.plugin import unwrap_to_real

        from led_ticker_weather.forecast_layouts import render_hero_big

        render_hero_big(bigsign, DEMO_DATA, "imperial")
        real = unwrap_to_real(bigsign)
        assert lit(real, 4, 0, 40, 13)  # location label row
        assert lit(real, 40, 10, 110, 42)  # big current temp
        assert lit(real, 4, 12, 40, 46)  # hero icon (hires sprite)
        for i in range(4):  # four strip columns
            x0 = 118 + int(i * (252 - 118) / 4)
            assert lit(real, x0, 0, x0 + 33, 62), f"strip col {i}"

    def test_divider_dotted_at_x112(self, bigsign, lit):
        from led_ticker.plugin import unwrap_to_real

        from led_ticker_weather.forecast_layouts import render_hero_big

        render_hero_big(bigsign, DEMO_DATA, "imperial")
        real = unwrap_to_real(bigsign)
        xs = {(x, y) for x, y, _ in lit(real, 112, 6, 113, 58)}
        assert xs == {(112, y) for y in range(6, 58, 3)}

    def test_feels_line_cyan(self, bigsign, lit):
        from led_ticker.plugin import unwrap_to_real

        from led_ticker_weather.forecast_layouts import render_hero_big

        render_hero_big(bigsign, DEMO_DATA, "imperial")
        real = unwrap_to_real(bigsign)
        ink = {p for _, _, p in lit(real, 44, 50, 112, 64)}
        assert any(r == 0 and g > 100 and b > 200 for r, g, b in ink)

    def test_short_feed_widens_columns(self, bigsign, lit):
        import attrs
        from led_ticker.plugin import unwrap_to_real

        from led_ticker_weather.forecast_layouts import render_hero_big

        short = attrs.evolve(DEMO_DATA, days=DEMO_DATA.days[:2])
        render_hero_big(bigsign, short, "imperial")
        real = unwrap_to_real(bigsign)
        # two columns spanning the whole strip: content near both ends
        assert lit(real, 118, 0, 185, 62)
        assert lit(real, 185, 0, 252, 62)

    def test_no_days_draws_hero_only(self, bigsign, lit):
        import attrs
        from led_ticker.plugin import unwrap_to_real

        from led_ticker_weather.forecast_layouts import render_hero_big

        render_hero_big(bigsign, attrs.evolve(DEMO_DATA, days=()), "imperial")
        real = unwrap_to_real(bigsign)
        assert lit(real, 4, 0, 110, 62)
        assert not lit(real, 118, 0, 252, 62)


class TestRenderHeroLong:
    def test_hero_strip_and_divider(self, longboi, lit):
        from led_ticker.plugin import unwrap_to_real

        from led_ticker_weather.forecast_layouts import render_hero_long

        render_hero_long(longboi, DEMO_DATA, "imperial")
        real = unwrap_to_real(longboi)
        assert lit(real, 6, 0, 60, 14)  # location, left-justified
        assert lit(real, 70, 10, 160, 45)  # big temp pushed right
        xs = {(x, y) for x, y, _ in lit(real, 156, 6, 157, 58)}
        assert xs == {(156, y) for y in range(6, 58, 3)}
        for i in range(6):  # six strip columns
            x0 = 162 + int(i * (506 - 162) / 6)
            assert lit(real, x0, 0, x0 + 57, 62), f"strip col {i}"

    def test_location_ellipsizes_to_hero_width(self, longboi, lit):
        import attrs
        from led_ticker.plugin import unwrap_to_real

        from led_ticker_weather.forecast_layouts import render_hero_long

        wide = attrs.evolve(
            DEMO_DATA, location="SOUTH BURLINGTON INTERNATIONAL DISTRICT"
        )
        render_hero_long(longboi, wide, "imperial")
        real = unwrap_to_real(longboi)
        # never bleeds past the divider into the strip's label row.
        # x=156 is the divider's own column (its dots are mandated lit by
        # test_hero_strip_and_divider), so the check starts at x=157.
        assert not lit(real, 157, 0, 162, 13)

    def test_precip_row_present(self, longboi, lit):
        from led_ticker.plugin import unwrap_to_real

        from led_ticker_weather.forecast_layouts import render_hero_long

        render_hero_long(longboi, DEMO_DATA, "imperial")
        real = unwrap_to_real(longboi)
        assert lit(real, 162, 50, 506, 62)  # pop % row on every column


class TestWorstCaseCollision:
    """Spec Testing section: column-collision guard with worst-case content
    (widest temps `-99/-99`, `100%` pop) on both hires layouts — each
    column's ink must stay inside its own column band."""

    def _worst_data(self):
        import attrs

        from led_ticker_weather.forecast_data import DayForecast

        worst = tuple(
            DayForecast(label="WED", kind="thunder", hi_f=-99, lo_f=-99, pop=100)
            for _ in range(6)
        )
        cur = attrs.evolve(
            DEMO_DATA.current, temp_f=-99, feels_f=-99, hi_f=-99, lo_f=-99
        )
        return attrs.evolve(DEMO_DATA, current=cur, days=worst)

    @staticmethod
    def _column_gaps_clear(real, lit, x0, x1, n):
        cw = (x1 - x0) / n
        for i in range(1, n):
            edge = round(x0 + i * cw)
            # 1px gutter each side of every column boundary stays dark
            assert not lit(real, edge - 1, 0, edge + 1, 62), f"boundary {i}"

    def test_big_strip_columns_stay_separated(self, bigsign, lit):
        from led_ticker.plugin import unwrap_to_real

        from led_ticker_weather.forecast_layouts import render_hero_big

        render_hero_big(bigsign, self._worst_data(), "imperial")
        self._column_gaps_clear(unwrap_to_real(bigsign), lit, 118, 252, 4)

    def test_long_strip_columns_stay_separated(self, longboi, lit):
        from led_ticker.plugin import unwrap_to_real

        from led_ticker_weather.forecast_layouts import render_hero_long

        render_hero_long(longboi, self._worst_data(), "imperial")
        self._column_gaps_clear(unwrap_to_real(longboi), lit, 162, 506, 6)

    def test_big_hero_never_bleeds_into_strip(self, bigsign, lit):
        from led_ticker.plugin import unwrap_to_real

        from led_ticker_weather.forecast_layouts import render_hero_big

        render_hero_big(bigsign, self._worst_data(), "imperial")
        # nothing between the divider (112) and the strip origin (118)
        assert not lit(unwrap_to_real(bigsign), 113, 0, 118, 62)


class TestHeroYOffsetContract:
    """F2: pin the y_offset contract per hero renderer. Both mutations that
    escaped the existing suite — dropping `+ oy` from one hires() call, or
    passing raw `y_offset` instead of `oy = y_offset * safe_scale(canvas)`
    (unscaled) — must fail one of these tests: dropping `+ oy` leaves that
    call's ink un-shifted (present at the y_offset=0 position instead of
    +8), and unscaling leaves it shifted by only 2 physical rows instead
    of 8, so in both cases the shifted snapshot no longer equals the base
    snapshot translated down exactly 8 physical rows (2 logical rows *
    bigsign/longboi scale 4)."""

    _SHIFT_ROWS = 8  # y_offset=2 * scale=4

    @staticmethod
    def _render_at(render_fn, width, height, y_offset):
        from led_ticker.plugin import HeadlessBackend, ScaledCanvas

        from led_ticker_weather.forecast_data import DEMO_DATA

        real = HeadlessBackend(width, height).create_canvas()
        canvas = ScaledCanvas(real, scale=4, content_height=16)
        render_fn(canvas, DEMO_DATA, "imperial", y_offset=y_offset)
        return real

    def _assert_shifts_uniformly(self, render_fn, width, height, lit):
        real0 = self._render_at(render_fn, width, height, 0)
        real2 = self._render_at(render_fn, width, height, self._SHIFT_ROWS // 4)

        base = lit(real0, 0, 0, width, height)
        assert base, "nothing rendered at y_offset=0"
        shifted = set(lit(real2, 0, 0, width, height))

        # translate every base pixel down by the fixed shift; a pixel
        # whose target row would clip past the bottom edge is dropped
        # from the expectation rather than asserted absent-or-present.
        expected = {
            (x, y + self._SHIFT_ROWS, c)
            for x, y, c in base
            if y + self._SHIFT_ROWS < height
        }
        assert shifted == expected

    def test_render_hero_big_y_offset_shifts_8_physical_rows(self, lit):
        from led_ticker_weather.forecast_layouts import render_hero_big

        self._assert_shifts_uniformly(render_hero_big, 256, 64, lit)

    def test_render_hero_long_y_offset_shifts_8_physical_rows(self, lit):
        from led_ticker_weather.forecast_layouts import render_hero_long

        self._assert_shifts_uniformly(render_hero_long, 512, 64, lit)


class TestHeroIconKindSelection:
    """F3: pin that `_hero_icon` reads KIND_SLUGS[kind][1] (the HIRES
    column), not [0] (lowres) — a tuple-order-swap mutation escaped the
    existing suite because demo's current kind ("partly") has identical
    lowres/hires slugs. "overcast" (hires: sun_behind_large_cloud, a pack
    sprite) vs "cloudy" (hires: cloud, curated) draw visibly different
    hero icons only when the hires column is the one read."""

    def test_overcast_and_cloudy_render_different_hero_icons(self, lit):
        import attrs
        from led_ticker.plugin import HeadlessBackend, ScaledCanvas

        from led_ticker_weather.forecast_layouts import render_hero_big

        def _icon_pixels(kind):
            real = HeadlessBackend(256, 64).create_canvas()
            canvas = ScaledCanvas(real, scale=4, content_height=16)
            data = attrs.evolve(
                DEMO_DATA, current=attrs.evolve(DEMO_DATA.current, kind=kind)
            )
            render_hero_big(canvas, data, "imperial")
            return {(x, y) for x, y, _ in lit(real, 4, 12, 40, 46)}

        overcast = _icon_pixels("overcast")
        cloudy = _icon_pixels("cloudy")
        assert overcast, "overcast hero icon region empty"
        assert cloudy, "cloudy hero icon region empty"
        assert overcast != cloudy
