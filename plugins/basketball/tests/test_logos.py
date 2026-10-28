import pytest

from led_ticker_basketball import _logos
from led_ticker_basketball.teams import NBA_TEAMS


@pytest.mark.parametrize("size", [36, 48])
def test_all_team_logos_decode(size):
    for abbrev in NBA_TEAMS:
        sp = _logos.sprite(abbrev, size)
        assert sp is not None, abbrev
        assert sp.size == size
        assert len(sp.pixels) > 0, abbrev
        assert all(0 <= x < size and 0 <= y < size for x, y, *_ in sp.pixels)


def test_logo_pixels_respect_floor_and_alpha(synthetic_logo_png):
    sp = _logos._decode(synthetic_logo_png, 64)
    coords = {(x, y): (r, g, b) for x, y, r, g, b in sp.pixels}
    assert coords.get((32, 32)) == (0, 107, 182)
    for x in range(2, 6):
        for y in range(2, 6):
            if (x, y) in coords:
                assert max(coords[(x, y)]) >= _logos.DARK_FLOOR
    assert not any(
        x <= 5 and y <= 5 and (x, y) in coords for x in range(2, 6) for y in range(2, 6)
    )
    assert not any((x, y) in coords for x in range(58, 62) for y in range(2, 6))


def test_missing_logo_falls_back_to_chip():
    assert _logos.sprite("ZZZ", 36) is None


def test_corrupt_logo_falls_back_to_chip(monkeypatch):
    monkeypatch.setattr(_logos, "_read_asset", lambda abbrev: b"not a png")
    assert _logos.sprite("BOS", 36) is None


def test_sprite_is_cached():
    assert _logos.sprite("BOS", 36) is _logos.sprite("BOS", 36)


def test_paint_logo_clips_on_shifted_real():
    class Real:
        width = 256
        height = 64

        def __init__(self):
            self.lit = []

        def SetPixel(self, x, y, r, g, b):
            self.lit.append((x, y))

    real = Real()
    sp = _logos.sprite("BOS", 36)
    _logos.paint_logo(real, sp, -20, 10)
    assert real.lit
    assert all(0 <= x < 256 and 0 <= y < 64 for x, y in real.lit)
