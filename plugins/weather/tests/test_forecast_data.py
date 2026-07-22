"""forecast_data: condition-code mapping + slug tables (+ later: models,
parsing, demo data)."""

import pytest

from led_ticker_weather.forecast_data import KIND_SLUGS, cond_kind


class TestCondKind:
    """Per-code-band tripwires for the handoff condKind table
    (design/README.md Data Sources section)."""

    @pytest.mark.parametrize(
        ("code", "is_day", "kind"),
        [
            (1000, 1, "sunny"),
            (1000, 0, "clear"),
            (1003, 1, "partly"),
            (1003, 0, "partly_night"),
            (1006, 1, "cloudy"),
            (1006, 0, "cloudy"),  # night swap only applies to 1000/1003
            (1009, 1, "overcast"),
            (1030, 1, "fog"),
            (1135, 1, "fog"),
            (1147, 1, "fog"),
            (1063, 1, "rain_patchy"),  # patchy rain possible
            (1150, 1, "rain_patchy"),  # patchy light drizzle
            (1183, 1, "rain_patchy"),  # light rain
            (1240, 1, "rain_patchy"),  # light rain shower
            (1186, 1, "rain"),  # moderate rain at times
            (1201, 1, "rain"),  # heavy freezing rain
            (1243, 1, "rain"),  # moderate/heavy rain shower
            (1246, 1, "rain"),  # torrential rain shower
            (1066, 1, "snow"),
            (1114, 1, "snow"),
            (1210, 1, "snow"),
            (1225, 1, "snow"),
            (1255, 1, "snow"),
            (1258, 1, "snow"),
            (1087, 1, "thunder"),
            (1273, 1, "thunder"),
            (1282, 1, "thunder"),
            (9999, 1, "cloudy"),  # unknown code -> handoff drawIcon default
        ],
    )
    def test_code_band(self, code, is_day, kind):
        assert cond_kind(code, is_day) == kind


class TestKindSlugs:
    def test_every_kind_has_an_entry(self):
        kinds = {
            "sunny", "clear", "partly", "partly_night", "cloudy",
            "overcast", "rain", "rain_patchy", "thunder", "snow", "fog",
        }
        assert set(KIND_SLUGS) == kinds

    def test_lowres_slugs_exist_in_both_curated_registries(self):
        # Strip icons blit the lowres sprite; heroes may fall back to it.
        from led_ticker import pixel_emoji

        lowres = pixel_emoji._get_registry()
        for kind, (lo, _) in KIND_SLUGS.items():
            assert lo in lowres, f"{kind}: lowres {lo!r} missing"
            assert lo in pixel_emoji.HIRES_REGISTRY, f"{kind}: {lo!r} no hires pair"

    def test_pack_hires_slugs_resolve(self):
        # overcast / rain_patchy upgrade to pack sprites in the hero.
        from led_ticker import emoji_pack, pixel_emoji

        for kind, (_, hi) in KIND_SLUGS.items():
            in_curated = hi in pixel_emoji.HIRES_REGISTRY
            assert in_curated or emoji_pack.has_slug(hi), (
                f"{kind}: hires {hi!r} in neither curated registry nor pack"
            )

    def test_pack_upgrades_are_where_the_spec_says(self):
        assert KIND_SLUGS["overcast"] == ("cloud", "sun_behind_large_cloud")
        assert KIND_SLUGS["rain_patchy"] == ("rain", "sun_behind_rain_cloud")
        assert KIND_SLUGS["partly_night"] == ("partly_cloudy", "moon")
