import pytest

from led_ticker_weather.forecast import VALID_LAYOUTS, resolve_forecast_layout


class TestResolveForecastLayout:
    @pytest.mark.parametrize(
        ("cfg", "scale", "phys_w", "expect"),
        [
            # scale 1: always strip, whatever the config asked for
            ("auto", 1, 160, "strip"),
            ("big", 1, 160, "strip"),
            ("long", 1, 160, "strip"),
            ("strip", 1, 160, "strip"),
            # auto at scale > 1 splits on the 400px physical-width threshold
            ("auto", 4, 256, "big"),
            ("auto", 4, 512, "long"),
            ("auto", 4, 400, "long"),  # boundary: >= 400 is wide
            # explicit names honored at scale > 1 ...
            ("big", 4, 512, "big"),
            ("strip", 4, 256, "strip"),  # logical-coord draw works anywhere
            ("long", 4, 512, "long"),
            # ... with ONE width-fit degrade (baseball Finding-3 pattern):
            # explicit long on a narrow panel would draw mostly off-panel
            ("long", 4, 256, "big"),
        ],
    )
    def test_table(self, cfg, scale, phys_w, expect):
        assert resolve_forecast_layout(cfg, scale, phys_w) == expect

    def test_valid_layouts_constant(self):
        assert VALID_LAYOUTS == ("auto", "strip", "big", "long")
