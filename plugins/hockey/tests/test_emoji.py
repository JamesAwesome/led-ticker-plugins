from led_ticker_hockey.emoji import PUCK


def test_puck_lowres_fits_8x8_without_black():
    assert PUCK
    assert all(0 <= x < 8 and 0 <= y < 8 for x, y, *_ in PUCK)
    assert all((r, g, b) != (0, 0, 0) for *_, r, g, b in PUCK)


def test_puck_is_never_near_black():
    # Dark pixels vanish on the panel: every pixel must read.
    assert all(max(r, g, b) >= 100 for *_, r, g, b in PUCK)
