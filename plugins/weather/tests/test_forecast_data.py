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
            "sunny",
            "clear",
            "partly",
            "partly_night",
            "cloudy",
            "overcast",
            "rain",
            "rain_patchy",
            "thunder",
            "snow",
            "fog",
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


def _payload(n_days=7):
    """Minimal /v1/forecast.json shape (fields per design/README.md)."""
    fd = [
        {
            "date": "2026-07-21",  # a Tuesday
            "day": {
                "maxtemp_f": 86.0,
                "mintemp_f": 66.0,
                "daily_chance_of_rain": 0,
                "condition": {"code": 1000},
            },
        }
    ]
    for i in range(1, n_days):
        fd.append(
            {
                "date": f"2026-07-{21 + i}",
                "day": {
                    "maxtemp_f": 80.0 + i,
                    "mintemp_f": 60.0 + i,
                    "daily_chance_of_rain": 10 * i,
                    "condition": {"code": 1063},
                },
            }
        )
    return {
        "location": {"name": "Boston"},
        "current": {
            "temp_f": 78.0,
            "feelslike_f": 80.0,
            "is_day": 1,
            "condition": {"code": 1003},
        },
        "forecast": {"forecastday": fd},
    }


class TestParseForecastPayload:
    def test_current_merges_today_hi_lo(self):
        from led_ticker_weather.forecast_data import parse_forecast_payload

        data = parse_forecast_payload(_payload())
        assert data.location == "Boston"
        assert data.current.temp_f == 78.0
        assert data.current.feels_f == 80.0
        assert data.current.kind == "partly"
        assert data.current.hi_f == 86.0  # forecastday[0]
        assert data.current.lo_f == 66.0

    def test_days_are_tomorrow_onward(self):
        from led_ticker_weather.forecast_data import parse_forecast_payload

        data = parse_forecast_payload(_payload())
        assert len(data.days) == 6  # forecastday[1:]
        assert data.days[0].label == "WED"  # 2026-07-22
        assert data.days[0].kind == "rain_patchy"
        assert data.days[0].pop == 10

    def test_day_kind_always_resolves_as_day(self):
        from led_ticker_weather.forecast_data import parse_forecast_payload

        p = _payload()
        p["forecast"]["forecastday"][1]["day"]["condition"]["code"] = 1000
        data = parse_forecast_payload(p)
        assert data.days[0].kind == "sunny"  # never "clear"

    def test_short_feed_parses_short(self):
        from led_ticker_weather.forecast_data import parse_forecast_payload

        data = parse_forecast_payload(_payload(n_days=3))
        assert len(data.days) == 2

    def test_night_current_swaps_kind(self):
        from led_ticker_weather.forecast_data import parse_forecast_payload

        p = _payload()
        p["current"]["is_day"] = 0
        assert parse_forecast_payload(p).current.kind == "partly_night"

    def test_string_typed_numerics_coerce_to_float(self):
        """F4: a string-typed numeric from the API ('86.0') must parse to
        a float, not survive as a str and blow up later at draw time."""
        from led_ticker_weather.forecast_data import parse_forecast_payload

        p = _payload()
        p["current"]["temp_f"] = "78.0"
        p["current"]["feelslike_f"] = "80.0"
        p["forecast"]["forecastday"][0]["day"]["maxtemp_f"] = "86.0"
        p["forecast"]["forecastday"][0]["day"]["mintemp_f"] = "66.0"
        p["forecast"]["forecastday"][1]["day"]["maxtemp_f"] = "81.0"
        p["forecast"]["forecastday"][1]["day"]["mintemp_f"] = "61.0"

        data = parse_forecast_payload(p)
        assert data.current.temp_f == 78.0
        assert isinstance(data.current.temp_f, float)
        assert data.current.feels_f == 80.0
        assert isinstance(data.current.feels_f, float)
        assert data.current.hi_f == 86.0
        assert isinstance(data.current.hi_f, float)
        assert data.current.lo_f == 66.0
        assert isinstance(data.current.lo_f, float)
        assert data.days[0].hi_f == 81.0
        assert isinstance(data.days[0].hi_f, float)
        assert data.days[0].lo_f == 61.0
        assert isinstance(data.days[0].lo_f, float)

    def test_non_numeric_string_raises_inside_parse(self):
        """F4: a non-numeric payload value must fail HERE (inside
        parse_forecast_payload, called from update()) as a ValueError —
        never survive parsing to raise TypeError later at draw time,
        which would trip core's render breaker instead of a benign
        monitor-loop retry."""
        from led_ticker_weather.forecast_data import parse_forecast_payload

        p = _payload()
        p["current"]["temp_f"] = "N/A"
        with pytest.raises(ValueError):
            parse_forecast_payload(p)


class TestDisplayTemp:
    def test_imperial_rounds(self):
        from led_ticker_weather.forecast_data import display_temp

        assert display_temp(78.4, "imperial") == 78
        assert display_temp(78.5, "imperial") == 79  # js_round half-up

    def test_metric_converts(self):
        from led_ticker_weather.forecast_data import display_temp

        assert display_temp(78.0, "metric") == 26  # (78-32)*5/9 = 25.6


class TestDemoData:
    def test_demo_is_the_handoff_boston_week(self):
        from led_ticker_weather.forecast_data import DEMO_DATA

        assert DEMO_DATA.location == "BOSTON"
        assert DEMO_DATA.current.temp_f == 78
        assert DEMO_DATA.current.kind == "partly"
        assert [d.label for d in DEMO_DATA.days] == [
            "TUE",
            "WED",
            "THU",
            "FRI",
            "SAT",
            "SUN",
        ]
        assert DEMO_DATA.days[1].kind == "thunder"
        assert DEMO_DATA.days[2].pop == 80


class TestFetchForecast:
    async def test_missing_key_raises(self, monkeypatch):
        from led_ticker_weather.forecast_data import fetch_forecast

        monkeypatch.delenv("WEATHERAPI_KEY", raising=False)
        with pytest.raises(ValueError, match="WEATHERAPI_KEY"):
            await fetch_forecast(None, "Boston")

    async def test_api_error_payload_raises(self, monkeypatch):
        import unittest.mock as mock

        from led_ticker_weather.forecast_data import fetch_forecast

        monkeypatch.setenv("WEATHERAPI_KEY", "test-key")
        resp = mock.MagicMock()
        resp.json = mock.AsyncMock(
            return_value={"error": {"code": 2008, "message": "disabled"}}
        )
        session = mock.MagicMock()
        session.get.return_value.__aenter__ = mock.AsyncMock(return_value=resp)
        session.get.return_value.__aexit__ = mock.AsyncMock(return_value=False)
        with pytest.raises(ValueError, match="2008"):
            await fetch_forecast(session, "Boston")

    async def test_requests_seven_days(self, monkeypatch):
        import unittest.mock as mock

        from led_ticker_weather.forecast_data import fetch_forecast

        monkeypatch.setenv("WEATHERAPI_KEY", "test-key")
        resp = mock.MagicMock()
        resp.json = mock.AsyncMock(return_value=_payload())
        session = mock.MagicMock()
        session.get.return_value.__aenter__ = mock.AsyncMock(return_value=resp)
        session.get.return_value.__aexit__ = mock.AsyncMock(return_value=False)
        await fetch_forecast(session, "Boston")
        params = session.get.call_args.kwargs["params"]
        assert params["days"] == 7
        assert params["q"] == "Boston"
