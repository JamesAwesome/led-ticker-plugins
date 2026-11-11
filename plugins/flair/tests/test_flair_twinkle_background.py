"""flair.twinkle BACKGROUND — twinkling starfield behind widget content."""

import statistics
import time
from unittest import mock

import pytest
from led_ticker.plugin import BackgroundEffectBase, HeadlessCanvas, ScaledCanvas

from led_ticker_flair.flair.twinkle_background import TwinkleBackground


def _paint(fx, frame, w=160, h=16) -> HeadlessCanvas:
    c = HeadlessCanvas(width=w, height=h)
    fx.paint(c, frame)
    return c


def test_is_background_effect() -> None:
    assert issubclass(TwinkleBackground, BackgroundEffectBase)
    assert TwinkleBackground.frame_invariant is False
    assert TwinkleBackground.restart_on_visit is False


def test_never_paints_black() -> None:
    fx = TwinkleBackground(density=0.1, seed=1)
    for f in range(0, 60, 3):
        c = HeadlessCanvas(width=64, height=32)
        calls = []
        orig = c.SetPixel

        def spy(x, y, r, g, b, _o=orig, _calls=calls):
            _calls.append((r, g, b))
            _o(x, y, r, g, b)

        c.SetPixel = spy
        fx.paint(c, f)
        assert all(rgb != (0, 0, 0) for rgb in calls)


def test_pure_function_of_frame() -> None:
    fx = TwinkleBackground(density=0.05, seed=9)
    a = _paint(fx, 17)._pixels
    _paint(fx, 40)
    assert _paint(fx, 17)._pixels == a
    assert a


def test_unseeded_instance_is_still_frame_pure() -> None:
    fx = TwinkleBackground(density=0.05)
    assert _paint(fx, 5)._pixels == _paint(fx, 5)._pixels
    other = TwinkleBackground(density=0.05)
    assert fx._seed != other._seed


def test_speed_changes_the_field() -> None:
    a = _paint(TwinkleBackground(density=0.05, seed=3), 7)._pixels
    b = _paint(TwinkleBackground(density=0.05, seed=3, speed=2.0), 7)._pixels
    assert a != b


def test_star_count_scales_with_area() -> None:
    fx = TwinkleBackground(density=0.03, seed=2)
    for w, h in ((160, 16), (256, 64)):
        n = len(fx._stars_for(w, h))
        assert 0.7 * 0.03 * w * h <= n <= 1.3 * 0.03 * w * h


def test_colors_scale_from_base() -> None:
    fx = TwinkleBackground(density=0.2, color=(255, 0, 0), seed=3)
    for rgb in _paint(fx, 4)._pixels.values():
        assert rgb[1] == 0 and rgb[2] == 0 and rgb[0] > 0


def test_brightness_dims_every_star() -> None:
    full = _paint(TwinkleBackground(density=0.2, seed=3), 4)._pixels
    dim = _paint(TwinkleBackground(density=0.2, seed=3, brightness=0.25), 4)._pixels
    assert dim and set(dim) <= set(full)
    for xy, rgb in dim.items():
        assert all(d <= f for d, f in zip(rgb, full[xy], strict=True))
        assert all(abs(d - f * 0.25) <= 1 for d, f in zip(rgb, full[xy], strict=True))
    assert max(map(max, dim.values())) < max(map(max, full.values()))


def test_brightness_default_is_unchanged() -> None:
    a = _paint(TwinkleBackground(density=0.1, seed=5), 9)._pixels
    b = _paint(TwinkleBackground(density=0.1, seed=5, brightness=1.0), 9)._pixels
    c = _paint(TwinkleBackground(density=0.1, seed=5, brightness=1), 9)._pixels
    assert a == b == c


class TestScaledCanvas:
    def test_paints_only_on_real(self) -> None:
        real = HeadlessCanvas(width=256, height=64)
        wrapped = ScaledCanvas(real, scale=4, content_height=16)
        fx = TwinkleBackground(seed=1)
        with mock.patch.object(
            ScaledCanvas, "SetPixel", side_effect=AssertionError("via wrapper")
        ):
            for f in range(0, 24, 5):
                fx.paint(wrapped, f)
        assert real._pixels


@pytest.mark.parametrize(
    "kwargs",
    [
        {"density": 0},
        {"density": 1.2},
        {"speed": 0},
        {"speed": 2.5},
        {"color": [1, 2]},
        {"color": [1, 2, 300]},
        {"color": [1, 2, True]},
        {"seed": "x"},
        {"brightness": 0},
        {"brightness": 1.5},
        {"brightness": True},
        {"brightness": float("nan")},
        {"brightness": "dim"},
    ],
)
def test_bad_args(kwargs) -> None:
    with pytest.raises(ValueError):
        TwinkleBackground(**kwargs)


def test_perf_bigsign() -> None:
    fx = TwinkleBackground(seed=1)
    c = HeadlessCanvas(width=256, height=64)
    fx.paint(c, 0)  # builds the star list
    samples = []
    for f in range(1, 12):
        c = HeadlessCanvas(width=256, height=64)
        t0 = time.perf_counter()
        fx.paint(c, f)
        samples.append(time.perf_counter() - t0)
    assert statistics.median(samples) <= 0.002
