import pytest

from led_ticker_football import _logos
from led_ticker_football.teams import NFL_TEAMS


@pytest.mark.parametrize("size", [_logos.LOGO_ROW, _logos.LOGO_LONG])
def test_all_team_logos_decode(size):
    for abbrev in NFL_TEAMS:
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


def test_corrupt_logo_falls_back_to_chip(monkeypatch, request):
    # Bypass (and afterwards drop) whatever earlier tests cached.
    _logos.sprite.cache_clear()
    request.addfinalizer(_logos.sprite.cache_clear)
    monkeypatch.setattr(_logos, "_read_asset", lambda abbrev: b"not a png")
    assert _logos.sprite("PHI", 36) is None


def test_sprite_is_cached():
    assert _logos.sprite("PHI", 36) is _logos.sprite("PHI", 36)


def test_paint_logo_clips_on_shifted_real():
    class Real:
        width = 256
        height = 64

        def __init__(self):
            self.lit = []

        def SetPixel(self, x, y, r, g, b):
            self.lit.append((x, y))

    real = Real()
    sp = _logos.sprite("PHI", 36)
    _logos.paint_logo(real, sp, -20, 10)
    assert real.lit
    assert all(0 <= x < 256 and 0 <= y < 64 for x, y in real.lit)


def test_every_team_has_a_trimmed_emoji_pair():
    for abbrev in NFL_TEAMS:
        pair = _logos.emoji(abbrev)
        assert pair is not None, abbrev
        lo, hi = pair
        assert len(lo) >= 12, abbrev  # a visible mark, not a blank sprite
        assert all(0 <= x < 8 and 0 <= y < 8 for x, y, *_ in lo), abbrev
        assert min(x for x, *_ in lo) == 0, abbrev
        assert hi.physical_size == _logos.EMOJI_HIRES
        xs = [x for x, *_ in hi.pixels]
        assert min(xs) == 0 and max(xs) + 1 == hi.physical_width, abbrev
        assert all(0 <= y < hi.physical_size for _, y, *_ in hi.pixels), abbrev


def test_emoji_is_none_when_logo_unavailable(monkeypatch, request):
    _logos.emoji.cache_clear()
    request.addfinalizer(_logos.emoji.cache_clear)
    monkeypatch.setattr(_logos, "_read_asset", lambda abbrev: b"not a png")
    assert _logos.emoji("PHI") is None
    assert _logos.emoji("ZZZ") is None


def test_wide_logo_emoji_keeps_its_aspect():
    lo, hi = _logos.emoji("NYJ")
    assert hi.physical_width > _logos.EMOJI_HIRES  # wider than tall, not squashed
    assert hi.physical_width <= _logos.EMOJI_HIRES_MAX_W
    assert len(lo) >= 12  # still a visible mark at 8x8
