from led_ticker.plugin import HeadlessBackend

from led_ticker_stocks._chip import chip_colors_for, draw_chip
from led_ticker_stocks.model import SymbolQuote


def test_chip_colors_deterministic_and_two_tone():
    a = chip_colors_for("AAPL", None)
    b = chip_colors_for("AAPL", None)
    assert (a[0].red, a[0].green, a[0].blue) == (b[0].red, b[0].green, b[0].blue)
    assert (a[1].red, a[1].green, a[1].blue) == (b[1].red, b[1].green, b[1].blue)
    assert a[0] != a[1] or (a[0].red, a[0].green, a[0].blue) != (
        a[1].red,
        a[1].green,
        a[1].blue,
    )


def test_distinct_symbols_differ():
    a = chip_colors_for("AAPL", None)
    z = chip_colors_for("ZM", None)
    assert (a[0].red, a[0].green, a[0].blue) != (z[0].red, z[0].green, z[0].blue)


def test_override_wins():
    from led_ticker.plugin import make_color

    ov = (make_color(1, 2, 3), make_color(4, 5, 6))
    c = chip_colors_for("AAPL", ov)
    assert (c[0].red, c[0].green, c[0].blue) == (1, 2, 3)


def test_draw_chip_fills_two_tone_block():
    real = HeadlessBackend(32, 32).create_canvas()
    q = SymbolQuote(sym="AAPL", price=1.0, prev=1.0)
    draw_chip(real, 0, 0, 16, q, dim=1.0)
    colors = {v for v in real._pixels.values() if v != (0, 0, 0)}
    assert len(colors) >= 2  # two tones present
    # corners knocked: (0,0) should be unlit at radius >= 1
    assert (0, 0) not in real._pixels
