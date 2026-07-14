from led_ticker_stocks.finnhub import parse_quote


def test_parse_quote_maps_fields():
    payload = {
        "c": 317.31,
        "d": 1.99,
        "dp": 0.6311,
        "h": 323.45,
        "l": 315.78,
        "o": 317.015,
        "pc": 315.32,
        "t": 1,
    }
    q = parse_quote("AAPL", payload)
    assert q.sym == "AAPL"
    assert q.price == 317.31 and q.prev == 315.32
    assert q.d == 1.99 and q.dp == 0.6311
    assert q.has_data


def test_parse_quote_zeroed_is_no_data():
    payload = {
        "c": 0,
        "d": None,
        "dp": None,
        "h": 0,
        "l": 0,
        "o": 0,
        "pc": 0,
        "t": 0,
    }
    q = parse_quote("ZZZZ", payload)
    assert not q.has_data
    assert q.change is None and q.pct is None
