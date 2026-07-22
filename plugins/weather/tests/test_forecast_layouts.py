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
        assert (255, 180, 0) in _colors(smallsign, 19, 0, 55, 8)

    def test_hi_lo_white_bottom_band(self, smallsign):
        render_strip_small(smallsign, DEMO_DATA, "imperial")
        assert (255, 255, 255) in _colors(smallsign, 19, 8, 55, 16)

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
