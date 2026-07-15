"""Shared layout helpers: `_common.flash_price_color` (Bloomberg price flash)."""

from led_ticker_stocks import _palette as pal
from led_ticker_stocks.layouts._common import flash_price_color


def _rgb(c):
    return (c.red, c.green, c.blue)


def test_no_flash_returns_amber():
    # flash_t None -> steady amber (dimmed)
    assert _rgb(flash_price_color(None, 1.0, now=100.0)) == _rgb(pal.PRICE)


def test_old_flash_decayed_to_amber():
    # now well past flash_t + 0.420 -> k=0 -> amber
    assert _rgb(flash_price_color(100.0, 1.0, now=101.0)) == _rgb(pal.PRICE)


def test_fresh_flash_is_near_white():
    # now == flash_t -> k=1 -> ~95% toward white; whiter than amber on every channel
    c = flash_price_color(100.0, 1.0, now=100.0)
    assert (
        c.green > pal.PRICE.green and c.blue > pal.PRICE.blue
    )  # amber has low G/B; white lifts them


def test_flash_decays_monotonically():
    # brightness (sum) at t=0 > t=0.2 > t=0.42
    def s(now):
        c = flash_price_color(100.0, 1.0, now=now)
        return c.red + c.green + c.blue

    assert (
        s(100.0)
        > s(100.2)
        > s(100.42)
        == (pal.PRICE.red + pal.PRICE.green + pal.PRICE.blue)
    )


def test_dim_applies():
    bright = flash_price_color(100.0, 1.0, now=100.0)
    dark = flash_price_color(100.0, 0.45, now=100.0)
    assert (dark.red + dark.green + dark.blue) < (
        bright.red + bright.green + bright.blue
    )
