"""flair.snow transition (flurry mode): per-column jittered front, snapshots
taken once per firing, flakes on top."""

import time
from typing import Any
from unittest import mock

import pytest
from led_ticker.plugin import ScaledCanvas

from led_ticker_flair.flair.snow import Snow

RED = (255, 0, 0)
GREEN = (0, 255, 0)


class _StubCanvas:
    def __init__(self, width: int = 16, height: int = 16) -> None:
        self.width = width
        self.height = height
        self._pixels: dict[tuple[int, int], tuple[int, int, int]] = {}

    def SetPixel(self, x: int, y: int, r: int, g: int, b: int) -> None:  # noqa: N802
        self._pixels[(x, y)] = (r, g, b)

    def SubFill(self, x: int, y: int, w: int, h: int, r: int, g: int, b: int) -> None:  # noqa: N802
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                self.SetPixel(xx, yy, r, g, b)

    def Clear(self) -> None:  # noqa: N802
        self._pixels.clear()

    def Fill(self, r: int, g: int, b: int) -> None:  # noqa: N802
        for y in range(self.height):
            for x in range(self.width):
                self.SetPixel(x, y, r, g, b)


def _fill_widget(color: tuple[int, int, int], w: int, h: int) -> Any:
    """Widget painting a solid logical rectangle of `color`."""
    widget = mock.Mock()
    widget.hold_time = 0.0

    def _draw(canvas: Any, cursor_pos: int = 0, **kw: Any) -> tuple[Any, int]:
        for y in range(h):
            for x in range(w):
                canvas.SetPixel(x, y, *color)
        return (canvas, cursor_pos)

    widget.draw.side_effect = _draw
    return widget


def _empty_widget() -> Any:
    widget = mock.Mock()
    widget.draw.side_effect = lambda canvas, cursor_pos=0, **kw: (canvas, cursor_pos)
    return widget


def _snow(**kw: Any) -> Snow:
    kw.setdefault("seed", 7)
    return Snow(**kw)


def _scene(w: int = 16, h: int = 16):
    return _fill_widget(RED, w, h), _fill_widget(GREEN, w, h)


class TestFrames:
    def test_t0_shows_only_outgoing(self):
        c = _StubCanvas()
        o, i = _scene()
        _snow().frame_at(0.0, c, o, i)
        assert {v for v in c._pixels.values() if v != (230, 240, 255)} == {RED}
        assert GREEN not in c._pixels.values()

    def test_snap_shows_only_incoming(self):
        c = _StubCanvas()
        o, i = _scene()
        s = _snow()
        s.frame_at(0.0, c, o, i)
        c.Clear()
        s.frame_at(0.95, c, o, i)
        assert set(c._pixels.values()) == {GREEN}

    def test_no_outgoing_pixels_after_snap(self):
        c = _StubCanvas()
        o, i = _scene()
        s = _snow()
        s.frame_at(0.0, c, o, i)
        c.Clear()
        s.frame_at(0.99, c, o, i)
        assert RED not in c._pixels.values()

    def test_front_monotone(self):
        c = _StubCanvas(16, 16)
        o, i = _scene()
        s = _snow()
        s._paint_flakes = lambda real, t: None  # isolate the front
        s.frame_at(0.0, c, o, i)
        prev = [0] * 16
        t = 0.0
        while t < 0.94:
            c.Clear()
            s.frame_at(round(t, 3), c, o, i)
            cols = [
                sum(1 for y in range(16) if c._pixels.get((x, y)) == GREEN)
                for x in range(16)
            ]
            assert all(a >= b for a, b in zip(cols, prev, strict=True)), t
            prev = cols
            t += 0.02
        assert any(prev)

    def test_front_mixes_both_sides_midway(self):
        c = _StubCanvas()
        o, i = _scene()
        s = _snow(density=0.001)
        s.frame_at(0.0, c, o, i)
        c.Clear()
        s.frame_at(0.5, c, o, i)
        vals = set(c._pixels.values())
        assert RED in vals and GREEN in vals

    def test_flakes_peak_midway_and_absent_at_ends(self):
        c = _StubCanvas(64, 32)
        o, i = _empty_widget(), _empty_widget()
        s = _snow(density=40)
        s.frame_at(0.0, c, o, i)
        assert not c._pixels
        c.Clear()
        s.frame_at(0.5, c, o, i)
        assert c._pixels  # flakes only (both widgets empty)
        assert (0, 0, 0) not in c._pixels.values()
        c.Clear()
        s.frame_at(0.949, c, o, i)
        assert not c._pixels  # flake count reaches 0 just before the snap

    def test_empty_outgoing(self):
        c = _StubCanvas()
        _, i = _scene()
        s = _snow()
        s.frame_at(0.0, c, _empty_widget(), i)
        c.Clear()
        s.frame_at(0.5, c, _empty_widget(), i)
        c.Clear()
        s.frame_at(0.95, c, _empty_widget(), i)
        assert set(c._pixels.values()) == {GREEN}


class TestSeeding:
    @staticmethod
    def _firing(s: Snow) -> dict:
        c = _StubCanvas(64, 32)
        o, i = _scene(64, 32)
        s.frame_at(0.0, c, o, i)
        c.Clear()
        s.frame_at(0.5, c, o, i)
        return dict(c._pixels)

    def test_unseeded_instance_differs_per_firing(self):
        s = Snow(density=20)
        assert self._firing(s) != self._firing(s)

    def test_explicit_seed_reproducible(self):
        a = self._firing(Snow(seed=5, density=20))
        b = self._firing(Snow(seed=5, density=20))
        assert a == b
        s = Snow(seed=5, density=20)
        assert self._firing(s) == self._firing(s)


class TestSnapshots:
    def test_outgoing_not_drawn_live_after_snapshot(self):
        c = _StubCanvas()
        o, i = _scene()
        s = _snow()
        for t in (0.0, 0.2, 0.5, 0.8):
            s.frame_at(t, c, o, i)
        assert o.draw.call_count == 1

    def test_refire_resnapshots(self):
        c = _StubCanvas()
        o, i = _scene()
        s = _snow()
        s.frame_at(0.0, c, o, i)
        s.frame_at(0.9, c, o, i)
        s.frame_at(0.1, c, o, i)
        assert o.draw.call_count == 2

    def test_t0_always_refires(self):
        c = _StubCanvas()
        o, i = _scene()
        s = _snow()
        s.frame_at(0.0, c, o, i)
        s.frame_at(0.0, c, o, i)
        assert o.draw.call_count == 2

    def test_equal_nonzero_t_is_not_a_refire(self):
        c = _StubCanvas()
        o, i = _scene()
        s = _snow()
        s.frame_at(0.3, c, o, i)
        s.frame_at(0.3, c, o, i)
        assert o.draw.call_count == 1

    def test_bordered_incoming_no_flash(self, monkeypatch):
        calls: list[Any] = []
        monkeypatch.setattr(
            "led_ticker_flair.flair.snow.snap_reset", lambda cv, bg: calls.append(bg)
        )
        c = _StubCanvas()
        o, i = _scene()
        _snow().frame_at(0.96, c, o, i, incoming_bg_color=(9, 9, 9))
        assert calls[-1] == (9, 9, 9)


class TestScaled:
    def test_scaled_physical_resolution(self):
        real = _StubCanvas(128, 64)
        sc = ScaledCanvas(real, scale=4, content_height=16)
        o = _fill_widget(RED, 32, 16)
        i = _fill_widget(GREEN, 32, 16)
        s = _snow(density=0.001)
        s._paint_flakes = lambda r, t: None  # isolate the front
        s.frame_at(0.0, sc, o, i)
        real.Clear()
        s.frame_at(0.5, sc, o, i)
        # first RED row per column = the front; at logical resolution it
        # would always be a multiple of the scale (4)
        firsts = []
        for x in range(128):
            reds = [y for y in range(64) if real._pixels.get((x, y)) == RED]
            greens = [y for y in range(64) if real._pixels.get((x, y)) == GREEN]
            if reds and greens:
                firsts.append(min(reds))
        assert firsts and any(y % 4 != 0 for y in firsts)
        assert sc.real is real


class TestValidation:
    def test_build_mode_refused(self):
        with pytest.raises(ValueError, match="planned, not yet available"):
            Snow(mode="build")

    def test_unknown_mode(self):
        with pytest.raises(ValueError, match="mode"):
            Snow(mode="blizzard")

    def test_bad_flake(self):
        with pytest.raises(ValueError, match="flake"):
            Snow(flake="not_a_slug_zzz")

    def test_bad_color_and_density(self):
        with pytest.raises(ValueError, match="color"):
            Snow(color=(1, 2))
        with pytest.raises(ValueError, match="density"):
            Snow(density=0)

    @pytest.mark.parametrize(
        "kw",
        [
            {"density": float("inf")},
            {"density": float("nan")},
            {"wind": float("inf")},
            {"wind": float("nan")},
            {"drift": float("inf")},
        ],
    )
    def test_non_finite_rejected(self, kw):
        with pytest.raises(ValueError, match="finite"):
            Snow(**kw)

    def test_attrs(self):
        assert Snow.min_frames == 24
        assert Snow.scale_switch_at == 1.0


class TestPerf:
    def test_perf_bigsign(self):
        c = _StubCanvas(256, 64)
        c.SetPixel = lambda *a: None  # type: ignore[method-assign]  # time OUR code
        o = _fill_widget(RED, 256, 64)
        i = _fill_widget(GREEN, 256, 64)
        s = _snow(density=6.0)
        s.frame_at(0.0, c, o, i)
        worst = 0.0
        for _ in range(5):
            t0 = time.perf_counter()
            s.frame_at(0.5, c, o, i)
            worst = max(worst, time.perf_counter() - t0)
        print(f"snow worst frame {worst * 1000:.2f} ms")
        assert worst < 0.008, worst
