from led_ticker_flight.adsb import (
    bearing_deg,
    compass8,
    haversine_km,
    parse_point_response,
    radius_nm,
)

NYC = (40.7128, -74.0060)


def test_radius_nm_conversion_and_clamp():
    assert radius_nm(30) == 16  # 30 / 1.852 = 16.198 -> 16
    assert radius_nm(2) == 1
    assert radius_nm(460) == 248
    assert radius_nm(10000) == 250  # API hard cap


def test_haversine_known_distance():
    # NYC -> Newark airport ~ 14.2 km
    d = haversine_km(*NYC, 40.6895, -74.1745)
    assert 13.5 < d < 15.0


def test_bearing_and_compass8():
    assert compass8(0) == "N"
    assert compass8(44) == "NE"
    assert compass8(23) == "NE"
    assert compass8(22) == "N"
    assert compass8(359) == "N"
    assert compass8(226) == "SW"
    # due east: same lat, greater lon
    b = bearing_deg(40.0, -74.0, 40.0, -73.5)
    assert 85 < b < 95


def _ac(**kw):
    base = {
        "flight": "UA2341 ",
        "t": "B738",
        "alt_baro": 34000,
        "baro_rate": 1200,
        "gs": 460.3,
        "track": 247.2,
        "lat": 40.80,
        "lon": -73.90,
        "r": "N12345",
    }
    base.update(kw)
    return base


def test_parse_maps_fields_and_strips():
    out = parse_point_response({"ac": [_ac()]}, *NYC, max_aircraft=4)
    assert len(out) == 1
    a = out[0]
    assert a.flt == "UA2341" and a.actype == "B738"
    assert a.alt == 34000 and a.vr == 1200 and a.gs == 460 and a.trk == 247
    assert a.dist.endswith(("NE", "N"))  # bearing from NYC to (40.80,-73.90) is NE-ish
    assert "KM " in a.dist
    assert a.reg == "N12345"


def test_parse_drops_bad_entries():
    payload = {
        "ac": [
            _ac(flight=None),  # no callsign
            _ac(flight="   "),  # blank callsign
            _ac(lat=None),  # no position
            _ac(alt_baro="ground"),  # on the ground
            _ac(flight="DL815"),  # good
        ]
    }
    out = parse_point_response(payload, *NYC, max_aircraft=8)
    assert [a.flt for a in out] == ["DL815"]


def test_parse_sorts_by_distance_and_caps():
    far = _ac(flight="FAR1", lat=41.5, lon=-72.0)
    near = _ac(flight="NEAR1", lat=40.72, lon=-74.0)
    mid = _ac(flight="MID1", lat=40.9, lon=-73.8)
    out = parse_point_response({"ac": [far, mid, near]}, *NYC, max_aircraft=2)
    assert [a.flt for a in out] == ["NEAR1", "MID1"]


def test_parse_defaults_missing_optionals():
    payload = {"ac": [_ac(baro_rate=None, gs=None, track=None, t=None, r=None)]}
    a = parse_point_response(payload, *NYC, max_aircraft=4)[0]
    assert (a.vr, a.gs, a.trk, a.actype, a.reg) == (0, 0, 0, "", "")


def test_parse_geom_rate_fallback():
    a = parse_point_response({"ac": [_ac(baro_rate=None, geom_rate=-800)]}, *NYC, 4)[0]
    assert a.vr == -800


def test_parse_empty_payload():
    assert parse_point_response({}, *NYC, 4) == []


def test_parse_ac_list_none():
    """{"ac": None} → [] instead of TypeError."""
    out = parse_point_response({"ac": None}, *NYC, 4)
    assert out == []


def test_parse_ac_list_non_list():
    """{"ac": "bogus"} → [] instead of AttributeError."""
    out = parse_point_response({"ac": "bogus"}, *NYC, 4)
    assert out == []


def test_parse_ac_list_int():
    """{"ac": 12345} → [] instead of error."""
    out = parse_point_response({"ac": 12345}, *NYC, 4)
    assert out == []


def test_parse_entry_not_dict():
    """Entry that is a string (not dict) → dropped."""
    payload = {
        "ac": [
            "not_a_dict_string",
            _ac(flight="VALID1"),
        ]
    }
    out = parse_point_response(payload, *NYC, 4)
    assert [a.flt for a in out] == ["VALID1"]


def test_parse_flight_as_int():
    """flight as int (not string) → entry dropped."""
    payload = {"ac": [_ac(flight=12345)]}
    out = parse_point_response(payload, *NYC, 4)
    assert out == []


def test_parse_gs_as_string():
    """gs as string "fast" (not numeric) → parses with gs == 0."""
    a = parse_point_response({"ac": [_ac(gs="fast")]}, *NYC, 4)[0]
    assert a.gs == 0


def test_parse_track_as_string():
    """track as string (not numeric) → parses with trk == 0."""
    a = parse_point_response({"ac": [_ac(track="north")]}, *NYC, 4)[0]
    assert a.trk == 0


def test_parse_lat_as_string():
    """lat as string (not numeric) → entry dropped."""
    payload = {"ac": [_ac(lat="north")]}
    out = parse_point_response(payload, *NYC, 4)
    assert out == []


def test_parse_lon_as_bool():
    """lon as bool (type-check rejects bool explicitly) → entry dropped."""
    payload = {"ac": [_ac(lon=True)]}
    out = parse_point_response(payload, *NYC, 4)
    assert out == []


def test_parse_alt_as_bool():
    """alt_baro as bool (type-check rejects bool explicitly) → entry dropped."""
    payload = {"ac": [_ac(alt_baro=True)]}
    out = parse_point_response(payload, *NYC, 4)
    assert out == []


def test_parse_type_as_int():
    """t (type) as int (not string) → parses with actype == ""."""
    a = parse_point_response({"ac": [_ac(t=738)]}, *NYC, 4)[0]
    assert a.actype == ""


def test_parse_reg_as_int():
    """r (reg) as int (not string) → parses with reg == ""."""
    a = parse_point_response({"ac": [_ac(r=12345)]}, *NYC, 4)[0]
    assert a.reg == ""
