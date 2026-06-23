from led_ticker.plugin import HiResEmoji

from led_ticker_flair.pokeball.emoji import POKEBALL, POKEBALL_HIRES


def test_pokeball_lowres_is_pixeldata():
    assert isinstance(POKEBALL, list) and POKEBALL, (
        "POKEBALL must be a non-empty pixel list"
    )
    for px in POKEBALL:
        assert len(px) == 5, "each pixel is (x, y, r, g, b)"


def test_pokeball_hires_is_hires_emoji():
    assert isinstance(POKEBALL_HIRES, HiResEmoji)
    assert POKEBALL_HIRES.physical_size == 32
    assert POKEBALL_HIRES.pixels, "hires sprite must have pixels"
