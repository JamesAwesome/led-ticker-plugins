"""Focused unit tests for the ported baseball emoji objects."""

import pytest

from led_ticker_baseball.emoji import BALL, BALL_HIRES, _generate_baseball_hires


def test_ball_is_nonempty_list_of_pixel_tuples():
    assert isinstance(BALL, list)
    assert len(BALL) > 0
    for px in BALL:
        assert isinstance(px, tuple)
        assert len(px) == 5
        x, y, r, g, b = px
        assert 0 <= x <= 7
        assert 0 <= y <= 7
        assert 0 <= r <= 255
        assert 0 <= g <= 255
        assert 0 <= b <= 255


def test_generate_baseball_hires_size_32_in_bounds_and_filled():
    pixels = _generate_baseball_hires(size=32)
    assert isinstance(pixels, tuple)
    assert len(pixels) >= 100  # it's a filled ball
    for px in pixels:
        assert isinstance(px, tuple)
        assert len(px) == 5
        x, y, r, g, b = px
        assert 0 <= x <= 31
        assert 0 <= y <= 31
        assert 0 <= r <= 255
        assert 0 <= g <= 255
        assert 0 <= b <= 255


def test_ball_hires_physical_size_and_pixels():
    assert BALL_HIRES.physical_size == 32
    assert len(BALL_HIRES.pixels) > 0
    assert BALL_HIRES.pixels == _generate_baseball_hires(size=32)


@pytest.mark.parametrize("size", [16, 24, 32])
def test_generate_baseball_hires_is_size_parametric(size):
    pixels = _generate_baseball_hires(size=size)
    assert len(pixels) > 0
    for x, y, *_rgb in pixels:
        assert 0 <= x <= size - 1
        assert 0 <= y <= size - 1
