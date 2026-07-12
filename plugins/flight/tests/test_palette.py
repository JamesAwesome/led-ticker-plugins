from led_ticker_flight.palette import (
    AIRLINES,
    ALT,
    DEFAULT_AIRLINE,
    IDENT,
    TRACK,
    airline_of,
)


def test_semantic_palette_values():
    assert IDENT == (255, 255, 255)
    assert ALT == (255, 180, 0)
    assert TRACK == (0, 220, 255)


def test_airline_of_known_prefixes():
    assert airline_of("UA2341").name == "UNITED"
    assert airline_of("DL815").c1 == (220, 40, 60)
    assert airline_of("WN88").name == "SOUTHWEST"
    assert airline_of("BA49H").name == "BRITISH"


def test_airline_of_unknown_and_edge():
    # single-letter prefix "N1..." -> "N" -> unknown
    assert airline_of("N12345") is DEFAULT_AIRLINE
    assert airline_of("XY123") is DEFAULT_AIRLINE
    assert airline_of("") is DEFAULT_AIRLINE
    assert DEFAULT_AIRLINE.name == ""


def test_airlines_table_complete():
    assert set(AIRLINES) == {"UA", "DL", "WN", "BA"}
