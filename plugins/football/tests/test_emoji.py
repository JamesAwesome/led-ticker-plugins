from led_ticker_football.emoji import BALL


def test_ball_lowres_fits_8x8_without_black():
    assert BALL
    assert all(0 <= x < 8 and 0 <= y < 8 for x, y, *_ in BALL)
    assert all((r, g, b) != (0, 0, 0) for *_, r, g, b in BALL)
