import unittest.mock as mock

from led_ticker_weather.source import _DEFAULT_FORMAT, WeatherSource

_CURRENT = {
    "temp_f": 72.0,
    "temp_c": 22.0,
    "feelslike_f": 74.0,
    "feelslike_c": 23.0,
    "humidity": 50,
    "wind_mph": 5.0,
    "condition": {"text": "Clear"},
}


def _src(**kw):
    return WeatherSource(
        id="weather.nyc", session=mock.Mock(), interval=1800, location="NYC", **kw
    )


async def test_update_renders_default_format(monkeypatch):
    monkeypatch.setattr(
        "led_ticker_weather.source.fetch_current", mock.AsyncMock(return_value=_CURRENT)
    )
    s = _src()
    await s.update()
    assert s.current == "72°F Clear"  # default "{temp_f}°F {condition}"
    assert s.version == 1  # _set_value bumped


async def test_update_custom_format_with_emoji(monkeypatch):
    monkeypatch.setattr(
        "led_ticker_weather.source.fetch_current", mock.AsyncMock(return_value=_CURRENT)
    )
    s = _src(format="{temp_f}° {emoji}")
    await s.update()
    # Clear -> sun -> :sun: (renders as sprite downstream)
    assert s.current == "72° :sun:"


async def test_update_exposes_all_current_fields(monkeypatch):
    monkeypatch.setattr(
        "led_ticker_weather.source.fetch_current", mock.AsyncMock(return_value=_CURRENT)
    )
    s = _src(format="{feelslike_f}|{humidity}|{wind_mph}|{temp_c}|{feelslike_c}")
    await s.update()
    assert s.current == "74|50|5|22|23"


def test_placeholder_until_first_fetch():
    s = _src(placeholder="—")
    assert s.current == "—" and s.version == 0  # nothing fetched yet


def test_location_dict_normalized():
    s = WeatherSource(
        id="w", session=mock.Mock(), interval=1800, location={"lat": 40.7, "lon": -74.0}
    )
    assert s.location == "40.7,-74.0"


def test_default_format_constant():
    assert _DEFAULT_FORMAT == "{temp_f}°F {condition}"


def test_validate_config_missing_location():
    errs = WeatherSource.validate_config({"type": "weather.current"})
    assert any("location" in e for e in errs)


def test_validate_config_unknown_format_field():
    errs = WeatherSource.validate_config(
        {"location": "NYC", "format": "{temp_f} {bogus}"}
    )
    assert any("bogus" in e for e in errs)


def test_validate_config_valid_block():
    errs = WeatherSource.validate_config(
        {"location": "NYC", "format": "{temp_f}°F {emoji}"}
    )
    assert errs == []


def test_validate_config_default_format_ok():
    # format omitted -> the default is used -> no unknown-field error
    assert WeatherSource.validate_config({"location": "NYC"}) == []
