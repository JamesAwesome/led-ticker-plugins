"""flair.laser — Laser transition classes.

Stub canvas / widget fixtures copied from test_flair_fairy_transition.py
(the per-file duplication is this repo's convention), plus a `SetImage`
on the stub so image widgets can draw live at the snap frame.
"""

from typing import Any
from unittest import mock

from led_ticker.plugin import ScaledCanvas, unwrap_to_real
from PIL import Image

from led_ticker_flair import flair as flair_pkg
from led_ticker_flair.flair.laser import (
    Laser,
    LaserAlternating,
    LaserBottom,
    LaserLeft,
    LaserRandom,
    LaserRight,
)


class _StubCanvas:
    """Minimal scale=1 real-canvas stub."""

    def __init__(self, width: int = 160, height: int = 16) -> None:
        self.width = width
        self.height = height
        self._pixels: dict[tuple[int, int], tuple[int, int, int]] = {}
        self.calls: list[tuple[int, int, int, int, int]] = []

    def SetPixel(self, x: int, y: int, r: int, g: int, b: int) -> None:  # noqa: N802
        self._pixels[(x, y)] = (r, g, b)
        self.calls.append((x, y, r, g, b))

    def SubFill(  # noqa: N802
        self, x: int, y: int, w: int, h: int, r: int, g: int, b: int
    ) -> None:
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                self.SetPixel(xx, yy, r, g, b)

    def Clear(self) -> None:  # noqa: N802
        self._pixels.clear()

    def Fill(self, r: int, g: int, b: int) -> None:  # noqa: N802
        for y in range(self.height):
            for x in range(self.width):
                self.SetPixel(x, y, r, g, b)

    def SetImage(self, image: Any, offset_x: int = 0, offset_y: int = 0) -> None:  # noqa: N802
        pixels = image.load()
        w, h = image.size
        for y in range(h):
            for x in range(w):
                px = pixels[x, y]
                if len(px) == 4 and px[3] == 0:
                    r, g, b = 0, 0, 0
                else:
                    r, g, b = px[0], px[1], px[2]
                self.SetPixel(offset_x + x, offset_y + y, r, g, b)


def _make_widget(draw_pixel: bool = True, fill: Any = None) -> Any:
    widget = mock.Mock()
    widget.hold_time = 0.0

    def _draw(canvas: Any, cursor_pos: int = 0, **kw: Any) -> tuple[Any, int]:
        if fill is not None:
            canvas.Fill(*fill)
        if draw_pixel:
            canvas.SetPixel(0, 0, 255, 0, 0)
        return (canvas, cursor_pos)

    widget.draw.side_effect = _draw
    return widget


def _text_widget(pixels: list[tuple[int, int, tuple[int, int, int]]]) -> Any:
    """A widget that SetPixels a fixed list onto whatever canvas it gets."""
    widget = mock.Mock()
    widget.hold_time = 0.0

    def _draw(canvas: Any, cursor_pos: int = 0, **kw: Any) -> tuple[Any, int]:
        for x, y, (r, g, b) in pixels:
            canvas.SetPixel(x, y, r, g, b)
        return (canvas, cursor_pos)

    widget.draw.side_effect = _draw
    return widget


def _image_widget(img: Any) -> Any:
    """A widget that paints via unwrap_to_real(canvas).SetImage (gif/still path)."""
    widget = mock.Mock()
    widget.hold_time = 0.0

    def _draw(canvas: Any, cursor_pos: int = 0, **kw: Any) -> tuple[Any, int]:
        unwrap_to_real(canvas).SetImage(img, 0, 0)
        return (canvas, cursor_pos)

    widget.draw.side_effect = _draw
    return widget


OUT = [(0, 0, (255, 0, 0)), (1, 0, (255, 0, 0)), (2, 0, (255, 0, 0))]  # n_out = 3
INC = [(5, 1, (0, 255, 0)), (6, 1, (0, 0, 255))]  # n_in = 2


class TestLaserFrames:
    def test_t0_paints_outgoing_snapshot_only_no_beam(self):
        c = _StubCanvas(8, 2)
        p = Laser()
        p.frame_at(0.0, c, _text_widget(OUT), _text_widget(INC))
        assert c._pixels == {(x, y): col for x, y, col in OUT}

    def test_erase_frame_hides_visited_and_draws_beam_in_head_colour(self):
        # N=5; visited == int(5*0.4/0.95) == 2
        c = _StubCanvas(8, 2)
        p = Laser()
        p.frame_at(0.0, c, _text_widget(OUT), _text_widget(INC))
        c.Clear()
        p.frame_at(0.4, c, _text_widget(OUT), _text_widget(INC))
        assert (2, 0) in c._pixels  # unvisited still painted
        assert (0, 0) not in c._pixels  # visited gone
        assert c._pixels[(1, 0)] == (255, 0, 0)  # beam over head (top edge is row 0)

    def test_write_frame_paints_visited_incoming_over_snap_reset(self, monkeypatch):
        # visited == int(5*0.77/0.95) == 4 -> 1 incoming written
        calls: list[Any] = []
        monkeypatch.setattr(
            "led_ticker_flair.flair.laser.snap_reset",
            lambda cv, bg: calls.append(bg),
        )
        c = _StubCanvas(8, 2)
        p = Laser()
        p.frame_at(0.0, c, _text_widget(OUT), _text_widget(INC))
        c.Clear()
        p.frame_at(
            0.77, c, _text_widget(OUT), _text_widget(INC), incoming_bg_color=(1, 2, 3)
        )
        assert calls == [(1, 2, 3)]
        # Parity continues from the erase row (forward) -> incoming row runs
        # backward, so (6,1) is written first.
        assert c._pixels[(6, 1)] == (0, 0, 255)
        assert (5, 1) not in c._pixels
        assert c._pixels[(6, 0)] == (0, 0, 255)  # beam from top edge to head

    def test_outgoing_not_drawn_live_after_snapshot(self):
        c = _StubCanvas(8, 2)
        p = Laser()
        o = _text_widget(OUT)
        for t in (0.0, 0.2, 0.4):
            p.frame_at(t, c, o, _text_widget(INC))
        assert o.draw.call_count == 1

    def test_snap_draws_incoming_over_bg(self, monkeypatch):
        calls: list[Any] = []
        monkeypatch.setattr(
            "led_ticker_flair.flair.laser.snap_reset",
            lambda cv, bg: calls.append(bg),
        )
        c = _StubCanvas(8, 2)
        p = Laser()
        i = _text_widget(INC)
        p.frame_at(0.96, c, _text_widget(OUT), i, incoming_bg_color=(9, 9, 9))
        assert calls[-1] == (9, 9, 9)
        assert i.draw.call_count >= 1
        assert c._pixels[(5, 1)] == (0, 255, 0)
        assert c._pixels[(6, 1)] == (0, 0, 255)

    def test_all_incoming_visited_at_0_95(self):
        c = _StubCanvas(8, 2)
        p = Laser()
        p.frame_at(0.0, c, _text_widget(OUT), _text_widget(INC))
        assert p._visited(0.95) == 5
        assert p._visited(0.949) == 4

    def test_empty_outgoing_starts_writing_immediately(self):
        c = _StubCanvas(8, 2)
        p = Laser()
        p.frame_at(0.0, c, _make_widget(draw_pixel=False), _text_widget(INC))
        c.Clear()
        # visited = int(2*0.5/0.95) = 1
        p.frame_at(0.5, c, _make_widget(draw_pixel=False), _text_widget(INC))
        assert c._pixels[(5, 1)] == (0, 255, 0)

    def test_zero_lit_pixels_both_sides_snaps_cleanly(self):
        c = _StubCanvas(8, 2)
        p = Laser()
        for t in (0.0, 0.5, 0.96):
            p.frame_at(
                t, c, _make_widget(draw_pixel=False), _make_widget(draw_pixel=False)
            )

    def test_refire_resnapshots_changed_incoming(self):
        c = _StubCanvas(8, 2)
        p = Laser()
        p.frame_at(0.0, c, _text_widget(OUT), _text_widget(INC))
        p.frame_at(0.96, c, _text_widget(OUT), _text_widget(INC))
        new = [(7, 1, (9, 9, 200))]
        p.frame_at(0.0, c, _text_widget(INC), _text_widget(new))
        c.Clear()
        p.frame_at(0.96, c, _text_widget(INC), _text_widget(new))
        assert c._pixels[(7, 1)] == (9, 9, 200)

    def test_equal_t_is_not_a_refire(self):
        c = _StubCanvas(8, 2)
        p = Laser()
        p.frame_at(0.3, c, _text_widget(OUT), _text_widget(INC))
        out_ref = p._out
        p.frame_at(0.3, c, _text_widget(OUT), _text_widget(INC))
        assert p._out is out_ref

    def test_image_widget_snapshots_through_setimage(self):
        img = Image.new("RGB", (8, 2), (0, 0, 0))
        img.putpixel((3, 1), (10, 20, 30))
        img.putpixel((5, 1), (1, 2, 3))
        c = _StubCanvas(8, 2)
        p = Laser()
        blank = _make_widget(draw_pixel=False)
        p.frame_at(0.0, c, blank, _image_widget(img))
        c.Clear()
        p.frame_at(0.96, c, blank, _image_widget(img))  # snap: live draw via SetImage
        assert c._pixels[(5, 1)] == (1, 2, 3)
        p.frame_at(0.0, c, blank, _image_widget(img))
        c.Clear()
        # N=2 -> visited 1 -> (3,1) only
        p.frame_at(0.949, c, blank, _image_widget(img))
        assert c._pixels[(3, 1)] == (10, 20, 30)
        assert (5, 1) not in c._pixels


class TestLaserScaled:
    def test_scaled_canvas_beam_is_one_real_pixel_wide(self):
        real = _StubCanvas(256, 64)
        sc = ScaledCanvas(real, scale=4, content_height=8)  # 32-row band, y_offset 16
        p = Laser()
        o = _make_widget(draw_pixel=False)
        # logical (0,0) = real 4x4 block at rows 16..19
        i = _text_widget([(0, 0, (0, 200, 0))])
        p.frame_at(0.0, sc, o, i)
        real.Clear()
        p.frame_at(0.3, sc, o, i)  # visited = int(16*0.3/0.95) = 5 real px
        assert sc.y_offset_real == 16
        beam_cols = {x for (x, y) in real._pixels if y < 16}
        assert len(beam_cols) == 1
        assert (next(iter(beam_cols)), 0) in real._pixels

    def test_beam_reaches_real_edge_through_letterbox_band(self):
        real = _StubCanvas(256, 64)
        sc = ScaledCanvas(real, scale=2, content_height=16)  # 32-row band centred
        p = Laser()
        i = _text_widget([(0, 0, (0, 200, 0))])
        p.frame_at(0.0, sc, _make_widget(draw_pixel=False), i)
        real.Clear()
        p.frame_at(0.3, sc, _make_widget(draw_pixel=False), i)
        assert (0, 0) in real._pixels  # top origin: beam starts at REAL row 0


class TestVariantsAndRegistration:
    def test_registration_six_types_distinct_instances(self):
        api = mock.Mock()
        reg: dict[str, Any] = {}
        api.transition.side_effect = lambda name: (
            lambda cls: reg.__setitem__(name, cls) or cls
        )
        api.animation.side_effect = lambda name: lambda cls: cls
        api.widget.side_effect = lambda name: lambda cls: cls
        flair_pkg.register(api)
        names = {
            "laser.top",
            "laser.bottom",
            "laser.left",
            "laser.right",
            "laser.alternating",
            "laser.random",
        }
        assert names <= set(reg)
        assert reg["laser.top"]() is not reg["laser.top"]()

    def test_origins_per_variant(self):
        assert (LaserBottom._origin, LaserLeft._origin, LaserRight._origin) == (
            "bottom",
            "left",
            "right",
        )

    def test_alternating_cycles_top_right_bottom_left(self):
        c = _StubCanvas(8, 2)
        p = LaserAlternating()
        seen = []
        for _ in range(5):
            p.frame_at(0.0, c, _text_widget(OUT), _text_widget(INC))
            seen.append(p._transitions[p._index]._origin)
            p.frame_at(0.96, c, _text_widget(OUT), _text_widget(INC))
        assert seen == ["top", "right", "bottom", "left", "top"]

    def test_random_never_repeats_back_to_back(self):
        c = _StubCanvas(8, 2)
        p = LaserRandom()
        p._rng.seed(1)
        seen = []
        for _ in range(30):
            p.frame_at(0.0, c, _text_widget(OUT), _text_widget(INC))
            seen.append(p._transitions[p._index]._origin)
            p.frame_at(0.96, c, _text_widget(OUT), _text_widget(INC))
        assert all(a != b for a, b in zip(seen, seen[1:], strict=False))
        assert len(set(seen)) >= 3

    def test_min_frames_48_on_every_type(self):
        for cls in (Laser, LaserBottom, LaserLeft, LaserRight):
            assert cls.min_frames == 48
        assert LaserAlternating().min_frames == 48
        assert LaserRandom().min_frames == 48


class TestPerfUniformity:
    """Committed CI-safe perf gate (lightning convention): count WORK per
    frame, not time — a deferred-backlog bug fails the bound
    deterministically."""

    def test_per_frame_paint_volume_bounded(self):
        canvas = _StubCanvas(width=160, height=16)
        o = _text_widget(OUT)
        i = _text_widget(INC)
        p = Laser()
        counts = []
        t = 0.02
        while t < 1.0:
            before = len(canvas.calls)
            p.frame_at(round(t, 3), canvas, o, i)
            counts.append((round(t, 2), len(canvas.calls) - before))
            t += 0.02
        panel = 160 * 16
        worst_t, worst = max(counts, key=lambda c: c[1])
        assert worst <= int(1.5 * panel), (
            f"frame at t={worst_t} painted {worst} px (> 1.5x panel {panel})"
        )

    def test_alternating_refire_frames_equally_bounded(self):
        canvas = _StubCanvas(width=160, height=16)
        o = _text_widget(OUT)
        i = _text_widget(INC)
        p = LaserAlternating()
        for t in (0.3, 0.6, 0.96):
            p.frame_at(t, canvas, o, i)
        panel = 160 * 16
        t = 0.02
        while t < 1.0:
            before = len(canvas.calls)
            p.frame_at(round(t, 3), canvas, o, i)
            assert len(canvas.calls) - before <= int(1.5 * panel)
            t += 0.02

    def test_full_panel_fill_within_paint_bound(self):
        real = _StubCanvas(256, 64)
        sc = ScaledCanvas(real, scale=4, content_height=16)
        full = _make_widget(draw_pixel=False, fill=(7, 7, 7))
        p = Laser()
        t = 0.02
        while t < 1.0:
            before = len(real.calls)
            p.frame_at(round(t, 3), sc, full, full)
            assert len(real.calls) - before <= int(1.5 * 256 * 64)
            t += 0.02
