from led_ticker_basketball.emoji import BALL, BALL_HIRES

FILL = (255, 120, 30)
SEAM = (110, 50, 20)


def test_ball_lowres_has_no_black_and_fits_8x8():
    assert all(0 <= x < 8 and 0 <= y < 8 for x, y, *_ in BALL)
    assert all((r, g, b) != (0, 0, 0) for *_, r, g, b in BALL)
    assert (0, 0) not in {(x, y) for x, y, *_ in BALL}
    colors = {(r, g, b) for *_, r, g, b in BALL}
    assert colors == {FILL, SEAM}


def test_ball_hires_is_32_square_disc():
    assert BALL_HIRES.physical_size == 32
    px = {(x, y): (r, g, b) for x, y, r, g, b in BALL_HIRES.pixels}
    assert all(0 <= x < 32 and 0 <= y < 32 for x, y in px)
    assert len(px) >= 600
    assert (0, 0) not in px
    assert (15, 15) in px
    assert {FILL, SEAM} <= set(px.values())
