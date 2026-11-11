"""flair.twinkle BACKGROUND — twinkling starfield behind widget content."""

import statistics
import time
from unittest import mock

import pytest
from led_ticker.plugin import (
    BackgroundEffectBase,
    ColorProviderBase,
    HeadlessCanvas,
    ScaledCanvas,
    as_color_provider,
    make_color,
)

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


# --- color providers (rainbow / gradient / any font_color-style value) ------


class _ByCell(ColorProviderBase):
    """Test provider: a distinct, frame-dependent color per cell index."""

    per_char = True
    frame_invariant = False

    def __init__(self) -> None:
        self.calls: list[tuple[int, int, int]] = []

    def color_for(self, frame: int, char_index: int, total_chars: int):
        self.calls.append((frame, char_index, total_chars))
        return make_color((char_index * 37) % 256, (frame * 11) % 256, 200)


def _stars(fx, w, h):
    return {(x, y) for x, y, _f, _o in fx._stars_for(w, h)}


def test_provider_color_follows_star_cell_and_frame() -> None:
    prov = _ByCell()
    fx = TwinkleBackground(density=0.2, color=prov, seed=4)
    c = _paint(fx, 7)
    # 160 px / 6 px cells -> 27 cells, each queried once per paint.
    assert sorted(i for _f, i, _t in prov.calls) == list(range(27))
    assert {(f, t) for f, _i, t in prov.calls} == {(7, 27)}
    for (x, _y), rgb in c._pixels.items():
        base = prov.color_for(7, x // 6, 27)
        peak = (base.red, base.green, base.blue)
        lvl = max(rgb) / max(peak)
        assert all(abs(v - p * lvl) <= 1.5 for v, p in zip(rgb, peak, strict=True))


def test_provider_cells_are_logical_on_scaled_canvas() -> None:
    real = HeadlessCanvas(width=256, height=64)
    wrapped = ScaledCanvas(real, scale=4, content_height=16)
    prov = _ByCell()
    fx = TwinkleBackground(density=0.05, color=prov, seed=1)
    fx.paint(wrapped, 3)
    # one cell = 6 LOGICAL px = 24 real px -> ceil(256 / 24) = 11 cells
    assert {t for _f, _i, t in prov.calls} == {11}
    assert real._pixels


def test_provider_cells_on_unwrapped_real_canvas_match_wrapper() -> None:
    """Image hosts (gif / image) paint backgrounds on the UNWRAPPED real
    canvas; cells must still be 6 LOGICAL px, i.e. match the wrapper."""
    via_wrapper, via_real = _ByCell(), _ByCell()
    real = HeadlessCanvas(width=256, height=64)
    TwinkleBackground(density=0.05, color=via_wrapper, seed=1).paint(
        ScaledCanvas(real, scale=4, content_height=16), 3
    )
    TwinkleBackground(density=0.05, color=via_real, seed=1).paint(
        HeadlessCanvas(width=256, height=64), 3
    )
    assert {t for _f, _i, t in via_real.calls} == {11}
    assert sorted(via_real.calls) == sorted(via_wrapper.calls)


def test_provider_cell_count_on_evenly_divisible_width() -> None:
    """192 px / 6 px = exactly 32 cells (no spare cell, so a gradient's
    rightmost column reaches its `to` color)."""
    prov = _ByCell()
    TwinkleBackground(density=0.05, color=prov, seed=1).paint(
        HeadlessCanvas(width=192, height=16), 0
    )
    assert {t for _f, _i, t in prov.calls} == {32}
    assert max(i for _f, i, _t in prov.calls) == 31


def test_wrapper_scale_wins_over_height_fallback() -> None:
    """A scale=2 section on a 64-row panel: the wrapper's scale (12 px
    cells), not the real_h // 16 guess (24 px)."""
    prov = _ByCell()
    real = HeadlessCanvas(width=256, height=64)
    TwinkleBackground(density=0.05, color=prov, seed=1).paint(
        ScaledCanvas(real, scale=2, content_height=32), 0
    )
    assert {t for _f, _i, t in prov.calls} == {22}  # ceil(256 / 12)


def test_short_unwrapped_canvas_does_not_divide_by_zero() -> None:
    """real_h < 16 on an image host: the scale clamps to 1 (6 px cells)."""
    prov = _ByCell()
    TwinkleBackground(density=0.2, color=prov, seed=1).paint(
        HeadlessCanvas(width=64, height=8), 0
    )
    assert {t for _f, _i, t in prov.calls} == {11}  # ceil(64 / 6)


def test_gradient_runs_left_to_right() -> None:
    fx = TwinkleBackground(
        density=0.3,
        color={"style": "gradient", "from": [255, 0, 0], "to": [0, 0, 255]},
        seed=2,
    )
    px = {}
    for f in range(0, 24, 2):  # union over frames so every star lights
        px.update(_paint(fx, f)._pixels)
    left = [rgb for (x, _y), rgb in px.items() if x < 12]
    right = [rgb for (x, _y), rgb in px.items() if x >= 148]
    assert left and right
    assert all(r > b for r, _g, b in left)
    assert all(b > r for r, _g, b in right)


def test_rainbow_string_animates_with_frame() -> None:
    fx = TwinkleBackground(density=0.3, color="rainbow", seed=2)
    a, b = _paint(fx, 3)._pixels, _paint(fx, 30)._pixels
    common = set(a) & set(b)
    assert common

    def hue_sig(rgb):
        m = max(rgb)
        return tuple(round(v / m, 1) for v in rgb)

    assert any(hue_sig(a[p]) != hue_sig(b[p]) for p in common)


def test_provider_is_frame_pure() -> None:
    fx = TwinkleBackground(density=0.1, color="rainbow", seed=6)
    a = _paint(fx, 12)._pixels
    _paint(fx, 50)
    assert _paint(fx, 12)._pixels == a


def test_provider_black_cells_paint_nothing() -> None:
    fx = TwinkleBackground(density=0.2, color=as_color_provider(make_color(0, 0, 0)))
    assert not _paint(fx, 5)._pixels


def test_provider_brightness_still_applies() -> None:
    spec = {"style": "gradient", "from": [255, 200, 0], "to": [255, 0, 200]}
    full = _paint(TwinkleBackground(density=0.2, color=spec, seed=3), 4)._pixels
    dim = _paint(
        TwinkleBackground(density=0.2, color=spec, seed=3, brightness=0.25), 4
    )._pixels
    assert dim and max(map(max, dim.values())) < max(map(max, full.values()))


@pytest.mark.parametrize(
    "color",
    ["nope", {"style": "no_such_style"}, {"style": "gradient"}, 7],
)
def test_bad_color_provider_specs(color) -> None:
    with pytest.raises(ValueError):
        TwinkleBackground(color=color)


def test_perf_bigsign_rainbow() -> None:
    fx = TwinkleBackground(seed=1, color="rainbow")
    real = HeadlessCanvas(width=256, height=64)
    c = ScaledCanvas(real, scale=4, content_height=16)
    fx.paint(c, 0)
    samples = []
    for f in range(1, 31):
        t0 = time.perf_counter()
        fx.paint(c, f)
        samples.append(time.perf_counter() - t0)
    assert statistics.median(samples) <= 0.004
