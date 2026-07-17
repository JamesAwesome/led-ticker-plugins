"""tests/test_resolve_layout.py — spec table: auto @ scale1 -> ticker;
auto @ scale>1 -> two_row (<400 phys) / scoreboard (>=400); explicit names
pass through (scale dispatch happens in the story's draw, not here)."""
from led_ticker_baseball.layouts import VALID_LAYOUTS, resolve_layout


def test_auto_scale1_is_ticker():
    assert resolve_layout("auto", 1, 160) == "ticker"


def test_auto_bigsign_is_two_row():
    assert resolve_layout("auto", 4, 256) == "two_row"


def test_auto_longboi_is_scoreboard():
    assert resolve_layout("auto", 4, 512) == "scoreboard"


def test_explicit_names_pass_through():
    for name in ("ticker", "scoreboard", "two_row"):
        assert resolve_layout(name, 1, 160) == name
        assert resolve_layout(name, 4, 256) == name


def test_valid_layouts_tuple():
    assert VALID_LAYOUTS == ("auto", "ticker", "scoreboard", "two_row")
