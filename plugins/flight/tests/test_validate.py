from led_ticker_flight.widget import OverheadWidget


def _errs(cfg):
    return OverheadWidget.validate_config(dict(cfg))


def test_valid_config_passes():
    assert _errs({"latitude": 40.7, "longitude": -74.0}) == []
    assert _errs({"demo": True}) == []


def test_missing_coords_flagged():
    errs = _errs({})
    assert any("latitude" in e for e in errs)


def test_ranges():
    assert any("latitude" in e for e in _errs({"latitude": 91, "longitude": 0}))
    assert any("longitude" in e for e in _errs({"latitude": 0, "longitude": -181}))
    assert any(
        "radius_km" in e for e in _errs({"latitude": 0, "longitude": 0, "radius_km": 1})
    )
    assert any(
        "max_aircraft" in e
        for e in _errs({"latitude": 0, "longitude": 0, "max_aircraft": 9})
    )
    assert any(
        "interval" in e for e in _errs({"latitude": 0, "longitude": 0, "interval": 2})
    )
    assert any(
        "layout" in e for e in _errs({"latitude": 0, "longitude": 0, "layout": "big"})
    )


def test_bool_rejected_for_numerics():
    assert any("latitude" in e for e in _errs({"latitude": True, "longitude": 0}))


def test_max_aircraft_rejects_non_integral_float():
    errs = _errs({"latitude": 0, "longitude": 0, "max_aircraft": 2.5})
    assert any("max_aircraft" in e for e in errs)


def test_radius_km_rejects_non_integral_float():
    errs = _errs({"latitude": 0, "longitude": 0, "radius_km": 30.5})
    assert any("radius_km" in e for e in errs)


def test_max_aircraft_accepts_integral_float():
    # 4.0 is a plausible TOML spelling of an int; only reject non-integral.
    assert _errs({"latitude": 0, "longitude": 0, "max_aircraft": 4.0}) == []


def test_demo_rejects_non_bool():
    errs = _errs({"demo": "yes"})
    assert any("demo" in e for e in errs)


def test_demo_true_still_fine():
    assert _errs({"demo": True}) == []


def test_warnings_hero_at_scale_1():
    from led_ticker.plugin import ValidationContext

    ctx = ValidationContext(
        scale=1, content_height=16, panel_width=160, panel_height=16, config_dir="."
    )
    warns = OverheadWidget.validate_config_warnings(
        {"latitude": 0, "longitude": 0, "layout": "hero"}, ctx
    )
    assert any("ticker" in w for w in warns)
