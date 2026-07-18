"""tests/test_palette.py"""

from led_ticker_baseball import _palette as pal


def test_tokens_exist_with_handoff_values():
    assert (pal.IDENT.red, pal.IDENT.green, pal.IDENT.blue) == (255, 255, 255)
    assert (pal.WIN.red, pal.WIN.green, pal.WIN.blue) == (60, 220, 60)
    assert (pal.LOSS.red, pal.LOSS.green, pal.LOSS.blue) == (255, 60, 60)
    assert (pal.AMBER.red, pal.AMBER.green, pal.AMBER.blue) == (255, 180, 0)
    assert (pal.CYAN.red, pal.CYAN.green, pal.CYAN.blue) == (0, 220, 255)
    assert (pal.MAGENTA.red, pal.MAGENTA.green, pal.MAGENTA.blue) == (255, 80, 255)
    assert (pal.VIOLET.red, pal.VIOLET.green, pal.VIOLET.blue) == (170, 90, 255)
    assert (pal.LABEL.red, pal.LABEL.green, pal.LABEL.blue) == (70, 90, 130)
    assert (pal.YEL.red, pal.YEL.green, pal.YEL.blue) == (255, 217, 0)
    assert (pal.ORANGE.red, pal.ORANGE.green, pal.ORANGE.blue) == (255, 128, 0)


def test_dim_scales_channels_and_clamps():
    d = pal.dim(pal.WIN, 0.5)
    assert (d.red, d.green, d.blue) == (30, 110, 30)
    full = pal.dim(pal.IDENT, 1.0)
    assert (full.red, full.green, full.blue) == (255, 255, 255)
