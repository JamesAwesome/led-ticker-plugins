"""flair.interlock — Interlock transition classes.

Stub canvas / widget fixtures copied from test_flair_laser_transition.py
(the per-file duplication is this repo's convention).
"""

from typing import Any
from unittest import mock

import pytest
from led_ticker.plugin import ScaledCanvas, unwrap_to_real
from PIL import Image

from led_ticker_flair import flair as flair_pkg
from led_ticker_flair.flair.interlock import (
    Interlock,
    InterlockAlternating,
    InterlockFlipped,
    InterlockRandom,
    InterlockVertical,
    InterlockVerticalFlipped,
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
    widget = mock.Mock()
    widget.hold_time = 0.0

    def _draw(canvas: Any, cursor_pos: int = 0, **kw: Any) -> tuple[Any, int]:
        unwrap_to_real(canvas).SetImage(img, 0, 0)
        return (canvas, cursor_pos)

    widget.draw.side_effect = _draw
    return widget


RED = (255, 0, 0)
GREEN = (0, 255, 0)
# Row 0 (even strand) and row 1 (odd strand), both at x=5 on a 20x2 panel.
PAIR = [(5, 0, RED), (5, 1, RED)]
# Centred block on a 160x16 panel: x 60..99 on every row -> both parities.
CENTRED = [(x, y, GREEN) for x in (60, 99) for y in range(16)]


def _frame(p: Any, t: float, c: Any, o: Any, i: Any, **kw: Any) -> dict:
    c.Clear()
    p.frame_at(t, c, o, i, **kw)
    return dict(c._pixels)


class TestInterlockFrames:
    def test_t0_paints_outgoing_unshifted(self):
        c = _StubCanvas(20, 2)
        px = _frame(Interlock(), 0.0, c, _text_widget(PAIR), _text_widget([]))
        assert px == {(5, 0): RED, (5, 1): RED}

    def test_split_moves_even_right_odd_left(self):
        c = _StubCanvas(20, 2)
        p = Interlock()
        o = _text_widget(PAIR)
        p.frame_at(0.0, c, o, _text_widget([]))
        px = _frame(p, 0.25, c, o, _text_widget([]))
        (x0,) = [x for (x, y) in px if y == 0]
        (x1,) = [x for (x, y) in px if y == 1]
        assert x0 > 5
        assert x1 < 5

    def test_flipped_reverses_parity_directions(self):
        c = _StubCanvas(20, 2)
        p = InterlockFlipped()
        o = _text_widget(PAIR)
        p.frame_at(0.0, c, o, _text_widget([]))
        px = _frame(p, 0.25, c, o, _text_widget([]))
        (x0,) = [x for (x, y) in px if y == 0]
        (x1,) = [x for (x, y) in px if y == 1]
        assert x0 < 5
        assert x1 > 5

    def test_mesh_conveyor_even_enters_from_left_odd_from_right(self):
        c = _StubCanvas(20, 2)
        p = Interlock()
        o, i = _text_widget([]), _text_widget(PAIR)
        p.frame_at(0.0, c, o, i)
        px = _frame(p, 0.8, c, o, i)
        (x0,) = [x for (x, y) in px if y == 0]
        (x1,) = [x for (x, y) in px if y == 1]
        assert x0 < 5  # still arriving from the left
        assert x1 > 5  # still arriving from the right
        px = _frame(p, 0.949, c, o, i)
        assert px == {(5, 0): RED, (5, 1): RED}

    def test_only_t_half_is_empty_for_centred_content(self):
        c = _StubCanvas(160, 16)
        p = Interlock()
        o, i = _text_widget(CENTRED), _text_widget(CENTRED)
        p.frame_at(0.0, c, o, i)
        # Both parity groups (even and odd rows) are still on screen just
        # before and just after the cut-over; only t = 0.5 is empty.
        for t in (0.48, 0.52):
            rows = {y for (_, y) in _frame(p, t, c, o, i)}
            assert rows == set(range(16)), t
        assert _frame(p, 0.5, c, o, i) == {}

    def test_outgoing_snapshot_uses_outgoing_scroll_pos(self):
        c = _StubCanvas(160, 16)
        o = _make_widget()
        Interlock().frame_at(0.0, c, o, _text_widget([]), outgoing_scroll_pos=-37)
        assert o.draw.call_args.kwargs["cursor_pos"] == -37

    def test_vertical_moves_along_y(self):
        c = _StubCanvas(4, 20)
        p = InterlockVertical()
        o = _text_widget([(0, 5, RED), (1, 5, RED)])  # col 0 even, col 1 odd
        p.frame_at(0.0, c, o, _text_widget([]))
        px = _frame(p, 0.25, c, o, _text_widget([]))
        (y0,) = [y for (x, y) in px if x == 0]
        (y1,) = [y for (x, y) in px if x == 1]
        assert y0 > 5  # even columns travel top -> bottom
        assert y1 < 5

    def test_vertical_flipped(self):
        c = _StubCanvas(4, 20)
        p = InterlockVerticalFlipped()
        o = _text_widget([(0, 5, RED), (1, 5, RED)])
        p.frame_at(0.0, c, o, _text_widget([]))
        px = _frame(p, 0.25, c, o, _text_widget([]))
        (y0,) = [y for (x, y) in px if x == 0]
        assert y0 < 5

    def test_snap_draws_incoming_over_bg(self, monkeypatch):
        calls: list[Any] = []
        monkeypatch.setattr(
            "led_ticker_flair.flair.interlock.snap_reset",
            lambda cv, bg: calls.append(bg),
        )
        c = _StubCanvas(20, 2)
        i = _text_widget(PAIR)
        Interlock().frame_at(0.96, c, _text_widget([]), i, incoming_bg_color=(9, 9, 9))
        assert calls[-1] == (9, 9, 9)
        assert c._pixels[(5, 0)] == RED

    def test_outgoing_not_drawn_live_after_snapshot(self):
        c = _StubCanvas(20, 2)
        p = Interlock()
        o = _text_widget(PAIR)
        for t in (0.0, 0.1, 0.2, 0.3, 0.45):
            p.frame_at(t, c, o, _text_widget([]))
        assert o.draw.call_count == 1

    def test_incoming_snapshot_is_lazy_from_rewrapped_canvas(self):
        real = _StubCanvas(256, 64)
        sc4 = ScaledCanvas(real, scale=4, content_height=16)
        scales: list[int] = []
        incoming = mock.Mock()

        def _draw(canvas: Any, cursor_pos: int = 0, **kw: Any) -> tuple[Any, int]:
            scales.append(canvas.scale)
            canvas.SetPixel(1, 1, 0, 255, 0)
            return (canvas, cursor_pos)

        incoming.draw.side_effect = _draw
        p = Interlock()
        for t in (0.0, 0.2, 0.45):
            p.frame_at(t, sc4, _make_widget(), incoming)
        assert incoming.draw.call_count == 0
        sc2 = ScaledCanvas(real, scale=2, content_height=16)
        p.frame_at(0.5, sc2, _make_widget(), incoming)
        assert scales == [2]

    def test_t0_always_starts_a_new_firing(self):
        c = _StubCanvas(20, 2)
        p = Interlock()
        p.frame_at(0.0, c, _text_widget(PAIR), _text_widget([]))
        new = [(9, 0, GREEN)]
        px = _frame(p, 0.0, c, _text_widget(new), _text_widget([]))
        assert px == {(9, 0): GREEN}

    def test_equal_t_is_not_a_refire(self):
        c = _StubCanvas(20, 2)
        p = Interlock()
        p.frame_at(0.3, c, _text_widget(PAIR), _text_widget([]))
        ref = p._out_plan
        p.frame_at(0.3, c, _text_widget(PAIR), _text_widget([]))
        assert p._out_plan is ref

    def test_empty_both_sides_snaps_cleanly(self):
        c = _StubCanvas(20, 2)
        p = Interlock()
        blank = _make_widget(draw_pixel=False)
        for t in (0.0, 0.3, 0.5, 0.7, 0.96):
            p.frame_at(t, c, blank, blank)

    def test_image_widget_snapshots_through_setimage(self):
        img = Image.new("RGB", (20, 2), (0, 0, 0))
        img.putpixel((5, 0), (10, 20, 30))
        c = _StubCanvas(20, 2)
        p = Interlock()
        blank = _make_widget(draw_pixel=False)
        p.frame_at(0.0, c, blank, _image_widget(img))
        px = _frame(p, 0.949, c, blank, _image_widget(img))
        assert px == {(5, 0): (10, 20, 30)}


class TestKnobsVariantsRegistration:
    @pytest.mark.parametrize("bad", [0, -1, True, 1.5, "2"])
    def test_strand_validation(self, bad):
        with pytest.raises(ValueError, match="strand"):
            Interlock(strand=bad)

    def test_multi_variants_forward_strand(self):
        assert all(s.strand == 3 for s in InterlockAlternating(strand=3)._transitions)
        assert all(s.strand == 3 for s in InterlockRandom(strand=3)._transitions)

    def test_strand_two_meshes_pairs_of_rows(self):
        c = _StubCanvas(20, 4)
        p = Interlock(strand=2)
        o = _text_widget([(5, y, RED) for y in range(4)])
        p.frame_at(0.0, c, o, _text_widget([]))
        px = _frame(p, 0.25, c, o, _text_widget([]))
        xs = {y: x for (x, y) in px}
        assert xs[0] == xs[1] > 5  # rows 0-1 = strand 0 (even)
        assert xs[2] == xs[3] < 5  # rows 2-3 = strand 1 (odd)

    def test_registration_four_types_distinct_instances(self):
        api = mock.Mock()
        reg: dict[str, Any] = {}
        api.transition.side_effect = lambda name: (
            lambda cls: reg.__setitem__(name, cls) or cls
        )
        api.animation.side_effect = lambda name: lambda cls: cls
        api.background.side_effect = lambda name: lambda cls: cls
        api.widget.side_effect = lambda name: lambda cls: cls
        flair_pkg.register(api)
        assert reg["interlock.horizontal"] is Interlock
        assert reg["interlock.vertical"] is InterlockVertical
        assert reg["interlock.alternating"] is InterlockAlternating
        assert reg["interlock.random"] is InterlockRandom
        assert reg["interlock.horizontal"]() is not reg["interlock.horizontal"]()

    def test_alternating_cycles_horizontal_vertical(self):
        c = _StubCanvas(20, 2)
        p = InterlockAlternating()
        seen = []
        for _ in range(4):
            p.frame_at(0.0, c, _text_widget(PAIR), _text_widget(PAIR))
            seen.append(p._transitions[p._index]._axis)
            p.frame_at(0.96, c, _text_widget(PAIR), _text_widget(PAIR))
        assert seen == ["horizontal", "vertical", "horizontal", "vertical"]

    def test_random_never_repeats_back_to_back(self):
        c = _StubCanvas(20, 2)
        p = InterlockRandom()
        p._rng.seed(1)
        seen = []
        for _ in range(30):
            p.frame_at(0.0, c, _text_widget(PAIR), _text_widget(PAIR))
            seen.append(p._index)
            p.frame_at(0.96, c, _text_widget(PAIR), _text_widget(PAIR))
        assert all(a != b for a, b in zip(seen, seen[1:], strict=False))
        assert len(set(seen)) >= 3

    def test_min_frames_24_on_every_type(self):
        for cls in (Interlock, InterlockFlipped, InterlockVertical):
            assert cls.min_frames == 24
        assert InterlockAlternating().min_frames == 24
        assert InterlockRandom().min_frames == 24

    def test_keeps_default_scale_switch_at(self):
        assert not hasattr(Interlock(), "scale_switch_at")


class TestPerfUniformity:
    """Count WORK per frame, not time (lightning convention)."""

    @staticmethod
    def _sweep(p: Any, canvas: Any, real: Any, o: Any, i: Any, panel: int) -> None:
        t = 0.0
        while t < 1.0:
            before = len(real.calls)
            p.frame_at(round(t, 3), canvas, o, i)
            n = len(real.calls) - before
            assert n <= int(1.5 * panel), f"t={t:.2f} painted {n} px"
            t += 0.02

    def test_per_frame_paint_volume_bounded(self):
        c = _StubCanvas(160, 16)
        self._sweep(
            Interlock(), c, c, _text_widget(CENTRED), _text_widget(CENTRED), 160 * 16
        )

    def test_alternating_refire_frames_equally_bounded(self):
        c = _StubCanvas(160, 16)
        p = InterlockAlternating()
        o, i = _text_widget(CENTRED), _text_widget(CENTRED)
        for t in (0.0, 0.6, 0.96):
            p.frame_at(t, c, o, i)
        self._sweep(p, c, c, o, i, 160 * 16)

    def test_full_panel_fill_within_paint_bound(self):
        real = _StubCanvas(256, 64)
        sc = ScaledCanvas(real, scale=4, content_height=16)
        full = _make_widget(draw_pixel=False, fill=(7, 7, 7))
        self._sweep(Interlock(), sc, real, full, full, 256 * 64)


class TestRealCoreWidgets:
    """Core's real widgets must snapshot through the raster without tripping,
    and the nearly-landed mesh must match the live snap frame."""

    @staticmethod
    def _landed_vs_snap(p: Any, canvas: Any, real: Any, incoming: Any) -> None:
        blank = _make_widget(draw_pixel=False)
        p.frame_at(0.0, canvas, blank, incoming)
        real.Clear()
        # 0.9499: mesh_offset rounds to 0 even for a 256-px travel, so the
        # landed mesh must equal the live snap frame exactly.
        p.frame_at(0.9499, canvas, blank, incoming)
        landed = dict(real._pixels)
        real.Clear()
        p.frame_at(0.96, canvas, blank, incoming)
        snap = {k: v for k, v in real._pixels.items() if v != (0, 0, 0)}
        assert snap
        assert landed == snap

    def test_ticker_message_scale_1(self):
        from led_ticker.plugin import TickerMessage

        c = _StubCanvas(160, 16)
        self._landed_vs_snap(Interlock(), c, c, TickerMessage(text="INTERLOCK"))

    def test_ticker_message_scaled(self):
        from led_ticker.plugin import TickerMessage

        real = _StubCanvas(256, 64)
        sc = ScaledCanvas(real, scale=4, content_height=16)
        self._landed_vs_snap(Interlock(), sc, real, TickerMessage(text="INTERLOCK"))

    def test_gif_widget_through_setimage(self, tmp_path):
        from led_ticker.widgets.gif import GifPlayer

        frame = Image.new("RGB", (32, 16), (0, 0, 0))
        for x in range(8, 24):
            frame.putpixel((x, 8), (200, 40, 40))
        path = tmp_path / "bar.gif"
        frame.save(path, save_all=True, append_images=[frame], duration=100)
        real = _StubCanvas(256, 64)
        sc = ScaledCanvas(real, scale=4, content_height=16)
        self._landed_vs_snap(
            Interlock(), sc, real, GifPlayer(path=str(path), fit="stretch")
        )
