from led_ticker_football.layouts import VALID_LAYOUTS, resolve_layout


def test_auto_is_scoreboard_everywhere():
    assert resolve_layout("auto", 1, 160) == "scoreboard"
    assert resolve_layout("auto", 4, 256) == "scoreboard"
    assert resolve_layout("auto", 4, 512) == "scoreboard"


def test_explicit_names_pass_through():
    assert resolve_layout("ticker", 4, 256) == "ticker"
    assert resolve_layout("scoreboard", 1, 160) == "scoreboard"
    assert VALID_LAYOUTS == ("auto", "scoreboard", "ticker")
