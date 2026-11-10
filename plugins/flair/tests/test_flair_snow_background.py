"""flair.snow BACKGROUND — falling snow behind widget content."""

import statistics
import time
from unittest import mock

import pytest
from led_ticker.plugin import (
    BackgroundEffectBase,
    HeadlessCanvas,
    ScaledCanvas,
    emoji_slugs,
)

from led_ticker_flair.flair._snow import (
    flake_count,
    flake_height,
    flake_pixels,
    flake_position,
)
from led_ticker_flair.flair.snow_background import SnowBackground
from led_ticker_flair.flair.stickers import capture_sprite


def _paint(fx, frame, w=160, h=16) -> HeadlessCanvas:
    c = HeadlessCanvas(width=w, height=h)
    fx.paint(c, frame)
    return c


def test_is_background_effect() -> None:
    assert issubclass(SnowBackground, BackgroundEffectBase)
    assert SnowBackground.frame_invariant is False
    assert SnowBackground.restart_on_visit is False


@pytest.mark.parametrize("flake", ["dot", "plus", "snow"])
def test_never_paints_black(flake) -> None:
    fx = SnowBackground(flake=flake, density=10, seed=1)
    for f in range(0, 80, 7):
        c = HeadlessCanvas(width=64, height=32)
        calls = []
        orig = c.SetPixel

        def spy(x, y, r, g, b, _o=orig, _calls=calls):
            _calls.append((r, g, b))
            _o(x, y, r, g, b)

        c.SetPixel = spy
        fx.paint(c, f)
        assert calls
        assert all(rgb != (0, 0, 0) for rgb in calls)


def test_pure_function_of_frame() -> None:
    fx = SnowBackground(density=8, seed=9)
    a = _paint(fx, 17)._pixels
    _paint(fx, 40)
    assert _paint(fx, 17)._pixels == a
    assert a


def test_unseeded_instance_is_frame_pure() -> None:
    fx = SnowBackground()
    assert _paint(fx, 5)._pixels == _paint(fx, 5)._pixels
    assert fx._seed != SnowBackground()._seed


def test_flakes_fall() -> None:
    args = (160, 64, 7, 1.0, 0.0, 0.0, 0.0, 1)
    # Same epoch: pick a start frame where flake 0 does not wrap within 10 frames.
    for f0 in range(0, 100):
        y0 = flake_position(0, f0, *args)[1]
        y1 = flake_position(0, f0 + 10, *args)[1]
        if y1 > y0:
            return
    pytest.fail("flake 0 never moved downward")


def test_wrap_reenters_at_new_x() -> None:
    w, h, sh = 160, 16, 1
    args = (w, h, 5, 1.0, 0.0, 0.0, 0.0, sh)
    ys = [(f, flake_position(0, f, w, h, *args[2:])[:2]) for f in range(0, 400)]
    xs_by_pass = []
    prev_y = None
    cur = None
    for _f, (x, y) in ys:
        if prev_y is None or y < prev_y:  # wrapped to the top
            cur = x
            xs_by_pass.append(cur)
        prev_y = y
    assert len(xs_by_pass) >= 3
    assert len(set(xs_by_pass)) > 1


def test_intensity_range() -> None:
    for i in range(30):
        for f in (0, 50, 500):
            inten = flake_position(i, f, 160, 16, 3, 1.0, 0.4, 0.3, 0.0, 1)[2]
            assert 0.5 <= inten <= 1.0


def _differs(frame=30, **kw) -> bool:
    a = _paint(SnowBackground(density=8, seed=1), frame)._pixels
    b = _paint(SnowBackground(density=8, seed=1, **kw), frame)._pixels
    return a != b


@pytest.mark.parametrize(
    "kw",
    [
        {"drift": 3.0},
        {"wind": 1.0},
        {"speed_variation": 0.9},
        {"speed": 2.0},
    ],
    ids=["drift", "wind", "speed_variation", "speed"],
)
def test_knob_changes_the_field(kw) -> None:
    assert _differs(**kw)


def test_zero_knobs_are_stable() -> None:
    assert not _differs()  # same args -> same field (guards the helper itself)


def test_emoji_flakes_keep_sprite_colors() -> None:
    sprite = set(flake_pixels("snow", (200, 220, 255)).values())
    fx = SnowBackground(flake="snow", density=10, seed=2)
    seen = set()
    for f in range(0, 120, 9):
        seen |= set(_paint(fx, f, 64, 32)._pixels.values())
    assert seen and seen <= sprite  # never intensity-shaded


def test_dim_color_never_paints_black() -> None:
    fx = SnowBackground(color=(1, 1, 1))
    assert fx._shade(8) == ()  # 1 * 0.5 rounds to 0: skipped, not black
    assert fx._shade(16) != ()
    for f in range(0, 80, 5):
        assert (0, 0, 0) not in _paint(fx, f, 64, 32)._pixels.values()


@pytest.mark.parametrize("w,h,n", [(160, 16, 8), (128, 64, 25), (256, 64, 49)])
def test_count_by_geometry(w, h, n) -> None:
    assert flake_count(w, h, 3.0) == n


def test_flake_pixels_shapes() -> None:
    assert flake_pixels("dot", (9, 9, 9)) == {(0, 0): (9, 9, 9)}
    plus = flake_pixels("plus", (9, 9, 9))
    assert set(plus) == {(1, 0), (0, 1), (1, 1), (2, 1), (1, 2)}
    assert flake_height("dot") == 1 and flake_height("plus") == 3
    assert 1 <= flake_height("snow") <= 8


def test_emoji_flake_is_8px_on_bigsign() -> None:
    real = HeadlessCanvas(width=256, height=64)
    wrapped = ScaledCanvas(real, scale=4, content_height=16)
    fx = SnowBackground(flake="snow", density=0.001, seed=4)  # exactly 1 flake
    assert flake_count(256, 64, fx.density) == 1
    # A frame where the whole sprite is on-canvas.
    for f in range(0, 100):
        real._pixels.clear()
        fx.paint(wrapped, f)
        if len(real._pixels) == len(flake_pixels("snow", (0, 0, 0))):
            break
    xs = [p[0] for p in real._pixels]
    ys = [p[1] for p in real._pixels]
    assert real._pixels
    assert max(xs) - min(xs) + 1 <= 8
    assert max(ys) - min(ys) + 1 <= 8


def test_hires_only_slug_refused() -> None:
    pack_only = next((s for s in emoji_slugs() if not capture_sprite(s, 1, None)), None)
    if pack_only is None:
        pytest.skip("no pack-only (no 8x8 form) slug available in emoji_slugs()")
    with pytest.raises(ValueError, match=pack_only) as e:
        SnowBackground(flake=pack_only)
    assert '"dot"' in str(e.value)


def test_unknown_slug_refused() -> None:
    with pytest.raises(ValueError, match="no_such_slug_xyz") as e:
        SnowBackground(flake="no_such_slug_xyz")
    assert '"dot"' in str(e.value)


class TestScaledCanvas:
    def test_paints_only_on_real(self) -> None:
        real = HeadlessCanvas(width=256, height=64)
        wrapped = ScaledCanvas(real, scale=4, content_height=16)
        fx = SnowBackground(seed=1)
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
        {"speed": 0},
        {"speed": 5.5},
        {"speed_variation": 1.0},
        {"speed_variation": -0.1},
        {"drift": -1},
        {"wind": "x"},
        {"color": [1, 2]},
        {"color": [1, 2, 300]},
        {"seed": "x"},
    ],
)
def test_bad_args(kwargs) -> None:
    with pytest.raises(ValueError):
        SnowBackground(**kwargs)


def test_perf_bigsign() -> None:
    fx = SnowBackground(flake="snow", density=3, seed=1)
    samples = []
    for f in range(12):
        c = HeadlessCanvas(width=256, height=64)
        t0 = time.perf_counter()
        fx.paint(c, f)
        samples.append(time.perf_counter() - t0)
    med = statistics.median(samples)
    print(f"snow paint median {med * 1000:.3f} ms")
    assert med <= 0.003


@pytest.mark.parametrize(
    "kw",
    [
        {"density": float("inf")},
        {"density": float("nan")},
        {"wind": float("inf")},
        {"speed": float("inf")},
    ],
)
def test_non_finite_numbers_rejected(kw):
    with pytest.raises(ValueError, match="finite"):
        SnowBackground(**kw)


def test_builtin_flake_shape() -> None:
    px = flake_pixels("flake", (200, 220, 255))
    assert set(px) == {
        (2, 2),
        (2, 0),
        (0, 2),
        (4, 2),
        (2, 4),
        (1, 1),
        (3, 1),
        (1, 3),
        (3, 3),
    }
    assert flake_height("flake") == 5
    # symmetric under both mirrors
    assert {(4 - x, y) for x, y in px} == set(px)
    assert {(x, 4 - y) for x, y in px} == set(px)


def test_builtin_flake_paints_never_black() -> None:
    fx = SnowBackground(flake="flake", density=10, seed=1)
    assert fx._is_emoji is False
    for f in range(0, 80, 7):
        c = _paint(fx, f, 160, 16)
        assert c._pixels
        assert all(v != (0, 0, 0) for v in c._pixels.values())


def test_density_cap() -> None:
    SnowBackground(density=50)
    with pytest.raises(ValueError, match=r"max 50"):
        SnowBackground(density=50.5)
    with pytest.raises(ValueError, match="density"):
        SnowBackground(density=1000)
