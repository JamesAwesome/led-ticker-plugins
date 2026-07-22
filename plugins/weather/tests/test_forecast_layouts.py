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
