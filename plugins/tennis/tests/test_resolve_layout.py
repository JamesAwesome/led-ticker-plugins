from led_ticker_tennis.layouts import VALID_LAYOUTS, resolve_layout


def test_auto_scale1_is_ticker():
    assert resolve_layout("auto", 1, 160) == "ticker"


def test_auto_scaled_is_scoreboard_on_both_widths():
    assert resolve_layout("auto", 4, 256) == "scoreboard"
    assert resolve_layout("auto", 4, 512) == "scoreboard"


def test_explicit_names_pass_through():
    for name in ("ticker", "scoreboard"):
        for scale, w in ((1, 160), (4, 256), (4, 512)):
            assert resolve_layout(name, scale, w) == name


def test_valid_layouts_tuple():
    assert VALID_LAYOUTS == ("auto", "ticker", "scoreboard")
