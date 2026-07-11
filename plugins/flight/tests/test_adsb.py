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
