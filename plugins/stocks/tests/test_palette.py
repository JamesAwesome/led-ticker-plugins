from led_ticker_stocks import _palette as p


def test_tokens_are_expected_rgb():
    assert (p.SYM.red, p.SYM.green, p.SYM.blue) == (255, 255, 255)
    assert (p.PRICE.red, p.PRICE.green, p.PRICE.blue) == (255, 180, 0)
    assert (p.UP.red, p.UP.green, p.UP.blue) == (60, 220, 60)
    assert (p.DOWN.red, p.DOWN.green, p.DOWN.blue) == (255, 60, 60)
    assert (p.IDX.red, p.IDX.green, p.IDX.blue) == (0, 220, 255)
    assert (p.FX.red, p.FX.green, p.FX.blue) == (170, 90, 255)
    assert (p.LABEL.red, p.LABEL.green, p.LABEL.blue) == (70, 90, 130)


def test_dim_scales_channels():
    d = p.dim(p.PRICE, 0.45)
    assert (d.red, d.green, d.blue) == (115, 81, 0)  # round(255*.45), round(180*.45), 0


def test_dim_full_is_identity():
    d = p.dim(p.UP, 1.0)
    assert (d.red, d.green, d.blue) == (60, 220, 60)
