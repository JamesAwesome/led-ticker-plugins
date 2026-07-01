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


# ── Finding 1: lazy field build ───────────────────────────────────────────────


async def test_update_skips_unused_missing_fields(monkeypatch):
    """update() must succeed when the API omits fields not used in the format.

    Before the fix: an eager build of all 8 fields raised KeyError on feelslike_f
    even though the format never referenced it, stalling the panel forever.
    """
    sparse_current = {
        "temp_f": 0.0,
        "condition": {"text": "x"},
        # feelslike_f / feelslike_c / humidity / wind_mph / temp_c deliberately absent
    }
    monkeypatch.setattr(
        "led_ticker_weather.source.fetch_current",
        mock.AsyncMock(return_value=sparse_current),
    )
    s = _src(format="{temp_f}°F {condition}")
    await s.update()  # must not raise
    assert s.current == "0°F x"
    assert s.version == 1


# ── Finding 2: validate dry-run ───────────────────────────────────────────────


def test_validate_config_bad_conversion_spec():
    """{temp_f:zzz} is a valid field name but an invalid conversion spec."""
    errs = WeatherSource.validate_config({"location": "NYC", "format": "{temp_f:zzz}"})
    assert errs, "expected an error for bad conversion spec, got none"


def test_validate_config_wrong_spec_for_type():
    """{condition:d} asks for an integer conversion on a str value."""
    errs = WeatherSource.validate_config({"location": "NYC", "format": "{condition:d}"})
    assert errs, "expected an error for %d on a str field, got none"


def test_validate_config_valid_float_spec():
    """A well-formed float spec {temp_f:.0f} should pass validation."""
    errs = WeatherSource.validate_config(
        {"location": "NYC", "format": "{temp_f:.0f}°F"}
    )
    assert errs == []


def test_validate_config_malformed_format_returns_error():
    # an unclosed brace must be a clean error, not a raised ValueError
    errs = WeatherSource.validate_config({"location": "NYC", "format": "{temp_f"})
    assert any("malformed" in e for e in errs)


def test_validate_config_non_str_format():
    """A non-string format value must produce a clear error, not a TypeError."""
    errs = WeatherSource.validate_config({"location": "NYC", "format": 123})
    assert errs, "expected an error for non-str format, got none"
    assert any("string" in e for e in errs)
