"""flair.sand transition: outgoing crumbles off the bottom, incoming pours in
from the top and stacks into place."""

import time
from typing import Any
from unittest import mock

import pytest
from led_ticker.plugin import ScaledCanvas

from led_ticker_flair.flair.sand import Sand

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


def _block_widget(
    color: tuple[int, int, int], w: int, h: int, y0: int = 0, x0: int = 0, step: int = 1
) -> Any:
    """Widget painting a logical rectangle of `color` at rows y0..y0+h,
    columns x0..x0+w (every `step`-th column)."""
    widget = mock.Mock()
    widget.hold_time = 0.0

    def _draw(canvas: Any, cursor_pos: int = 0, **kw: Any) -> tuple[Any, int]:
        for y in range(y0, y0 + h):
            for x in range(x0, x0 + w, step):
                canvas.SetPixel(x, y, *color)
        return (canvas, cursor_pos)

    widget.draw.side_effect = _draw
    return widget


def _empty_widget() -> Any:
    widget = mock.Mock()
    widget.draw.side_effect = lambda canvas, cursor_pos=0, **kw: (canvas, cursor_pos)
    return widget


def _frame(s: Sand, t: float, c: Any, o: Any, i: Any, **kw: Any) -> dict:
    c.Clear()  # the runner clears before every frame_at
    s.frame_at(t, c, o, i, **kw)
    return dict(c._pixels)


class TestFrames:
    def test_t0_shows_only_outgoing(self):
        c = _StubCanvas()
        o, i = _block_widget(RED, 16, 16), _block_widget(GREEN, 16, 16)
        px = _frame(Sand(seed=1), 0.0, c, o, i)
        assert px == {(x, y): RED for x in range(16) for y in range(16)}

    def test_snap_shows_only_incoming(self, monkeypatch):
        calls: list[Any] = []
        monkeypatch.setattr(
            "led_ticker_flair.flair.sand.snap_reset", lambda cv, bg: calls.append(bg)
        )
        c = _StubCanvas()
        o, i = _block_widget(RED, 16, 16), _block_widget(GREEN, 8, 4, y0=3)
        s = Sand(seed=1)
        _frame(s, 0.0, c, o, i)
        px = _frame(s, 0.96, c, o, i, incoming_bg_color=(9, 9, 9))
        assert px == {(x, y): GREEN for x in range(8) for y in range(3, 7)}
        assert calls[-1] == (9, 9, 9)

    def test_crumble_frames_only_outgoing_colors_and_falling(self):
        c = _StubCanvas()
        o, i = _block_widget(RED, 16, 8), _block_widget(GREEN, 16, 16)
        s = Sand(seed=2)
        _frame(s, 0.0, c, o, i)
        px = _frame(s, 0.25, c, o, i)
        assert px
        assert set(px.values()) == {RED}
        assert any(y >= 8 for (_x, y) in px)

    def test_crumble_empty_by_phase_end(self):
        c = _StubCanvas()
        o, i = _block_widget(RED, 16, 16), _block_widget(GREEN, 16, 16)
        s = Sand(seed=3)
        _frame(s, 0.0, c, o, i)
        assert _frame(s, 0.499, c, o, i) == {}

    @pytest.mark.parametrize("size", [(160, 16), (256, 64)])
    def test_crumble_empty_at_last_sampled_frame(self, size):
        # run_transition at min_frames = 30: the last crumble frame is t = 14/30
        w, h = size
        c = _StubCanvas(w, h)
        o, i = _block_widget(RED, w, h), _block_widget(GREEN, w, h)
        s = Sand(seed=8)
        _frame(s, 0.0, c, o, i)
        assert _frame(s, 14 / 30, c, o, i) == {}

    @pytest.mark.parametrize("t", [0.65, 0.75, 0.85])
    def test_pour_only_incoming_colors_and_straight_drop(self, t):
        c = _StubCanvas()
        # every other column only, so a grain that shifts even one column
        # lands in an empty one
        o, i = _block_widget(RED, 16, 16), _block_widget(GREEN, 8, 4, y0=8, step=2)
        s = Sand(seed=4)
        _frame(s, 0.0, c, o, i)
        px = _frame(s, t, c, o, i)
        assert px
        assert set(px.values()) <= {GREEN}
        for x, y in px:
            assert x in (0, 2, 4, 6)  # its own target column: no sideways motion
            assert y <= 11  # never below the lowest target row

    def test_pour_complete_before_snap(self):
        c = _StubCanvas()
        o, i = _block_widget(RED, 16, 16), _block_widget(GREEN, 16, 8, y0=8)
        s = Sand(seed=5)
        _frame(s, 0.0, c, o, i)
        _frame(s, 0.6, c, o, i)
        px = _frame(s, 0.9499, c, o, i)
        assert px == {(x, y): GREEN for x in range(16) for y in range(8, 16)}

    def test_scroll_pos_forwarded(self):
        c = _StubCanvas()
        o, i = _block_widget(RED, 4, 4), _block_widget(GREEN, 4, 4)
        _frame(Sand(seed=1), 0.0, c, o, i, outgoing_scroll_pos=7)
        assert o.draw.call_args.kwargs["cursor_pos"] == 7

    def test_empty_outgoing_and_incoming(self):
        c = _StubCanvas()
        o, i = _empty_widget(), _empty_widget()
        s = Sand(seed=1)
        for t in (0.0, 0.25, 0.6, 0.9):
            assert _frame(s, t, c, o, i) == {}

    def test_incoming_snapshot_taken_lazily_after_switch(self):
        c = _StubCanvas()
        o, i = _block_widget(RED, 4, 4), _block_widget(GREEN, 4, 4)
        s = Sand(seed=1)
        for t in (0.0, 0.2, 0.45):
            _frame(s, t, c, o, i)
        assert i.draw.call_count == 0
        for t in (0.5, 0.7, 0.9):
            _frame(s, t, c, o, i)
        assert i.draw.call_count == 1
        assert o.draw.call_count == 1

    def test_sparse_frames(self):
        c = _StubCanvas()
        o, i = _block_widget(RED, 16, 16), _block_widget(GREEN, 8, 8)
        s = Sand(seed=6)
        for t in (0.0, 0.11, 0.33, 0.51, 0.77, 0.96):
            _frame(s, t, c, o, i)
        px = _frame(s, 1.0, c, o, i)
        assert px == {(x, y): GREEN for x in range(8) for y in range(8)}

    @pytest.mark.parametrize("t", [0.926, 14 / 15])
    def test_pour_landed_by_last_sampled_frame_bigsign(self, t):
        # last sampled pour frame: ~0.926 under ease_in_out, 28/30 linear
        c = _StubCanvas(256, 64)
        o, i = _block_widget(RED, 256, 64), _block_widget(GREEN, 256, 64)
        s = Sand(seed=9)
        _frame(s, 0.0, c, o, i)
        _frame(s, 0.5, c, o, i)
        px = _frame(s, t, c, o, i)
        assert px == {(x, y): GREEN for x in range(256) for y in range(64)}

    def test_real_rederived_every_frame(self):
        # the runner hands a different back buffer each frame (constraint #1);
        # a ScaledCanvas wrapper has its .real swapped in place
        a, b = _StubCanvas(64, 16), _StubCanvas(64, 16)
        sc = ScaledCanvas(a, scale=4, content_height=4)
        o, i = _block_widget(RED, 16, 4), _block_widget(GREEN, 16, 4)
        s = Sand(seed=1)
        for k, t in enumerate((0.0, 0.1, 0.2, 0.6, 0.7, 0.8)):
            buf = a if k % 2 == 0 else b
            sc.real = buf
            buf.Clear()
            s.frame_at(t, sc, o, i)
            assert buf._pixels, t

    def test_first_frame_in_pour_skips_crumble(self):
        c = _StubCanvas()
        o, i = _block_widget(RED, 16, 16), _block_widget(GREEN, 16, 16)
        s = Sand(seed=1)
        px = _frame(s, 0.6, c, o, i)
        assert RED not in px.values()


class TestFiring:
    @staticmethod
    def _firing(s: Sand) -> list[dict]:
        c = _StubCanvas(32, 16)
        o, i = _block_widget(RED, 32, 16), _block_widget(GREEN, 32, 16)
        return [_frame(s, t, c, o, i) for t in (0.0, 0.25, 0.7)]

    def test_explicit_seed_reproducible(self):
        assert self._firing(Sand(seed=5)) == self._firing(Sand(seed=5))
        s = Sand(seed=5)
        assert self._firing(s) == self._firing(s)

    def test_unseeded_instance_differs_per_firing(self):
        s = Sand()
        assert self._firing(s) != self._firing(s)

    def test_t0_always_refires(self):
        c = _StubCanvas()
        o, i = _block_widget(RED, 4, 4), _block_widget(GREEN, 4, 4)
        s = Sand(seed=1)
        _frame(s, 0.0, c, o, i)
        _frame(s, 0.0, c, o, i)
        assert o.draw.call_count == 2

    def test_refire_resnapshots(self):
        c = _StubCanvas()
        o, i = _block_widget(RED, 4, 4), _block_widget(GREEN, 4, 4)
        s = Sand(seed=1)
        for t in (0.0, 0.6, 0.9, 0.1, 0.6):
            _frame(s, t, c, o, i)
        assert o.draw.call_count == 2
        assert i.draw.call_count == 2


class TestScaled:
    @pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
    def test_scaled_physical_resolution(self, seed):
        real = _StubCanvas(64, 16)
        sc = ScaledCanvas(real, scale=4, content_height=4)
        # one logical pixel away from the edges -> one 4x4 real block
        o, i = _block_widget(RED, 1, 1, x0=4, y0=0), _block_widget(GREEN, 1, 1)
        s = Sand(seed=seed)
        s.frame_at(0.0, sc, o, i)
        grains = s._crumble
        assert grains is not None and len(grains) == 16
        # every real LED is its own grain with its own timing and drift
        assert len({(g[0], g[1]) for g in grains}) == 16
        assert len({g[5] for g in grains}) == 16
        assert len({g[6] for g in grains}) == 16
        real.Clear()
        s.frame_at(0.25, sc, o, i)
        painted = set(real._pixels)
        xs = {x for x, _ in painted}
        ys = {y for _, y in painted}
        is_block = (
            len(painted) == 16 and max(xs) - min(xs) == 3 and max(ys) - min(ys) == 3
        )
        assert not is_block
        assert sc.real is real


class TestValidation:
    @pytest.mark.parametrize("seed", [True, "x", 1.5])
    def test_bad_seed(self, seed):
        with pytest.raises(ValueError, match="seed"):
            Sand(seed=seed)

    def test_attrs(self):
        assert Sand.min_frames == 30
        assert Sand.scale_switch_at == 0.5


class TestPerf:
    def test_perf_bigsign(self):
        c = _StubCanvas(256, 64)
        c.SetPixel = lambda *a: None  # type: ignore[method-assign]  # time OUR code
        c.Clear = lambda: None  # type: ignore[method-assign]
        o, i = _block_widget(RED, 256, 64), _block_widget(GREEN, 256, 64)
        s = Sand(seed=1)
        s.frame_at(0.0, c, o, i)
        s.frame_at(0.5, c, o, i)
        for t in (0.3, 0.75):
            worst = 0.0
            for _ in range(5):
                t0 = time.perf_counter()
                s.frame_at(t, c, o, i)
                worst = max(worst, time.perf_counter() - t0)
            assert worst < 0.015, (t, worst)
