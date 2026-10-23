from led_ticker_hockey.layouts import VALID_LAYOUTS, resolve_layout


def test_resolve_layout_auto_is_scoreboard_everywhere():
    for scale, w in ((1, 160), (4, 256), (4, 512)):
        assert resolve_layout("auto", scale, w) == "scoreboard"


def test_explicit_names_pass_through():
    for name in ("scoreboard", "ticker"):
        for scale, w in ((1, 160), (4, 256), (4, 512)):
            assert resolve_layout(name, scale, w) == name
    assert VALID_LAYOUTS == ("auto", "scoreboard", "ticker")
