from led_ticker_flight.data import SAMPLE_AIRCRAFT, VR_GLYPH, fmt_alt, vr_state


def test_vr_thresholds():
    assert vr_state(51) == "climb"
    assert vr_state(50) == "level"
    assert vr_state(-50) == "level"
    assert vr_state(-51) == "descend"
    assert vr_state(0) == "level"


def test_vr_glyph_names():
    assert VR_GLYPH == {"climb": "up", "descend": "down", "level": "level"}


def test_fmt_alt_thousands():
    assert fmt_alt(34000) == "34,000FT"
    assert fmt_alt(900) == "900FT"


def test_sample_feed_matches_handoff():
    assert [a.flt for a in SAMPLE_AIRCRAFT] == ["UA2341", "DL815", "WN88", "BA49H"]
    ua = SAMPLE_AIRCRAFT[0]
    assert (ua.actype, ua.alt, ua.vr, ua.gs, ua.trk, ua.dist, ua.reg) == (
        "B738",
        34000,
        1200,
        460,
        247,
        "12KM NE",
        "N12345",
    )
    assert SAMPLE_AIRCRAFT[3].reg == "G-STBA"
